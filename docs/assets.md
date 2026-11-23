# Original-Sprite assets

**Zero screenshot-derived templates. Every current recognition template is a
Unity Sprite from the game installation.** No game images, APKs, resource blocks,
replay fixtures or model weights are distributed in this repository.

The versioned `assets/sprite-recipe.json` selects the complete **28-template set
used by this recognizer**, not every Sprite in the installed game. The current
resource index contains 733,565 bundle rows; it is not a full decoded catalog.
The recipe binds the game version, index/APK hashes, bundle payload, CAB,
Sprite pathId, render mode and decoded RGBA hash. Names alone are insufficient.

## Rebuild from your own device

Installation and `status` do not read a device or download resources. Run these
explicit commands when preparing local assets:

```sh
.venv/bin/pip install -r requirements-assets.txt
.venv/bin/python scripts/export_sprites.py prepare-codec --codec-dir private-data/codec
.venv/bin/python scripts/export_sprites.py build \
  --codec-dir private-data/codec \
  --serial "$HSR_UI_SERIAL" \
  --output private-data/assets \
  --cache private-data/resource-cache
export HSR_UI_ASSET_DIR="$PWD/private-data/assets"
```

`prepare-codec` downloads two data-only source tables from a pinned AnimeStudio
revision and verifies their SHA-256. See [third-party notices](../THIRD_PARTY_NOTICES.md).
The Linux adapter uses UnityPy, texture2ddecoder, pyooz and lz4 instead of
reimplementing Unity/ASTC/Oodle. No downloaded C# or game code is executed.

`build` requires an explicit device identity. It reads the installed version,
resource index, precise resource ranges and the asset APK split. Device slices
are read twice and must agree; every cached payload is hash-verified. The APK
and index can require hundreds of MB on first use. It does **not** unlock the
screen, capture it, launch or stop the game, send input, or change device settings.
Use `--adb-port` only for a nondefault ADB server. `--package` and `--remote-root`
are configurable. A version/hash mismatch fails rather than guessing new IDs.

For an offline resource mirror use `--source-root /path/to/resources` instead of
`--serial`. Supply the named index, block files and APK split in that directory;
a previously verified export cache can also satisfy reads. Keep these files
private. The output manifest is replaced only after every template succeeds.

## Output and enforcement

```text
private-data/assets/
  sprite-manifest.json
  sprites/<decoded-RGBA-SHA256>.webp
```

WebP is lossless with exact transparent RGB preservation; every output is decoded
again and must match the source RGBA bytes. `sprite_assets.py` checks the complete
recipe, original-only provenance, file/pixel hashes and path containment. Missing,
changed, screenshot or Android-drawable sources are rejected. There is no legacy
screenshot-manifest fallback. Failed recognition stays unknown, not a new crop.

All 28 templates are original Sprites. In particular:

- Battle HUD uses original `IconAuto` and `IconBattlePause` from the native Battle_UI atlas;
  gold ON state has replay coverage. White/gray/OFF/disabled states remain unknown.

| Recognition purpose | Game Sprite | Rendering |
| --- | --- | --- |
| Nameless Honor HUD | `BPiPhone` | Unity Sprite extraction |
| Selected space anchor | `IconMapMazePortal` | Unity Sprite extraction |
| Trailblaze Power | item Sprite `11` | Original logical canvas |
| Reserved Trailblaze Power | item Sprite `12` | Original logical canvas |

The two power Sprites have a 128×128 logical rect exactly covering an independent
same-CAB 128×128 Texture2D, without atlas, packing or rotation. The exporter checks
those properties and preserves that original texture, including its transparent
border. It does not add padding inferred from a screenshot. Other templates use
UnityPy's Sprite/atlas/trim/rotation reconstruction. The shop matcher retains a
stable subregion of its **original** Sprite to ignore a dynamic badge; this is not
a screenshot-derived image.

## What still uses screenshots

Current screen observations, dynamic text/number OCR and before-click
current-vs-fresh patch comparisons still use JPEG frames. These are observations
and guards, not reusable template sources. PNG/raw capture buffers remain in
memory or pipes. Static prefab/resource metadata is not proof of current screen
visibility or live hitboxes.

New game versions or UI variants require an updated recipe and positive/negative
replay checks. Do not lower thresholds to accept a missing Sprite. Do not add
screenshots, game images, full resource indexes or caches to Git.
