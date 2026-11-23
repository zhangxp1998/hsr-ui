"""Bounded, original-Sprite battle HUD profile; no screenshot templates.

The visible pause glyph AND explicit turn text gate battle.active. The auto
control additionally needs its own glyph and positive gold foreground evidence.
Only ON has real replay coverage. White/gray/disabled/missing stays unknown and
has no toggle until an independently verified OFF fixture is available.
"""
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from cavern_state import clean, evidence


@lru_cache(maxsize=4)
def _alpha(path):
    # The regular asset loader has already verified recipe + exact RGBA hashes.
    with Image.open(path) as image:
        return np.array(image.convert('RGBA'))[:, :, 3]


def _auto_color(v, im, match):
    """Measure positive color on original glyph interior, not its background."""
    if not match or not match['accepted']:
        return dict(enabled=None, reason='auto_sprite_missing_or_ambiguous')
    l,t,r,b = match['bounds']
    if not (0 <= l < r <= im.shape[1] and 0 <= t < b <= im.shape[0]):
        return dict(enabled=None, reason='auto_bounds_outside_image')
    alpha = cv2.resize(_alpha(v.sprites.assets['IconAuto']['path']), (r-l,b-t),
                       interpolation=cv2.INTER_LINEAR)
    # Avoid antialiasing, the dynamic backdrop, and glow outside the glyph.
    interior = cv2.erode((alpha > 220).astype(np.uint8), np.ones((3,3), np.uint8)) > 0
    pixels = cv2.cvtColor(im[t:b,l:r], cv2.COLOR_BGR2HSV)[interior]
    if len(pixels) < 12:
        return dict(enabled=None, reason='insufficient_original_glyph_interior',
                    foreground_samples=len(pixels))
    gold = ((pixels[:,0] >= 15) & (pixels[:,0] <= 40) &
            (pixels[:,1] >= 40) & (pixels[:,2] >= 180))
    white = (pixels[:,1] <= 25) & (pixels[:,2] >= 205)
    gold_fraction,white_fraction = float(gold.mean()),float(white.mean())
    enabled = True if gold_fraction >= .75 and white_fraction <= .05 else None
    return dict(enabled=enabled, reason='positive_gold_foreground' if enabled is True
                else 'off_or_disabled_state_not_live_verified',
                source='original_sprite_foreground_color',
                foreground_samples=len(pixels), gold_fraction=gold_fraction,
                white_fraction=white_fraction)


def read_battle(v, im):
    s = im.shape[0]/1440
    if abs(im.shape[1]/im.shape[0] - 2200/1440) > .02:
        return None
    pause = v.sprites.match('IconBattlePause', [2050,20,2190,125], (20,42), threshold=.88)
    if not pause or not pause['accepted']:
        return None
    lines = v.ocr(im, [1800,1250,2160,1380], 'battle.turn', min_height=20, max_height=80)
    turns = [q for q in lines if clean(q['name']) in ('我方行动中','敌方行动中')
             and q.get('score',0) >= .95]
    if len(turns) != 1:
        return None
    turn = turns[0]
    auto = v.sprites.match('IconAuto', [1900,20,2040,125], (20,42), threshold=.80)
    color = _auto_color(v,im,auto)
    # Same-row, expected-order relation is observed from the live frames. Native
    # prefab layout is provenance, not a substitute for measured screen bounds.
    if auto and auto['accepted']:
        ax,ay = (np.array(auto['bounds'][:2])+auto['bounds'][2:])/2
        px,py = (np.array(pause['bounds'][:2])+pause['bounds'][2:])/2
        if not (100*s <= px-ax <= 200*s and abs(py-ay) <= 8*s):
            color = dict(enabled=None,reason='hud_geometry_mismatch')
    enabled = color['enabled']
    nodes = []
    if enabled is not None:
        nodes.append(v.node('battle/auto','自动战斗','switch',auto['bounds'],
                     'original_sprite',True,effect='configuration',enabled=True,
                     checked=enabled,evidence=dict(icon=auto,color=color)))
    battle = dict(active=True,phase='ally_turn' if clean(turn['name'])=='我方行动中'
                  else 'enemy_turn',auto_enabled=enabled,
                  auto_reason=color['reason'],auto_evidence=dict(icon=auto,color=color))
    return dict(page='battle.active',label='战斗中',
                state=dict(schema='hsr-battle-state-v1',battle=battle),nodes=nodes,
                evidence=[pause,evidence(turn)])
