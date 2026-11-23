"""Evidence-backed resources and challenge configuration.

Missing/ambiguous evidence stays null. Multi-run costs are interpreted only
under the live-verified cavern batch profile and matching visible totals.
"""
import re
import unicodedata

import cv2
import numpy as np


def aligned_box(box, close, scale):
    cx = (close['bounds'][0] + close['bounds'][2]) / 2 / scale
    cy = (close['bounds'][1] + close['bounds'][3]) / 2 / scale
    return np.array(box, float) + [cx-2118, cy-84, cx-2118, cy-84]


def clean(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


def unique_match(lines, pattern):
    found = []
    for q in lines:
        match = re.fullmatch(pattern, clean(q['name']))
        if match and q.get('score', 0) >= .90:
            found.append((q, match))
    return found[0] if len(found) == 1 else (None, None)


def evidence(q):
    if q is None:
        return None
    return dict(raw_text=q['name'], bounds=[round(v) for v in q['bounds']],
                source=q.get('source','roi_ocr'), score=q['score'])


def read_switch(im, label, scale):
    """Find the actual white knob; do not infer OFF from a missing knob."""
    if label is None:
        return dict(enabled=None, reason='label_missing')
    l, t, r, b = label['bounds']
    cy = (t+b)/2
    bounds = [round(r+5*scale), round(cy-32*scale),
              round(r+115*scale), round(cy+32*scale)]
    x0,y0,x1,y1 = bounds
    if not (0 <= x0 < x1 <= im.shape[1] and 0 <= y0 < y1 <= im.shape[0]):
        return dict(enabled=None, reason='track_outside_image')
    hsv = cv2.cvtColor(im[y0:y1,x0:x1], cv2.COLOR_BGR2HSV)
    mask = ((hsv[:,:,1] < 55) & (hsv[:,:,2] > 215)).astype(np.uint8)
    n, _, stats, centers = cv2.connectedComponentsWithStats(mask)
    candidates = []
    for i in range(1,n):
        x,y,w,h,area = stats[i]
        if (15*scale <= w <= 44*scale and 15*scale <= h <= 44*scale
                and .70 <= w/h <= 1.40 and area/(w*h) > .55):
            candidates.append((stats[i],centers[i]))
    if len(candidates) != 1:
        return dict(enabled=None,bounds=bounds,source='pixel_geometry',reason='knob_missing_or_ambiguous')
    stats, center = candidates[0]
    ratio = float(center[0]/(x1-x0))
    checked = False if .08 <= ratio <= .40 else True if .60 <= ratio <= .95 else None
    x,y,w,h,_ = [int(v) for v in stats]
    return dict(enabled=checked,bounds=bounds,source='pixel_geometry',
                knob_bounds=[x0+x,y0+y,x0+x+w,y0+y+h],knob_position=ratio,
                method='label_anchored_white_knob_left_off_right_on',
                reason='measured_knob' if checked is not None else 'knob_between_states')


def derive_plan(resources, challenge):
    current = resources['trailblaze_power']['current']
    count = challenge['selected_count']
    displayed = challenge['displayed_power_cost']
    # Live 1..6 configuration rehearsal established 40,80,120,160,200,240.
    # Only this page profile and matching visible total enable batch arithmetic.
    profile=challenge.get('cost_profile')
    unit,maximum=(30,3) if profile=='echo_batch_30_v1' else (40,6)
    batch = profile in ('cavern_batch_40_v1','echo_batch_30_v1') and count in range(2,maximum+1) and displayed==unit*count
    per_run = displayed if count == 1 and displayed is not None and displayed > 0 else unit if batch else None
    challenge['power_cost_per_run'] = per_run
    challenge['cost_basis'] = ('validated_echo_batch_total' if unit==30 else 'validated_cavern_batch_total') if batch else 'visible_cost_at_single_run' if per_run is not None else 'unverified'
    ready = current is not None and count is not None and per_run is not None
    affordable = current//per_run if ready else None
    total = count*per_run if ready else None
    limit = challenge['visible_max_count']
    return dict(ready=ready, scope='current_power_only_no_refills',
                affordable_runs_without_refill=affordable,
                max_selectable_affordable_runs=min(affordable,limit) if ready and limit is not None else affordable,
                selected_batch_power_cost=total,
                selected_batch_affordable=total <= current if ready else None,
                power_after_selected_batch=current-total if ready and total <= current else None,
                power_shortfall=max(0,total-current) if ready else None,
                reserve_power_included=False, fuel_or_premium_currency_included=False,
                unknowns=[name for name,value in [('current_power',current),('selected_count',count),
                          ('verified_per_run_cost',per_run)] if value is None])


def read_cavern_state(vision, im, close, cost_lines, page='cavern'):
    s = im.shape[0]/1440
    box = lambda b: aligned_box(b,close,s)
    resource_lines = vision.ocr(im,box([1450,20,2020,130]),'cavern.resources',min_height=16,max_height=70)
    resources = {}
    nodes = []
    for key,name,asset,region,next_x,pattern in [
        ('reserved_trailblaze_power','后备开拓力','combo_widget_hkrpg_icon_backup_stamina',
         [1450,15,1750,130],1740,r'(\d+)'),
        ('trailblaze_power','开拓力','combo_widget_hkrpg_icon_stamina',
         [1710,15,2020,130],2025,r'(\d+)/(\d+)\+?')]:
        icon = vision.sprites.match(asset,box(region),(44,78),threshold=.80)
        candidates = []
        if icon and icon['accepted']:
            left = icon['bounds'][2]-5*s
            right = box([next_x,0,next_x,0])[0]*s
            cy = (icon['bounds'][1]+icon['bounds'][3])/2
            candidates = [q for q in resource_lines if q['bounds'][0]>=left
                          and q['bounds'][2]<=right
                          and abs((q['bounds'][1]+q['bounds'][3])/2-cy)<25*s]
        q,m = unique_match(candidates,pattern)
        current = int(m.group(1)) if m else None
        capacity = int(m.group(2)) if m and key=='trailblaze_power' else None
        if capacity is not None and capacity <= 0:
            q,m,current,capacity = None,None,None,None
        resources[key] = dict(current=current,capacity=capacity,evidence=evidence(q),icon_evidence=icon)
        if q:
            value = f'{current}/{capacity}' if capacity is not None else str(current)
            nodes.append(vision.node('resources/'+key,name+' '+value,'text',q['bounds'],'roi_ocr',False,
                                     value=current,capacity=capacity,ocr_score=q['score'],icon_evidence=icon))
    settings = vision.ocr(im,box([1380,1030,2140,1240]),'cavern.settings',min_height=16,max_height=70)
    cq,cm = unique_match(settings,r'挑战次数(\d+)')
    selected = int(cm.group(1)) if cm and 1 <= int(cm.group(1)) <= 99 else None
    max_candidates = [q for q in settings if q['bounds'][0]/s > box([1940,0,1940,0])[0]
                      and q['bounds'][1]/s > box([0,1140,0,1140])[1]]
    mq,mm = unique_match(max_candidates,r'(\d+)')
    if mq is None:
        # A sparse isolated maximum digit can be missed by the detector.
        maximum_lines=vision.recognize_line(im,box([1980,1150,2030,1200]),'cavern.maximum')
        mq,mm=unique_match(maximum_lines,r'(\d+)')
    maximum = int(mm.group(1)) if mm and 1 <= int(mm.group(1)) <= 99 else None
    if selected is not None and maximum is not None and selected > maximum:
        selected = None
    pq,pm = unique_match(cost_lines,r'[×xX*](\d+)')
    # Keep a leading multiplication sign mandatory; never read a resource icon as a digit.
    displayed = int(pm.group(1)) if pm and int(pm.group(1)) > 0 else None
    sq,sm = unique_match(settings,r'快捷补充开拓力')
    refill = read_switch(im,sq,s)
    challenge = dict(cost_profile='echo_batch_30_v1' if page=='echo' else 'cavern_batch_40_v1',selected_count=selected,visible_max_count=maximum,
                     displayed_power_cost=displayed,
                     auto_refill_enabled=refill['enabled'],
                     evidence=dict(count=evidence(cq),maximum=evidence(mq),cost=evidence(pq),
                                   auto_refill_label=evidence(sq),auto_refill=refill))
    plan = derive_plan(resources,challenge)
    if page=='echo':
        weekly=vision.ocr(im,box([1450,960,2120,1045]),'echo.weekly',min_height=20,max_height=65)
        wq,wm=unique_match(weekly,r'本周[「『]?历战余响[」』]?剩余次数[:：](\d+)/(\d+)')
        if wm is None:
            # After the allowance is exhausted the count/refill controls vanish
            # and the observed weekly-counter bar moves above the challenge button.
            weekly=vision.ocr(im,box([1450,1160,2120,1250]),'echo.weekly-empty',min_height=20,max_height=65)
            wq,wm=unique_match(weekly,r'本周[「『]?历战余响[」』]?剩余次数[:：](\d+)/(\d+)')
        remaining,capacity=(int(wm[1]),int(wm[2])) if wm else (None,None)
        if capacity!=3 or remaining is None or not 0<=remaining<=capacity:remaining,capacity=None,None
        challenge.update(weekly_rewards_remaining=remaining,weekly_rewards_capacity=capacity)
        challenge['weekly_rewards_available']=remaining>0 if remaining is not None else None
        challenge['evidence']['weekly']=evidence(wq)
        plan['selected_batch_within_weekly_allowance']=selected<=remaining if selected is not None and remaining is not None else None
        if remaining is None:plan['unknowns'].append('weekly_rewards_remaining')
        plan['ready']=plan['ready'] and remaining is not None
        if plan['max_selectable_affordable_runs'] is not None and remaining is not None:
            plan['max_selectable_affordable_runs']=min(plan['max_selectable_affordable_runs'],remaining)
    settings_nodes = []
    if cq and selected is not None:
        settings_nodes.append(vision.node('challenge-settings/count','挑战次数 '+str(selected),'spinbutton',
                              cq['bounds'],'roi_ocr',False,value=selected,maximum=maximum,ocr_score=cq['score']))
    if mq and maximum is not None:
        settings_nodes.append(vision.node('challenge-settings/maximum','次数上限 '+str(maximum),'text',
                              mq['bounds'],'roi_ocr',False,value=maximum,ocr_score=mq['score']))
    if pq and displayed is not None:
        settings_nodes.append(vision.node('challenge-settings/cost','显示消耗 '+str(displayed),'text',
                              pq['bounds'],'roi_ocr',False,value=displayed,ocr_score=pq['score']))
    if sq and refill.get('bounds'):
        settings_nodes.append(vision.node('challenge-settings/auto-refill','快捷补充开拓力','switch',
                              refill['bounds'],'observed_layout',False,checked=refill['enabled'],evidence=refill))
    return dict(schema='hsr-cavern-state-v1',resources=resources,challenge=challenge,planning=plan), [
        vision.group('resources','当前资源',nodes),
        vision.group('challenge-settings','挑战设置',settings_nodes)]
