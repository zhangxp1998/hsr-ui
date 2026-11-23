"""Installation, private data and device configuration; no local account defaults."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('HSR_UI_WORKSPACE', str(HERE))).expanduser().resolve()
ASSETS = Path(os.environ.get('HSR_UI_ASSET_DIR', str(HERE / 'assets'))).expanduser().resolve()
SCRIPTS = HERE / 'scripts'
SERIAL = os.environ.get('HSR_UI_SERIAL', '')
GAME_PACKAGE = os.environ.get('HSR_UI_GAME_PACKAGE', 'com.HoYoverse.hkrpgoversea')
