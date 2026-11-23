"""Observed post-battle and generic item-reward overlays, with bounded actions."""
import re
from cavern_state import clean, evidence


def read_reward_popup(v,im):
    title=v.ocr(im,[800,180,1400,320],'reward.title',min_height=25,max_height=85)
    heading=next((q for q in title if clean(q['name'])=='获得物品'),None)
    if heading is None:return None
    footer=v.ocr(im,[850,1010,1390,1140],'reward.dismiss',min_height=20,max_height=75)
    dismiss=next((q for q in footer if clean(q['name'])=='点击空白处关闭'),None)
    if dismiss is None:return None
    names=v.ocr(im,[520,805,1680,875],'reward.items',min_height=20,max_height=60)
    counts=v.ocr(im,[520,755,1680,820],'reward.counts',min_height=20,max_height=60)
    items=[]
    for q in names:
        if not re.fullmatch(r'[\u3400-\u9fff·]{2,12}',clean(q['name'])):continue
        cx=(q['bounds'][0]+q['bounds'][2])/2
        amounts=[x for x in counts if re.fullmatch(r'\d+',clean(x['name'])) and
                 abs((x['bounds'][0]+x['bounds'][2])/2-cx)<90*im.shape[0]/1440]
        amount=int(clean(amounts[0]['name'])) if len(amounts)==1 else None
        items.append(dict(name=q['name'],count=amount))
    node=v.node('reward/dismiss','关闭奖励弹窗',bounds=dismiss['bounds'],source='roi_ocr',
                effect='navigation',ocr_score=dismiss['score'])
    return dict(page='reward.popup',label='获得物品',
                state=dict(reward=dict(items=items,visible=True)),nodes=[node],
                evidence=[evidence(heading),evidence(dismiss)])


def read_challenge_result(v,im):
    header=v.ocr(im,[600,200,1550,380],'result.title',min_height=40,max_height=150)
    success=next((q for q in header if clean(q['name'])=='挑战成功'),None)
    if success is None:return None
    footer=v.ocr(im,[450,1200,1800,1380],'result.actions',min_height=20,max_height=85)
    leave=next((q for q in footer if clean(q['name'])=='退出关卡'),None)
    if leave is None:return None
    wave_text=v.ocr(im,[1270,1155,1620,1265],'result.waves',min_height=20,max_height=65)
    waves=next((int(m.group(1)) for q in wave_text
                if (m:=re.search(r'上轮挑战波次[:：]?(\d+)',clean(q['name'])))),None)
    salvage_text=v.ocr(im,[650,900,1550,1010],'result.salvage',min_height=20,max_height=70)
    salvage=next((int(m.group(1)) for q in salvage_text
                  if (m:=re.search(r'遗失碎金[×xX](\d+)',clean(q['name'])))),None)
    node=v.node('result/exit','退出关卡',bounds=leave['bounds'],source='roi_ocr',
                effect='navigation',ocr_score=leave['score'])
    return dict(page='battle.result',label='挑战成功',
                state=dict(result=dict(success=True,last_round_waves=waves,salvaged_lost_gold=salvage)),
                nodes=[node],evidence=[evidence(success),evidence(leave)])
