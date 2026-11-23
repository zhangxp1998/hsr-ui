# Local visual assets

No game images, APKs, model weights, screenshot crops or replay fixtures are
distributed. The recognizer cannot analyze pages until appropriate local assets
exist. Nothing is fetched from a device by installation or `status`.

The `assets/` JSON files document the original calibration's named templates.
Supply images obtained from your own authorized installation at the indicated
relative paths, preserving alpha, dimensions and crop identity. A filename alone
does not establish that an image matches this calibration.

The root defaults to `assets/` next to the code; `HSR_UI_ASSET_DIR` can point to a
private directory with the same layout, including copies of the manifests:

```text
assets/
  resource-icons.json
  screenshot-profiles.json
  <images named by these two manifests>
  hud/
    candidate-provenance.json
    common-discovery-index.json
    <candidate images>
    common/<common images>
  guide/
    asset-provenance.json
    images/<guide images>
```

`image` is relative to the directory containing its manifest. Resource drawables
are distinct from Unity Sprites. `screenshot-profiles.json` describes explicitly
reviewed screenshot-derived templates, not original Sprites. Names and source
categories are retained; source-machine paths, screenshot hashes and account
data are omitted. `layout-profile.json` contains only measured layout geometry.

Guide matching requires the five named main-tab glyphs and `CommonCloseIcon@3x`.
Additional covered pages require the names referenced in `vision.py` and the
state readers. Large manifests include candidate assets that are not all used.
Unknown or changed variants need separate calibration and negative controls;
do not lower matching thresholds to make a missing asset pass.

All image formats are ignored by Git, including locally supplied game templates.
Generated screenshots must persist only as JPEG; PNG/raw capture buffers stay
in memory. EXIF capture metadata can include a real device identity, so do not
publish raw screenshots or output JSON without a separate privacy review.
