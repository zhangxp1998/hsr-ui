# Local semantic console

```sh
.venv/bin/python web/server.py --port 8000
```

Open http://localhost:8000 on the same machine. The server binds only to loopback.
Page loads and polls do not unlock or take over a device. Explicit connection
requires `HSR_UI_SERIAL` and local visual assets, plus an unlocked foreground game.
If needed, configure `HSR_UI_UNLOCK_HELPER` as an absolute local executable; it is
called once with `unlock`. No PIN, secret store or unlock implementation is shipped.

Connecting verifies identity, owns an exclusive brightness save/restore session,
and sets minimum manual brightness. Real browser input renews a 60-second server
deadline; polls and recognition frames do not. Expiry/shutdown locks and verifies
the device, releases capture, restores owned brightness and clears refs, preserving
the running game. External brightness changes are not silently overwritten.

The canvas follows device proportions and uses semantic observationId/ref only.
Sixteen bounded owner slots preserve the exact displayed frame for ten seconds;
the backend never rebinds a click to an unseen newer frame. No coordinate,
screenshot, arbitrary-file or shell-command HTTP endpoint exists. Unknown pages
remain non-actionable. Host/Origin checks and a per-process CSRF token protect
POST routes; OCR strings are rendered with textContent. Keep the service local.

`python web/test_server.py` uses a mock tablet/RPC and checks idle ownership,
reference binding, scrolling, no retries and HTTP boundaries. It does not prove
live browser/device behavior on an uncalibrated device.
