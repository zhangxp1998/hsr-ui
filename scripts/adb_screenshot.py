#!/usr/bin/env python3
"""Capture an ADB screen as a full-resolution JPEG Q75.

The PNG from adb stays in memory.  Capture metadata is embedded in the JPEG
so clients can safely convert image coordinates back to device coordinates.
"""

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from PIL import Image


SCHEMA = 'adb-screenshot-v1'
JPEG_QUALITY = 75


def adb(serial, *args, timeout=30):
    command = ['adb']
    if serial:
        command += ['-s', serial]
    command += list(args)
    return subprocess.run(command, check=True, capture_output=True, timeout=timeout).stdout


def display_state(serial):
    """Return the active Android default display's rotation and logical size."""
    output = adb(serial, 'shell', 'dumpsys', 'display').decode('utf-8', 'replace')
    matches = []
    for body in re.findall(r'DisplayViewport\{([^}]+)\}', output):
        if not re.search(r'\bdisplayId=0\b', body) or not re.search(r'\bisActive=true\b', body):
            continue
        rotation = re.search(r'\borientation=(\d+)\b', body)
        frame = re.search(r'\blogicalFrame=Rect\(0,\s*0\s*-\s*(\d+),\s*(\d+)\)', body)
        if rotation and frame:
            matches.append({'rotation': int(rotation.group(1)),
                            'width': int(frame.group(1)), 'height': int(frame.group(2))})
    if len(matches) != 1 or matches[0]['rotation'] not in (0, 1, 2, 3):
        raise ValueError('cannot determine a unique active default display')
    return matches[0]


def optional_display_state(serial):
    try:
        return display_state(serial)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def capture(serial, output):
    output = Path(output)
    if output.suffix.lower() not in ('.jpg', '.jpeg'):
        raise ValueError('output filename must end in .jpg or .jpeg')
    selected = adb(serial, 'get-serialno').decode('utf-8', 'strict').strip()
    if not selected or selected == 'unknown':
        raise ValueError('ADB did not identify a unique device')
    before = optional_display_state(selected)
    png = adb(selected, 'exec-out', 'screencap', '-p', timeout=60)
    after = optional_display_state(selected)
    with Image.open(BytesIO(png)) as source:
        if source.format != 'PNG':
            raise ValueError('adb screencap did not return a PNG')
        source.load()
        native = list(source.size)
        image = source.convert('RGB')
    stable = before if before == after and before is not None and (
        before['width'], before['height']) == tuple(native) else None
    metadata = {'schema': SCHEMA, 'serial': selected, 'native_size': native,
                'display': stable}
    exif = Image.Exif()
    exif[270] = json.dumps(metadata, separators=(',', ':'))
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.' + output.name + '.', suffix='.tmp',
                                         dir=output.parent, delete=False) as temporary:
            temp_name = temporary.name
            image.save(temporary, format='JPEG', quality=JPEG_QUALITY, subsampling=2,
                       optimize=True, progressive=True, exif=exif)
        os.replace(temp_name, output)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
    return {'path': str(output), 'serial': selected, 'native_size': native,
            'image_size': list(image.size), 'jpeg_quality': JPEG_QUALITY,
            'bytes': output.stat().st_size, 'display_verified': stable is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', '-s', help='ADB device serial; omit only with one selected device')
    parser.add_argument('output', help='output JPEG path')
    args = parser.parse_args()
    try:
        print(json.dumps(capture(args.serial, args.output), ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            detail = exc.stderr.decode('utf-8', 'replace').strip()
        else:
            detail = str(exc)
        print(f'capture failed: {detail}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
