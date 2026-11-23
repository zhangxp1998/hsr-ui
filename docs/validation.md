# Validation

## Semantic coverage goal and entry/battle readers, 2026-11-23

- Policy clarification: zero fallback is a coverage goal, not a prohibition.
  The initial prompt/tool-allowlist restriction was withdrawn; screenshots, image
  inspection and verified mapped input remain available for coverage gaps. Follow
  [the iteration loop](workflow.md): record gaps, implement, add regressions and
  verify semantics. Internal JPEG/OCR/fresh-pixel guards stay unchanged.
- **28/28 original templates** rebuilt with the current device index/APK verified:
  the two additional native Battle_UI Sprites are `IconAuto` and `IconBattlePause`.
  No screenshot-crop templates were added. Exact RGBA/provenance checks passed.
- **57 public tests passed**: 35 semantic/source/parser contracts, 17 Web tests
  and 5 plugin tests. Login includes pre-input server-change rejection; current
  field/supply UID changes or disappearance also refuse before input.
- **Eight private regression groups passed** against the publishable CPU code:
  base 72/72, audit gaps 11/11, top bar 17/17, power/planning 16/16,
  daily state 43/43, catch-up 15/15, supply 13/13 and compact output 13/13.
  An obsolete assertion expecting a screenshot-derived map anchor was corrected
  to require original-Sprite provenance; production thresholds were not relaxed.
- Focused saved-frame checks: login **18/18**, battle HUD **97/97**, integrated
  full-recognizer routing/compact output **18/18**, visible account identity
  **9/9** (field and pre/post-claim monthly overlays, scaling and masked-UID
  negatives). The monthly overlay exposes its current UID for verification
  before the initial claim; no prior account identity is substituted. Battle checks include four
  positive ON frames, 82 non-battle/cinematic negatives, eight synthetic negatives
  and three unchanged appearance-guard refusals. These scopes overlap and are
  calibrated examples, not a global accuracy estimate.
- The reloaded installed native tool verified saved login/battle/field frames,
  including observed server, unknown UID before entry, positively ON auto state,
  all ten field entries and rejection of replay input. The actual exported
  plugin → exported launcher → Python path separately verified login, battle,
  field, map, monthly UID, compact/full output and replay rejection. The native
  tool was separately reloaded and checked for the monthly UID addition.

**Remaining acceptance:** no new complete unattended daily was run. Zero fallback
and completing every daily step are distinct requirements. Auto ON is supported;
OFF/white/gray/disabled remains unknown with no inferred semantic toggle. Fresh
image inspection may verify a fallback action and supply regression evidence for
that gap. Control-free animations may also remain unknown.
The next natural scheduled occurrence still needs whole-run leaf-call auditing.

This change used read-only device resources and saved/private JPEGs; the tablet
remained locked. There was no new live capture, game input, reward claim, challenge
or resource spending. Device/account fixtures and assets remain outside GitHub.

## Original-Sprite-only migration, 2026-11-23

- **26/26 current templates** rebuilt from device resources (25 bundles), with
  original-only provenance and exact RGBA round trips. A separate Python 3.12
  export from the verified payload cache reproduced the Python 3.14 manifest
  and every decoded pixel hash exactly. A cached index cannot conceal a device
  hot update: current index/APK hashes are checked in device mode.
- **44 public tests passed**: 22 semantic/source-integrity/parser contracts,
  17 Web contracts and 5 plugin contracts. This includes screenshot/drawable
  rejection, same-name substitution, pixel tampering, missing templates, path
  escape, malformed bundles and logical-canvas geometry guards.
- Private integration checks: **72/72** base assertions, **17/17** top-bar
  assertions, **16/16** power/planning assertions and **11/11** audit-gap cases.
- Original replacement checks retained existing thresholds: Honor **15/15**
  real-frame checks; anchor **13/13** real/synthetic checks; power **30/30**
  real/synthetic checks. These are calibrated fixtures, not global accuracy.
- The installed native tool was reloaded and verified with saved field, map and
  weekly-preparation frames: all ten HUD entries, the selected anchor and both
  power icons report original-Sprite evidence; replay clicks still refuse.
  The exported plugin → exported launcher → Python path was also exercised for
  full/compact outputs and replay rejection.

The installed source/templates were intentionally migrated for this feature;
legacy template files were retained only in a private backup outside the active
installation. Device work was read-only resource extraction. There was no screen
unlock, new capture, input, gameplay, reward claim or resource spending. The
original OCR and pre-click appearance guards remain in place. This does not
claim a new full unattended daily run or a catalog of every game Sprite.

## Initial sanitized publication

The initial sanitized snapshot was validated on 2026-11-23. Configuration/data-loading
changes were tested independently of the earlier installed-service acceptance.
The original installed source and device environment were not modified.

| Check | Result | Inputs |
| --- | --- | --- |
| Public Python semantic/action contracts | 9/9 passed | Synthetic images and mocked I/O |
| Public Web contracts | 17/17 passed | Mock tablet/RPC, local HTTP |
| Public plugin contracts | 5/5 passed | Temporary executable, including relocated package |
| Existing visual corpus | 72/72 assertions passed | Private calibrated/replay JPEGs |
| Audit-gap regressions | 11/11 test cases passed | Private frame pairs, ten material variants, negative controls |
| Actual plugin → exported launcher → Python | Passed | Offline compact/full results and replay-click rejection |

The 31 public tests need neither game images nor account fixtures. Run commands
are in the README. Private fixture suites were run against this export, not
against the installed production modules; the fixtures, expected inventory values,
raw JSON, per-frame hashes and full logs are intentionally not published.

The real offline transport check verified an exhausted weekly allowance,
material-popup state, compact/full formats, and rejection of a saved-image ref.
It did not unlock, capture, claim, scroll, fight or spend resources on a device.
Live device lifecycle behavior on a new installation remains unverified.

CPU dependencies are pinned in requirements.txt; plugin dependencies are locked
in package-lock.json with OpenClaw 2026.10.9 as the development SDK. The optional
CUDA configuration was not rerun for publication. No new latency claim is made.

Passing this small calibrated corpus is not a global accuracy estimate, nor
proof of a complete unattended battle run. Unknown pages and unseen dialogs
remain unsupported and must not receive inferred actions.

The intended file set and initial Git history were checked for credentials with
Gitleaks 8.30.1 and for known private identifiers, local paths and binary data.
No existing Git history, screenshots, game assets, credentials or runtime state
were imported. Runtime capture data created by future use is not automatically
sanitized; keep it private and out of commits.
