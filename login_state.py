"""Title-screen entry from independent live OCR anchors, never a saved crop."""
from cavern_state import clean, evidence
import numpy as np


def bright_text(im, q):
    l, t, r, b = [round(x) for x in q['bounds']]
    if not (0 <= l < r <= im.shape[1] and 0 <= t < b <= im.shape[0]):
        return False
    return bool(np.mean(np.min(im[t:b, l:r], axis=2) > 180) > .05)


def read_login(v, im):
    start_lines = v.ocr(im, [750, 1030, 1470, 1155], 'login.start',
                        min_height=30, max_height=130)
    start = [q for q in start_lines if clean(q['name']) == '开始游戏' and q['score'] >= .90]
    entry_lines = (v.ocr(im, [800, 1280, 1410, 1390], 'login.entry',
                         min_height=20, max_height=85) if not start else [])
    entry = [q for q in entry_lines if clean(q['name']) == '点击进入' and q['score'] >= .90]
    if len(start) + len(entry) != 1:
        return None
    server_lines = v.ocr(im, [780, 1150, 1420, 1265], 'login.server',
                         min_height=20, max_height=85)
    servers = {'Asia': 'Asia', 'Europe': 'Europe', 'America': 'America',
               'TW,HK,MO': 'TW,HK,MO'}
    server = [q for q in server_lines if clean(q['name']) in servers and q['score'] >= .90]
    rail = v.ocr(im, [1960, 100, 2170, 760], 'login.rail', min_height=20, max_height=85)
    anchors = {clean(q['name']): q for q in rail
               if clean(q['name']) in ('公告', '设置', '登出') and q['score'] >= .90}
    # Do not turn a stray "start" string or an account/verification popup into input.
    if (start and len(server) != 1) or not {'公告', '设置', '登出'} <= anchors.keys():
        return None
    q = (start or entry)[0]
    if not all(bright_text(im, x) for x in [q, *server, *anchors.values()]):
        return None
    return dict(page='login.title' if start else 'login.entry', label=q['name'],
                state=dict(login=dict(server=servers[clean(server[0]['name'])] if len(server) == 1 else None,
                                      start_available=True, uid=None,
                                      account_verification_required=True)),
                nodes=[v.node('login/start' if start else 'login/enter', q['name'], bounds=q['bounds'], source='roi_ocr',
                              effect='enter_game', ocr_score=q['score'])],
                evidence=[evidence(q), *[evidence(x) for x in server], *[evidence(x) for x in anchors.values()]])
