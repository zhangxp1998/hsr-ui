#!/usr/bin/env python3
"""Rebuild calibrated templates from a read-only game installation, never captures.

Only the explicit recipe is exported; this is not a claim to index every asset
in the game. The recipe binds each selector to a specific index/APK and payload.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import zipfile
from sprite_bundle import Codec, SRAM, prepare_codec, require, sha256

HERE = Path(__file__).resolve().parents[1]


def basename(name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name not in ('.', '..'), 'invalid source basename')
    return name


class Source:
    def __init__(self, args, recipe):
        self.args, self.recipe = args, recipe
        self.cache = args.cache.resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.adb = [args.adb]
        if args.adb_port is not None:
            self.adb += ['-P', str(args.adb_port)]
        if args.source_root is None:
            require(bool(args.serial), 'device extraction requires explicit --serial or HSR_UI_SERIAL')
            self.adb += ['-s', args.serial]
            require(self.run('get-state').strip() == b'device', 'device is not ready')
            info = self.shell('dumpsys', 'package', args.package).decode()
            version = re.search(r'\bversionName=(\S+)', info)
            require(version is not None and version[1] == recipe['game_version'], 'game version differs from calibrated recipe')
        index_spec = recipe['index']
        index = self.file(index_spec['file'], index_spec['sha256'])
        self.index = SRAM(index)
        self.bundle_bytes = {}
        self.apks = {}

    def run(self, *args):
        return subprocess.run([*self.adb, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True, timeout=180).stdout

    def shell(self, *args):
        # adb invokes a remote shell: quote every argument even with local argv.
        return self.run('exec-out', shlex.join(args))

    def file(self, name, expected):
        basename(name)
        if self.args.source_root is None:
            # A hot update may keep versionName unchanged. Never let a valid
            # old cache conceal a different currently installed resource index.
            remote = self.args.remote_root.rstrip('/') + '/' + name
            actual = self.shell('sha256sum', remote).decode().split()
            require(bool(actual) and actual[0] == expected, 'device index differs from calibrated recipe')
        target = self.cache / (expected + '-' + name)
        if target.is_file():
            data = target.read_bytes()
        elif self.args.source_root is not None:
            data = (self.args.source_root / name).read_bytes()
        else:
            data = self.shell('cat', self.args.remote_root.rstrip('/') + '/' + name)
        require(sha256(data) == expected, 'source hash mismatch: ' + name)
        if not target.exists():
            target.write_bytes(data)
        return data

    def apk(self, key):
        if key in self.apks:
            return self.apks[key]
        spec = self.recipe['apks'][key]
        name = basename(spec['file'])
        target = self.cache / (spec['sha256'] + '-' + name)
        remote_path = None
        if self.args.source_root is None:
            paths = self.shell('pm', 'path', self.args.package).decode().splitlines()
            paths = [p.removeprefix('package:') for p in paths if p.startswith('package:') and p.endswith('/' + name)]
            require(len(paths) == 1, 'APK split missing or ambiguous: ' + name)
            remote_path = paths[0]
            actual = self.shell('sha256sum', remote_path).decode().split()
            require(bool(actual) and actual[0] == spec['sha256'], 'device APK differs from calibrated recipe')
        if not target.exists():
            if self.args.source_root is not None:
                data = (self.args.source_root / name).read_bytes()
            else:
                data = self.shell('cat', remote_path)
            require(sha256(data) == spec['sha256'], 'APK differs from calibrated recipe')
            target.write_bytes(data)
        require(sha256(target.read_bytes()) == spec['sha256'], 'cached APK hash mismatch')
        self.apks[key] = zipfile.ZipFile(target)
        return self.apks[key]

    def bundle(self, key):
        if key in self.bundle_bytes:
            return self.bundle_bytes[key]
        spec = self.recipe['bundles'][key]
        expected = spec['sha256']
        target = self.cache / (expected + '.encr')
        if target.is_file():
            data = target.read_bytes()
        elif spec['kind'] == 'sram':
            row = self.index.bundle(spec['index'])
            name, offset, length = row['block'], row['offset'], row['length']
            require(length <= 256 * 1024 * 1024, 'bundle exceeds extraction limit')
            if self.args.source_root is not None:
                with (self.args.source_root / name).open('rb') as stream:
                    stream.seek(offset)
                    data = stream.read(length)
            else:
                path = self.args.remote_root.rstrip('/') + '/' + name
                argv = ['dd', 'if=' + path, 'bs=65536', 'iflag=skip_bytes,count_bytes',
                        'skip=' + str(offset), 'count=' + str(length), 'status=none']
                data = self.shell(*argv)
                require(data == self.shell(*argv), 'device resource changed between reads')
            require(len(data) == length, 'truncated bundle read')
        elif spec['kind'] == 'apk':
            archive = self.apk(spec['apk'])
            require(spec['member'].startswith('assets/Asb/Android/') and '..' not in spec['member'].split('/'), 'invalid APK member')
            member = archive.getinfo(spec['member'])
            require(member.file_size <= 256 * 1024 * 1024, 'APK member exceeds limit')
            raw = archive.read(member)
            offset = spec['offset']
            require(0 <= offset <= len(raw) - 25 and raw[offset:offset+5] == b'ENCR\0', 'invalid APK bundle offset')
            length, = struct.unpack_from('>Q', raw, offset + 5)
            require(25 <= length <= len(raw) - offset, 'APK bundle outside member')
            data = raw[offset:offset+length]
        else:
            raise ValueError('unsupported source kind')
        require(sha256(data) == expected, 'bundle hash mismatch: ' + key)
        if not target.exists():
            target.write_bytes(data)
        self.bundle_bytes[key] = data
        return data

    def close(self):
        for archive in self.apks.values():
            archive.close()


def vector(obj, keys):
    return {k: float(getattr(obj, k)) for k in keys}


def render_sprite(sprite, rd, atlas, mode, packing):
    if mode == 'trimmed':
        return sprite.image.convert('RGBA')
    require(mode == 'logical_canvas', 'unsupported Sprite render mode')
    # These standalone item Sprites occupy their entire original texture. Keep
    # its original transparent border, not padding estimated from screenshots.
    texture = rd.texture.deref_parse_as_object()
    rect = sprite.m_Rect
    require(atlas is None and packing == 0 and not (rd.settingsRaw & 1)
            and not rd.alphaTexture and getattr(rd, 'downscaleMultiplier', 1) == 1
            and rect.x == rect.y == 0
            and rect.width == texture.m_Width and rect.height == texture.m_Height,
            'logical canvas is not a standalone full-texture Sprite')
    require(rd.texture.m_FileID == 0, 'logical canvas requires same-CAB texture')
    return texture.image.convert('RGBA')


def build(args):
    import UnityPy
    from UnityPy.export.SpriteHelper import SpriteSettings
    from PIL import Image
    recipe_bytes = args.recipe.read_bytes()
    recipe = json.loads(recipe_bytes)
    require(recipe['schema'] == 'hsr-sprite-recipe-v1', 'unsupported recipe')
    codec = Codec(args.codec_dir)
    source = Source(args, recipe)
    output = args.output.resolve()
    (output / 'sprites').mkdir(parents=True, exist_ok=True)
    records, loaded = [], {}
    try:
        for item in recipe['sprites']:
            # Same-name assets in different bundles are not interchangeable.
            key = item['bundle']
            if key not in loaded:
                env = UnityPy.Environment()
                bundle_keys = [key, *recipe['bundles'][key].get('dependencies', [])]
                names = set()
                for dependency in bundle_keys:
                    for name, raw in codec.nodes(source.bundle(dependency)).items():
                        require(name not in names, 'ambiguous CAB/resource dependency')
                        names.add(name)
                        env.load_file(raw, name=name)
                loaded[key] = env
            env = loaded[key]
            matches = [obj for obj in env.objects if obj.type.name == 'Sprite'
                       and str(obj.path_id) == item['path_id'] and obj.assets_file.name == item['cab']]
            require(len(matches) == 1, 'Sprite selector missing or ambiguous: ' + item['name'])
            obj = matches[0]
            sprite = obj.read()
            require(sprite.m_Name == item['sprite_name'], 'Sprite name changed')
            atlas, rd = None, sprite.m_RD
            if sprite.m_SpriteAtlas:
                atlas = sprite.m_SpriteAtlas.deref_parse_as_object()
                rd = next(v for k, v in atlas.m_RenderDataMap if k == sprite.m_RenderDataKey)
            packing = int(SpriteSettings(rd.settingsRaw).packingRotation)
            mode = item.get('render_mode', 'trimmed')
            image = render_sprite(sprite, rd, atlas, mode, packing)
            rgba_hash = sha256(image.tobytes())
            require(rgba_hash == item['rgba_sha256'], 'decoded pixels differ from calibration: ' + item['name'])
            relative = 'sprites/' + rgba_hash + '.webp'
            path = output / relative
            image.save(path, 'WEBP', lossless=True, exact=True)
            require(Image.open(path).convert('RGBA').tobytes() == image.tobytes(), 'WebP RGBA round trip failed')
            records.append(dict(name=item['name'], sprite_name=sprite.m_Name, image=relative,
                                source_kind='original_sprite', source_screenshot=False,
                                file_sha256=sha256(path.read_bytes()), rgba_sha256=rgba_hash,
                                dimensions=list(image.size), cab=item['cab'], path_id=item['path_id'],
                                bundle=key, bundle_sha256=recipe['bundles'][key]['sha256'],
                                logical_rect=vector(sprite.m_Rect, ['x', 'y', 'width', 'height']),
                                texture_rect=vector(rd.textureRect, ['x', 'y', 'width', 'height']),
                                trim_offset=vector(rd.textureRectOffset, ['x', 'y']),
                                packing_rotation=packing, render_mode=mode,
                                texture_path_id=str(rd.texture.m_PathID),
                                atlas=atlas.m_Name if atlas else None))
            print(json.dumps({'exported': item['name'], 'completed': len(records), 'total': len(recipe['sprites'])}), flush=True)
        require(len({r['name'] for r in records}) == len(records), 'duplicate template names')
        manifest = dict(schema='hsr-original-sprites-v1', game_version=recipe['game_version'],
                        recipe_sha256=sha256(recipe_bytes), index_sha256=source.index.sha256,
                        scope='complete calibrated template set; not every game asset',
                        exporter=dict(unitypy=UnityPy.__version__), assets=records)
        temporary = output / '.sprite-manifest.tmp'
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(output / 'sprite-manifest.json')
        return {'templates': len(records), 'screenshot_templates': 0, 'bundles': len(source.bundle_bytes),
                'index_bundles': source.index.count, 'manifest': str(output / 'sprite-manifest.json')}
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare-codec', help='explicitly fetch hash-pinned upstream format tables')
    prep.add_argument('--codec-dir', type=Path, required=True)
    export = sub.add_parser('build', help='rebuild the entire calibrated template set from game resources')
    export.add_argument('--recipe', type=Path, default=HERE / 'assets' / 'sprite-recipe.json')
    export.add_argument('--codec-dir', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--cache', type=Path, required=True)
    export.add_argument('--source-root', type=Path, help='offline resource directory; includes the index, blocks and APK splits')
    export.add_argument('--adb', default='adb')
    export.add_argument('--adb-port', type=int)
    export.add_argument('--serial', default=os.environ.get('HSR_UI_SERIAL', ''))
    export.add_argument('--package', default=os.environ.get('HSR_UI_GAME_PACKAGE', 'com.HoYoverse.hkrpgoversea'))
    export.add_argument('--remote-root', help='read-only game resource directory on Android')
    args = parser.parse_args()
    if args.command == 'prepare-codec':
        result = prepare_codec(args.codec_dir)
    else:
        require(re.fullmatch(r'[A-Za-z0-9_.]+', args.package) is not None, 'invalid Android package')
        if args.remote_root is None:
            args.remote_root = '/sdcard/Android/data/' + args.package + '/files/Asb/Android'
        result = build(args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
