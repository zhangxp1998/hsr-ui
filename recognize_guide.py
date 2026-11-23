"""Original-Sprite guide anchors; images are supplied locally, not distributed."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from paths import HUD, GUIDE

cv2.setNumThreads(4)
LABELS = [('training', '每日实训', 'DailyQuestPracticeIcon'),
          ('survival', '生存索引', 'DailyQuestExploreIcon'),
          ('cosmic', '旷宇纷争', 'DailyQuestRogueAndGridFightIcon'),
          ('challenge', '逐光捡金', 'DailyQuestChallengeStoryIcon'),
          ('story', '开拓历程', 'DailyQuestMainStoryIcon')]


def feature(im):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    return gray - cv2.GaussianBlur(gray, (0, 0), 3.)


def catalog():
    sources = {x['name']: x for x in json.loads((GUIDE / 'asset-provenance.json').read_text())}
    records = [dict(id=i, label=l, asset_name=n,
                    template=str(GUIDE / sources[n]['image']), provenance=sources[n],
                    roi=[0, .12, 1, .28], heights=[52, 90], role='main_tab',
                    allow_inversion=True) for i, l, n in LABELS]
    common = json.loads((HUD / 'common-discovery-index.json').read_text())
    close = next(x for x in common['assets'] if x['name'] == 'CommonCloseIcon@3x')
    records.append(dict(id='close', label='关闭', asset_name=close['name'],
                        template=str(HUD / close['image']), provenance=close,
                        roi=[0, 0, 1, .14], heights=[40, 88], role='page_anchor',
                        allow_inversion=False))
    for record in records:
        path = Path(record['template'])
        if not path.is_file():
            raise ValueError('missing_local_asset: ' + record['asset_name'] + '; see docs/assets.md')
        record['template_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return records
