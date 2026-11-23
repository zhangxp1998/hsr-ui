#!/usr/bin/env python3
"""Temporarily dim the TCL tablet for automation, preserving its settings."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


DEFAULT_STATE_DIR = Path(os.environ.get('HSR_UI_BRIGHTNESS_STATE',
    str(Path.home()/'.local/state/hsr-ui/brightness'))).expanduser()
SCHEMA = 1
MINIMUM_BRIGHTNESS = 1


def adb(*args):
    result = subprocess.run(['/usr/bin/adb', *args], check=True, capture_output=True,
                            text=True, timeout=15)
    return result.stdout.strip()


def tablet_id(serial):
    if not serial:
        raise ValueError('HSR_UI_SERIAL is required for live device access')
    lines = [line.split() for line in adb('devices', '-l').splitlines()]
    model='model:'+os.environ.get('HSR_UI_MODEL','9469X')
    product='device:'+os.environ.get('HSR_UI_PRODUCT','Bellona_WF_GL')
    tablets = [parts for parts in lines if len(parts) >= 2 and parts[1] == 'device'
               and model in parts[2:] and product in parts[2:]]
    if len(tablets) != 1 or tablets[0][0] != serial:
        raise ValueError('selected device is not the unique online TCL tablet')
    hardware_id = adb('-s', serial, 'shell', 'getprop', 'ro.serialno')
    if not hardware_id or hardware_id.lower() in ('unknown', 'null'):
        raise ValueError('tablet hardware identity is unavailable')
    user = adb('-s', serial, 'shell', 'am', 'get-current-user')
    if not re.fullmatch(r'\d+', user):
        raise ValueError('current Android user is unavailable')
    return hardware_id, user


def get_setting(serial, user, name):
    value = adb('-s', serial, 'shell', 'settings', '--user', user, 'get', 'system', name)
    if not re.fullmatch(r'\d+', value):
        raise ValueError(f'cannot safely read {name}: {value!r}')
    return int(value)


def get_settings(serial, user):
    mode = get_setting(serial, user, 'screen_brightness_mode')
    brightness = get_setting(serial, user, 'screen_brightness')
    if mode not in (0, 1) or not 0 <= brightness <= 255:
        raise ValueError('unrecognized brightness settings')
    return mode, brightness


def put_setting(serial, user, name, value):
    adb('-s', serial, 'shell', 'settings', '--user', user, 'put', 'system', name, str(value))


def read_state(path):
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(state, dict) or state.get('schema') != SCHEMA
            or state.get('phase') not in ('applying', 'active', 'restoring')
            or not isinstance(state.get('hardware_id'), str)
            or not isinstance(state.get('user'), str) or not re.fullmatch(r'\d+', state['user'])
            or type(state.get('mode')) is not int or state['mode'] not in (0, 1)
            or type(state.get('brightness')) is not int or not 0 <= state['brightness'] <= 255):
        raise ValueError('saved brightness state is invalid; refusing to overwrite it')
    return state


def write_state(path, state):
    fd, temporary = tempfile.mkstemp(prefix='.brightness-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(state, out, ensure_ascii=False)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def finish(serial, hardware_id, user, path):
    state = read_state(path)
    if state is None:
        return {'status': 'no_saved_state'}
    if state['hardware_id'] != hardware_id or state['user'] != user:
        raise ValueError('saved settings belong to a different tablet or Android user')
    current = get_settings(serial, user)
    original = state['mode'], state['brightness']
    if current == original:
        path.unlink()
        return {'status': 'already_restored', 'mode': current[0], 'brightness': current[1]}
    expected = (0, MINIMUM_BRIGHTNESS)
    partial = (current[0] in (0, original[0]) and
               current[1] in (MINIMUM_BRIGHTNESS, original[1]))
    if current != expected and not (state['phase'] != 'active' and partial):
        raise ValueError('brightness was changed during the task; preserving the current setting and saved state')
    state['phase'] = 'restoring'
    write_state(path, state)
    put_setting(serial, user, 'screen_brightness_mode', 0)
    put_setting(serial, user, 'screen_brightness', original[1])
    if original[0] == 1:
        put_setting(serial, user, 'screen_brightness_mode', 1)
    restored = get_settings(serial, user)
    if restored[0] != original[0] or (original[0] == 0 and restored[1] != original[1]):
        raise RuntimeError('brightness restore could not be verified; saved state retained')
    path.unlink()
    return {'status': 'restored', 'mode': restored[0], 'brightness': restored[1]}


def start(serial, hardware_id, user, path):
    if read_state(path) is not None:
        raise ValueError('a brightness session is already recorded; inspect it before recovery')
    mode, brightness = get_settings(serial, user)
    state = {'schema': SCHEMA, 'phase': 'applying', 'hardware_id': hardware_id,
             'user': user, 'mode': mode, 'brightness': brightness}
    write_state(path, state)
    try:
        put_setting(serial, user, 'screen_brightness_mode', 0)
        put_setting(serial, user, 'screen_brightness', MINIMUM_BRIGHTNESS)
        if get_settings(serial, user) != (0, MINIMUM_BRIGHTNESS):
            raise RuntimeError('minimum brightness could not be verified')
        state['phase'] = 'active'
        write_state(path, state)
    except Exception as exc:
        try:
            rollback = finish(serial, hardware_id, user, path)
        except Exception as rollback_error:
            raise RuntimeError(f'{exc}; brightness recovery failed: {rollback_error}; saved state retained') from exc
        raise RuntimeError(f'{exc}; brightness recovery: {rollback["status"]}') from exc
    return {'status': 'active', 'mode': 0, 'brightness': MINIMUM_BRIGHTNESS,
            'original_mode': mode, 'original_brightness': brightness}


def status(serial, hardware_id, user, path):
    state = read_state(path)
    if state is not None and (state['hardware_id'] != hardware_id or state['user'] != user):
        raise ValueError('saved settings belong to a different tablet or Android user')
    mode, brightness = get_settings(serial, user)
    power = adb('-s', serial, 'shell', 'dumpsys', 'power')
    override = re.search(r'mScreenBrightnessOverrideFromWindowManager=([^\s]+)', power)
    return {'status': 'recorded' if state else 'no_saved_state', 'mode': mode,
            'brightness': brightness, 'phase': state['phase'] if state else None,
            'window_brightness_override': override.group(1) if override else 'unknown'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True, help='current TCL ADB serial')
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument('action', choices=('start', 'finish', 'status'))
    args = parser.parse_args()
    try:
        args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_fd = os.open(args.state_dir / '.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(lock_fd, 'a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            hardware_id, user = tablet_id(args.serial)
            path = args.state_dir / 'saved.json'
            result = {'start': start, 'finish': finish, 'status': status}[args.action](
                args.serial, hardware_id, user, path)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
