"""Monthly supply overlay: two exact, independent OCR labels gate a claim node."""
import re


def read_supply(v, im):
    title = v.ocr(im, (850, 45, 1350, 155), 'supply.title', min_height=25, max_height=100)
    matched_title = next((q for q in title if q['name'] == '列车补给' and q['score'] >= .9), None)
    if not matched_title:
        return None
    prompt = v.ocr(im, (800, 1200, 1400, 1330), 'supply.claim', min_height=20, max_height=65)
    matched_prompt = next((q for q in prompt if q['name'] == '点击领取今日补给' and q['score'] >= .9), None)
    if not matched_prompt:
        return None
    remaining = v.ocr(im, (850, 155, 1350, 260), 'supply.days', min_height=20, max_height=90)
    if not remaining:
        remaining = v.recognize_line(im, (960, 160, 1250, 220), 'supply.days-line')
    days = None
    for q in remaining:
        match = re.fullmatch(r'剩余[:：]?\s*(\d+)\s*天', q['name'].replace(' ', ''))
        if match and q['score'] >= .9:
            days = int(match[1])
    nodes = v.text_nodes([matched_title, *remaining], 'supply')
    reward=v.ocr(im,(1000,745,1210,900),'supply.reward',min_height=20,max_height=65)
    jade=any(q['name']=='星琼' and q['score']>=.9 for q in reward)
    amount=next((int(q['name']) for q in reward if q['name'].isdigit() and q['score']>=.9),None)
    confirmed=jade and amount==90
    nodes.append(v.node('supply/dismiss' if confirmed else 'supply/claim',
                        '关闭已领取的补给' if confirmed else matched_prompt['name'],bounds=matched_prompt['bounds'],
                        source='roi_ocr', effect='navigation' if confirmed else 'claim', ocr_score=matched_prompt['score']))
    return dict(state={'subscription': {'days_remaining': days, 'daily_claim_available': not confirmed,
                                       'reward_confirmed':confirmed, 'stellar_jade_received':amount if confirmed else None}},
                nodes=nodes, evidence=[dict(source='roi_ocr', title=matched_title, prompt=matched_prompt)])
