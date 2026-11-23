# Publication validation

The sanitized snapshot was revalidated on 2026-11-23. Configuration/data-loading
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
