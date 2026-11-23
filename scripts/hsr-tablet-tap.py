#!/usr/bin/env python3
"""Tap near the center of a freshly observed Android game button."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adb_screenshot


MAX_JITTER_PX = 8
MAX_SCREENSHOT_AGE_SECONDS = 120


def choose_point(bounds, image_size, randbelow=secrets.randbelow):
    """Choose within a central, inset portion of the supplied button rectangle."""
    left, top, right, bottom = bounds
    width, height = image_size
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError('button bounds must lie within the screenshot')

    def axis(low, high):
        length = high - low
        margin = length // 4
        center = (low + high - 1) // 2
        a = max(low + margin, center - MAX_JITTER_PX)
        b = min(high - 1 - margin, center + MAX_JITTER_PX)
        return a + randbelow(b - a + 1)

    return axis(left, right), axis(top, bottom)


def screenshot_size(path, now=time.time):
    path = Path(path)
    if path.suffix.lower() not in ('.jpg', '.jpeg'):
        raise ValueError('screenshot must be a JPEG file')
    stat = path.stat()
    age = now() - stat.st_mtime
    if age < -5 or age > MAX_SCREENSHOT_AGE_SECONDS:
        raise ValueError('screenshot is stale or has an invalid timestamp')
    result = subprocess.run(
        ['/usr/bin/ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=codec_name,width,height', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True, timeout=10)
    streams = json.loads(result.stdout).get('streams', [])
    if len(streams) != 1 or streams[0].get('codec_name') != 'mjpeg':
        raise ValueError('screenshot is not a JPEG image')
    width, height = streams[0].get('width'), streams[0].get('height')
    if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
        raise ValueError('invalid screenshot dimensions')
    return width, height


def validate_tablet(serial):
    if not serial:
        raise ValueError('HSR_UI_SERIAL is required for live device access')
    result = subprocess.run(['/usr/bin/adb', 'devices', '-l'], check=True,
                            capture_output=True, text=True, timeout=10)
    lines = [line.split() for line in result.stdout.splitlines()]
    matches = [parts for parts in lines if parts and parts[0] == serial]
    if len(matches) != 1 or len(matches[0]) < 2 or matches[0][1] != 'device':
        raise ValueError('selected device is not uniquely online')
    attrs = set(matches[0][2:])
    model='model:'+os.environ.get('HSR_UI_MODEL','9469X')
    product='device:'+os.environ.get('HSR_UI_PRODUCT','Bellona_WF_GL')
    if model not in attrs or product not in attrs:
        raise ValueError('selected device is not the TCL tablet')
    tablets = [parts for parts in lines if len(parts) >= 2 and parts[1] == 'device'
               and model in parts[2:] and product in parts[2:]]
    if len(tablets) != 1:
        raise ValueError('TCL tablet identification is ambiguous')


def map_to_device(point, image_size, path, serial):
    """Map a point only when capture metadata matches the live tablet display."""
    with Image.open(path) as image:
        if image.format != 'JPEG' or image.size != tuple(image_size):
            raise ValueError('screenshot dimensions or format changed')
        description = image.getexif().get(270)
    if not isinstance(description, str):
        raise ValueError('screenshot lacks ADB capture metadata; recapture with adb_screenshot.py')
    meta = json.loads(description)
    if not isinstance(meta, dict) or meta.get('schema') != adb_screenshot.SCHEMA:
        raise ValueError('unrecognized capture metadata')
    if meta.get('serial') != serial:
        raise ValueError('screenshot was captured from a different ADB device')
    native = meta.get('native_size')
    if (not isinstance(native, list) or len(native) != 2 or
            any(type(n) is not int or n < 1 for n in native)):
        raise ValueError('invalid native capture dimensions')
    display = meta.get('display')
    current = adb_screenshot.display_state(serial)
    if (not isinstance(display, dict) or display != current or
            [current['width'], current['height']] != native):
        raise ValueError('device display changed or was unverified; recapture before tapping')
    return tuple(min(native[i] - 1, ((2 * point[i] + 1) * native[i]) // (2 * image_size[i]))
                 for i in range(2)), tuple(native)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True, help='current TCL ADB serial')
    parser.add_argument('--screenshot', required=True, help='fresh, inspected JPEG')
    parser.add_argument('--bounds', required=True, type=int, nargs=4,
                        metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'),
                        help='button rectangle in JPEG pixels; right/bottom exclusive')
    parser.add_argument('--dry-run', action='store_true', help='validate and choose a point without tapping')
    args = parser.parse_args()
    try:
        size = screenshot_size(args.screenshot)
        validate_tablet(args.serial)
        image_point = choose_point(args.bounds, size)
        point, native_size = map_to_device(image_point, size, args.screenshot, args.serial)
        if not args.dry_run:
            subprocess.run(['/usr/bin/adb', '-s', args.serial, 'shell', 'input', 'tap',
                            str(point[0]), str(point[1])], check=True, timeout=15)
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f'no tap: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({'x': point[0], 'y': point[1], 'bounds': args.bounds,
                      'image_point': image_point, 'screenshot_size': size,
                      'native_size': native_size, 'tapped': not args.dry_run}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
