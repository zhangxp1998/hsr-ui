"""Fail-closed loader for the complete, versioned original-Sprite template set."""
import hashlib
import json
from pathlib import Path
from PIL import Image


def load_assets(root=None, recipe_path=None):
    if root is None:
        from paths import ASSETS
        root = ASSETS
    root = Path(root).resolve()
    recipe_path = Path(recipe_path) if recipe_path is not None else Path(__file__).parent / 'assets/sprite-recipe.json'
    recipe_bytes = recipe_path.read_bytes()
    recipe = json.loads(recipe_bytes)
    manifest = json.loads((root / 'sprite-manifest.json').read_text())
    if (manifest.get('schema') != 'hsr-original-sprites-v1'
            or manifest.get('recipe_sha256') != hashlib.sha256(recipe_bytes).hexdigest()
            or manifest.get('index_sha256') != recipe['index']['sha256']
            or manifest.get('game_version') != recipe['game_version']):
        raise ValueError('sprite_manifest_version_mismatch; rebuild with scripts/export_sprites.py')
    expected = {r['name']: r for r in recipe['sprites']}
    if len(expected) != len(recipe['sprites']):
        raise ValueError('duplicate_recipe_sprite')
    records = manifest.get('assets', [])
    if len(records) != len(expected) or {r.get('name') for r in records} != set(expected):
        raise ValueError('incomplete_original_sprite_set')
    assets = {}
    for record in records:
        name = record['name']
        spec = expected[name]
        if record.get('source_kind') != 'original_sprite' or record.get('source_screenshot') is not False:
            raise ValueError('non_original_sprite_source: ' + name)
        for field in ('cab', 'path_id', 'sprite_name', 'bundle', 'rgba_sha256', 'render_mode'):
            if record.get(field) != spec[field]:
                raise ValueError('sprite_provenance_mismatch: ' + name)
        if record.get('bundle_sha256') != recipe['bundles'][spec['bundle']]['sha256']:
            raise ValueError('sprite_bundle_mismatch: ' + name)
        image_name = Path(record['image'])
        path = (root / image_name).resolve()
        if image_name.is_absolute() or not path.is_relative_to(root) or path.suffix != '.webp':
            raise ValueError('invalid_sprite_image_path: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('file_sha256'):
            raise ValueError('sprite_file_changed: ' + name)
        with Image.open(path) as image:
            rgba = image.convert('RGBA')
            if list(rgba.size) != record.get('dimensions') or hashlib.sha256(rgba.tobytes()).hexdigest() != spec['rgba_sha256']:
                raise ValueError('sprite_pixels_changed: ' + name)
        assets[name] = dict(path=str(path), provenance=record, source='original_sprite')
    return assets
