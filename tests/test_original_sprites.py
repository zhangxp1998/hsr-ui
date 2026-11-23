"""Integrity/negative contracts use synthetic pixels, never game fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE / 'scripts')]
from sprite_assets import load_assets
from sprite_bundle import Codec, SRAM
from export_sprites import Source, render_sprite


def digest(data):
    return hashlib.sha256(data).hexdigest()


class OriginalSprites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        image = Image.new('RGBA', (8, 8), (70, 90, 120, 0))
        image.putpixel((3, 4), (255, 255, 255, 255))
        image.save(self.root / 'test.webp', lossless=True, exact=True)
        self.spec = dict(name='TestSprite', sprite_name='TestSprite', bundle='test',
                         cab='CAB-test', path_id='1', rgba_sha256=digest(image.tobytes()),render_mode='trimmed')
        self.recipe = dict(schema='hsr-sprite-recipe-v1', game_version='test', index={'sha256':'index'},
                           bundles={'test':{'sha256':'bundle'}}, sprites=[self.spec])
        self.recipe_path = self.root / 'recipe.json'
        self.recipe_path.write_text(json.dumps(self.recipe))
        self.manifest = dict(schema='hsr-original-sprites-v1', game_version='test', index_sha256='index',
                             recipe_sha256=digest(self.recipe_path.read_bytes()), assets=[dict(self.spec,
                             image='test.webp', source_kind='original_sprite', source_screenshot=False,
                             file_sha256=digest((self.root / 'test.webp').read_bytes()), dimensions=[8,8], bundle_sha256='bundle')])

    def load(self, manifest=None):
        (self.root / 'sprite-manifest.json').write_text(json.dumps(manifest or self.manifest))
        return load_assets(self.root, self.recipe_path)

    def test_original_pixels_and_hidden_alpha_rgb_preserved(self):
        self.assertEqual(self.load()['TestSprite']['source'], 'original_sprite')

    def test_explicit_screenshot_and_drawable_sources_rejected(self):
        for kind in ('screenshot_template', 'original_android_drawable'):
            value=copy.deepcopy(self.manifest);value['assets'][0]['source_kind']=kind
            with self.assertRaisesRegex(ValueError, 'non_original'):self.load(value)
        value=copy.deepcopy(self.manifest);value['assets'][0]['source_screenshot']=True
        with self.assertRaisesRegex(ValueError, 'non_original'):self.load(value)

    def test_same_name_different_sprite_or_pixels_rejected(self):
        for field,value in [('path_id','2'),('cab','CAB-other'),('rgba_sha256','wrong')]:
            changed=copy.deepcopy(self.manifest);changed['assets'][0][field]=value
            with self.assertRaisesRegex(ValueError, 'provenance'):self.load(changed)
        (self.root/'test.webp').write_bytes(b'not a game sprite')
        with self.assertRaisesRegex(ValueError, 'file_changed'):self.load()

    def test_forged_file_hash_does_not_replace_pixel_identity(self):
        Image.new('RGBA',(8,8),'red').save(self.root/'test.webp',lossless=True)
        self.manifest['assets'][0]['file_sha256']=digest((self.root/'test.webp').read_bytes())
        with self.assertRaisesRegex(ValueError, 'pixels_changed'):self.load()

    def test_missing_duplicate_and_old_version_fail_closed(self):
        for rows in ([],self.manifest['assets']*2):
            value=copy.deepcopy(self.manifest);value['assets']=rows
            with self.assertRaisesRegex(ValueError, 'incomplete'):self.load(value)
        value=copy.deepcopy(self.manifest);value['index_sha256']='new-version'
        with self.assertRaisesRegex(ValueError, 'version_mismatch'):self.load(value)

    def test_image_path_cannot_escape_asset_root(self):
        for path in ('../test.webp','/tmp/test.webp','test.jpg'):
            value=copy.deepcopy(self.manifest);value['assets'][0]['image']=path
            with self.assertRaisesRegex(ValueError, 'image_path'):self.load(value)


class BundleBounds(unittest.TestCase):
    def codec(self):
        result=Codec.__new__(Codec);result.max_bytes=1024*1024
        return result

    def encr(self, node='CAB-test', offset=0, length=3):
        info=struct.pack('>I',1)+struct.pack('>IIH',3,3,0)+struct.pack('>I',1)
        info+=struct.pack('>QQI',offset,length,0)+node.encode()+b'\0'
        return b'ENCR\0'+struct.pack('>QIII',25+len(info)+3,len(info),len(info),0)+info+b'abc'

    def test_raw_bundle_and_truncated_ranges(self):
        data=self.encr()
        self.assertEqual(self.codec().nodes(data),{'CAB-test':b'abc'})
        for bad in (data[:-1],data+b'junk',self.encr(offset=2,length=3),self.encr(node='../outside')):
            with self.assertRaises(ValueError):self.codec().nodes(bad)

    def test_decode_limits_before_codecs_run(self):
        with self.assertRaisesRegex(ValueError,'byte limit'):self.codec().decode(b'',2**31,6)
        with self.assertRaisesRegex(ValueError,'length mismatch'):self.codec().decode(b'x',2,0)
        with self.assertRaisesRegex(ValueError,'unsupported'):self.codec().decode(b'',0,63)

    def test_index_rejects_foreign_or_truncated_data(self):
        for data in (b'',b'UnityFS',b'SRAM\0\5\0\1'+b'\0'*160):
            with self.assertRaises(ValueError):SRAM(data)

    def test_device_requires_explicit_identity_before_adb(self):
        with tempfile.TemporaryDirectory() as folder:
            args=SimpleNamespace(cache=Path(folder),adb='adb',adb_port=None,source_root=None,serial='')
            with patch('export_sprites.subprocess.run',side_effect=AssertionError('ADB must not run')):
                with self.assertRaisesRegex(ValueError,'explicit'):Source(args,{})

    def test_adb_remote_arguments_are_shell_quoted(self):
        source=Source.__new__(Source);calls=[]
        source.run=lambda *args:calls.append(args)
        source.shell('cat','/path with space/$(not-a-command)')
        self.assertEqual(calls,[('exec-out',"cat '/path with space/$(not-a-command)'")])

    def test_old_cache_cannot_hide_a_device_hot_update(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Source.__new__(Source);source.cache=Path(folder)
            data=b'cached-index';expected=digest(data)
            (source.cache/(expected+'-index.bytes')).write_bytes(data)
            source.args=SimpleNamespace(source_root=None,remote_root='/resources')
            source.shell=lambda *args:b'different-current-index  /resources/index.bytes\n'
            with self.assertRaisesRegex(ValueError,'device index differs'):source.file('index.bytes',expected)

    def test_logical_canvas_is_original_texture_not_invented_padding(self):
        image=Image.new('RGBA',(16,16),(20,30,40,0))
        texture=SimpleNamespace(m_Width=16,m_Height=16,image=image)
        pointer=SimpleNamespace(m_FileID=0,deref_parse_as_object=lambda:texture)
        sprite=SimpleNamespace(m_Rect=SimpleNamespace(x=0,y=0,width=16,height=16))
        rd=SimpleNamespace(texture=pointer,settingsRaw=64,alphaTexture=None,downscaleMultiplier=1)
        self.assertEqual(render_sprite(sprite,rd,None,'logical_canvas',0).tobytes(),image.tobytes())
        for field,value in [('x',1),('width',12)]:
            changed=copy.deepcopy(sprite);setattr(changed.m_Rect,field,value)
            with self.assertRaisesRegex(ValueError,'standalone'):render_sprite(changed,rd,None,'logical_canvas',0)
        with self.assertRaisesRegex(ValueError,'standalone'):render_sprite(sprite,rd,object(),'logical_canvas',0)
        with self.assertRaisesRegex(ValueError,'standalone'):render_sprite(sprite,rd,None,'logical_canvas',1)


if __name__=='__main__':unittest.main(verbosity=2)
