"""Bounded daily-state readers. Unknown visuals are not false/disabled defaults."""
import re
import cv2
import numpy as np
from cavern_state import aligned_box, clean, evidence, unique_match


def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n.get('children',[]))


def roi(im, bounds):
    l,t,r,b=[round(x) for x in bounds]
    if not (0<=l<r<=im.shape[1] and 0<=t<b<=im.shape[0]):return None
    return im[t:b,l:r]


def button_palette(im, bounds, scale):
    l,t,r,b=bounds
    patch=roi(im,[l-24*scale,t-12*scale,r+24*scale,b+12*scale])
    if patch is None:return dict(enabled=None,reason='clipped')
    hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
    gold=float(np.mean((hsv[:,:,0]>12)&(hsv[:,:,0]<42)&(hsv[:,:,1]>90)&(hsv[:,:,2]>170)))
    # Gold reward pills are enabled. Gray alone is not universally a disabled style.
    return dict(enabled=True if gold>.35 else None,gold_fraction=round(gold,3),source='pixel_palette')


def notification(im,bounds,scale):
    l,t,r,b=bounds
    patch=roi(im,[l,t-25*scale,r+35*scale,b])
    if patch is None:return None
    hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
    red=(((hsv[:,:,0]<10)|(hsv[:,:,0]>170))&(hsv[:,:,1]>150)&(hsv[:,:,2]>170)).astype(np.uint8)
    _,_,stats,_=cv2.connectedComponentsWithStats(red)
    return bool(any(a>60*scale*scale and 9*scale<w<45*scale and 9*scale<h<45*scale for x,y,w,h,a in stats[1:]))


def tick_geometry(im,cx,cy,s):
    """Two opposing strokes inside a gold milestone circle; not circle/color alone."""
    bounds=[round(cx-29*s),round(cy-25*s),round(cx+34*s),round(cy+29*s)]
    patch=roi(im,bounds)
    if patch is None:return dict(claimed=None,bounds=bounds,reason='clipped')
    hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
    mask=(((hsv[:,:,0]>10)&(hsv[:,:,0]<38)&(hsv[:,:,1]>100)&(hsv[:,:,2]>140))*255).astype(np.uint8)
    lines=cv2.HoughLinesP(mask,1,np.pi/180,threshold=max(6,round(8*s)),minLineLength=max(6,round(9*s)),maxLineGap=max(1,round(3*s)))
    positive=[];negative=[]
    for x0,y0,x1,y1 in ([] if lines is None else lines.reshape(-1,4)):
        if x1<x0:x0,x1,y0,y1=x1,x0,y1,y0
        dx=x1-x0;dy=y1-y0
        if dx<6*s:continue
        slope=dy/dx
        # Exclude outer circular arcs by requiring the join in the central lower area.
        if .40<slope<1.45 and dx>=15*s and x0<16*s and y0<31*s and x1<43*s and y1>23*s:positive.append([x0,y0,x1,y1])
        if -1.65<slope<-.40 and dx>=25*s and x0<43*s and y0>23*s and y1<16*s:negative.append([x0,y0,x1,y1])
    pair=next(((a,b) for a in positive for b in negative if abs(a[2]-b[0])<15*s and abs(a[3]-b[1])<12*s),None)
    return dict(claimed=True if pair else None,bounds=bounds,source='pixel_geometry',
                method='two_stroke_gold_tick_inside_milestone',stroke_pair=[list(map(int,q)) for q in pair] if pair else [])


def training_state(v,im,close,detail):
    s=im.shape[0]/1440;box=lambda b:aligned_box(b,close,s)
    activity_lines=v.recognize_line(im,box([245,452,345,520]),'training.activity')
    aq,am=unique_match(activity_lines,r'(\d{1,4})')
    activity=int(am.group(1)) if am else None
    milestone_lines=v.ocr(im,box([610,450,2040,530]),'training.milestones',min_height=18,max_height=65)
    milestones=[];nodes=[]
    if aq:nodes.append(v.node('training/activity','活跃度 '+str(activity),'text',aq['bounds'],aq['source'],False,value=activity,ocr_score=aq['score']))
    for amount in [100,200,300,400,500]:
        q,m=unique_match(milestone_lines,str(amount))
        item=dict(activity=amount,claimed=None,unlocked=activity>=amount if activity is not None else None,
                  claimable=None,evidence=evidence(q))
        if q:
            cx=(q['bounds'][0]+q['bounds'][2])/2;cy=q['bounds'][1]-38*s
            tick=tick_geometry(im,cx,cy,s);item.update(claimed=tick['claimed'],tick_evidence=tick)
            badge=notification(im,tick['bounds'],s)
            item['claimable']=(True if badge and item['unlocked'] and tick['claimed'] is not True
                               else False if tick['claimed'] is True or item['unlocked'] is False
                               else None)
            nodes.append(v.node('training/milestone/'+str(amount),str(amount)+' 活跃度奖励','status',tick['bounds'],'pixel_geometry',False,
                                claimed=tick['claimed'],unlocked=item['unlocked'],notification=badge,evidence=tick))
            if item['claimable']:
                nodes.append(v.node('training/milestone/'+str(amount)+'/claim','领取 '+str(amount)+' 活跃度奖励',
                                    bounds=tick['bounds'],source='pixel_geometry',effect='claim',
                                    enabled=True,notification=True))
        milestones.append(item)
    # Card actions may all say 领取. Bind each to its visible task title and
    # horizontal card slot, never to OCR's unstable output order.
    lines=v.ocr(im,box([210,535,1930,825]),'training.task_names',min_height=20,max_height=65) if detail=='content' else []
    title_top,title_bottom=box([0,625,0,770])[1]*s,box([0,625,0,770])[3]*s
    titles=([q for q in lines if title_top <= (q['bounds'][1]+q['bounds'][3])/2 <= title_bottom]
            if lines else v.ocr(im,box([210,625,1930,770]),'training.task_titles',min_height=20,max_height=65))
    statuses=v.ocr(im,box([210,1030,1930,1185]),'training.task_actions',min_height=20,max_height=70)
    task_nodes=v.text_nodes(lines,'training/task-text')
    actionable=sorted((q for q in statuses if q['name'] in ['前往','领取']),
                      key=lambda q:(q['bounds'][0]+q['bounds'][2])/2)
    for slot,q in enumerate(actionable,1):
        center=(q['bounds'][0]+q['bounds'][2])/2
        context=sorted((x for x in titles if abs((x['bounds'][0]+x['bounds'][2])/2-center)<210*s),
                       key=lambda x:(x['bounds'][1],x['bounds'][0]))
        title=''.join(x['name'] for x in context) or '未识别任务'
        if not context:continue
        key='task/'+str(slot)+'-'+clean(title)
        action=v.node(key+'/'+q['name'],q['name'],bounds=q['bounds'],source=q['source'],
                      effect='claim' if q['name']=='领取' else 'navigation',ocr_score=q['score'])
        task_nodes.append(v.group(key,title,[action]))
    task_nodes+=v.text_nodes([q for q in statuses if q['name'] not in ['前往','领取']],
                             'training/task-status')
    nodes.append(v.group('tasks','每日实训任务',task_nodes))
    claimed=True if all(x['claimed'] is True for x in milestones) else None
    return dict(activity=activity,activity_evidence=evidence(aq),milestones=milestones,
                all_milestones_claimed=claimed,activity_full=activity>=500 if activity is not None else None,
                visible_claim_buttons=sum(q['name']=='领取' for q in actionable)),nodes


def commissions_state(v,im,close,children):
    s=im.shape[0]/1440;box=lambda b:aligned_box(b,close,s)
    footer=v.ocr(im,box([165,1020,1370,1130]),'commissions.summary',min_height=18,max_height=75)
    fq,fm=unique_match(footer,r'(\d+)/(\d+)')
    has_label=any(clean(q['name'])=='进行中的委托' for q in footer)
    running=int(fm.group(1)) if fm and has_label else None
    capacity=int(fm.group(2)) if fm and has_label else None
    hours=v.ocr(im,box([1400,830,2100,940]),'commissions.elapsed',min_height=18,max_height=70)
    hq,hm=unique_match(hours,r'已进行[:：]?(\d+)/(\d+)小时')
    elapsed=int(hm.group(1)) if hm else None
    duration=int(hm.group(2)) if hm else None
    reward=None;palette=None
    for n in walk(children):
        if n.get('name') in ['领取奖励','一键领取','再次派遣'] and n.get('actions'):
            n['effect']='claim' if n['name']!='再次派遣' else 'dispatch'
            if n['name']=='领取奖励':
                palette=button_palette(im,n['bounds'],s)
                reward=palette['enabled']
                # Calibrated no-accrual state needs an observed zero, not running alone.
                if reward is None and elapsed==0:reward=False
                n.update(enabled=reward,enabled_evidence=palette)
        if n.get('key','').startswith('tabs/') and n.get('actions'):n['effect']='navigation'
    nodes=[]
    if fq and running is not None:nodes.append(v.node('commissions/running','进行中的委托 '+str(running)+'/'+str(capacity),'status',fq['bounds'],'roi_ocr',False,value=running,capacity=capacity,ocr_score=fq['score']))
    if hq:nodes.append(v.node('commissions/elapsed',hq['name'],'text',hq['bounds'],'roi_ocr',False,value=elapsed,maximum=duration,ocr_score=hq['score']))
    return dict(running_count=running,capacity=capacity,elapsed_hours=elapsed,duration_hours=duration,
                accumulated_rewards_claimable=reward,evidence=dict(running=evidence(fq),elapsed=evidence(hq),reward_button=palette)),nodes


def honor_state(v,im,close,children,page):
    s=im.shape[0]/1440;tabs={}
    for n in walk(children):
        if n.get('key') in ['main/rewards','main/tasks']:
            n['notification']=notification(im,n['bounds'],s);tabs[n['key']]=n['notification']
        if page=='honor.rewards' and n.get('actions') and n.get('name')=='一键领取':n['effect']='claim_level_rewards'
        if n.get('actions') and '解锁无名客' in n.get('name',''):n['effect']='purchase'
    nodes=[]
    actions=v.ocr(im,aligned_box([1280,1170,2140,1360],close,s),'honor.claim_all',min_height=20,max_height=70) if page=='honor.tasks' else []
    if page=='honor.tasks' and not any(q['name']=='一键领取' for q in actions):
        actions+=v.recognize_line(im,aligned_box([1805,1230,1945,1288],close,s),'honor.claim-all-line')
    for q in actions:
        if q['name']=='一键领取':
            nodes.append(v.node('honor/tasks/claim-all',q['name'],bounds=q['bounds'],source='roi_ocr',effect='claim',ocr_score=q['score']))
    visible_claims=sum(n.get('name')=='领取' and bool(n.get('actions')) for n in walk(children))
    return dict(page_scope='task_xp' if page=='honor.tasks' else 'level_rewards_not_daily_authorized',
                task_notification=tabs.get('main/tasks'),level_reward_notification=tabs.get('main/rewards'),
                claim_all_visible=bool(nodes) if page=='honor.tasks' else None,
                visible_task_claim_buttons=visible_claims if page=='honor.tasks' else None),nodes


def cavern_controls(v,im,close,children,state):
    s=im.shape[0]/1440;box=lambda b:aligned_box(b,close,s);challenge=state['challenge']
    title=[n for n in walk(children) if n.get('key','').startswith('title/')]
    selected=None
    for n in title:
        m=re.fullmatch(r'难度([IV]+)',clean(n['name']))
        if m:selected=m.group(1)
    challenge['selected_difficulty']=selected
    for n in walk(children):
        if n.get('key','').startswith('difficulty/') and n.get('actions'):
            n.update(key='difficulty/'+clean(n['name']),role='tab',selected=clean(n['name'])==selected if selected else None,effect='configuration')
    nodes=[];count=challenge['selected_count'];maximum=challenge['visible_max_count']
    plus=v.sprites.match('IconAdd',box([2020,1130,2150,1210]),(14,50),invert=True,threshold=.85)
    if count is not None and maximum is not None:
        if plus and plus['accepted']:
            nodes.append(v.sprite_node('challenge-settings/increase','增加次数',plus,effect='configuration',enabled=count<maximum))
        # The decrement remains usable when the increment is dimmed at maximum.
        # A close-aligned bounded ROI only proposes geometry; require the visible stroke.
        bb=[round(x*s) for x in box([1432,1161,1478,1188])]
        patch=roi(im,bb)
        if patch is not None:
            gray=cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY)
            baseline=float(np.median(np.concatenate([gray[0],gray[-1],gray[:,0],gray[:,-1]])))
            mask=(np.abs(gray.astype(float)-baseline)>35).astype(np.uint8)
            _,_,stats,_=cv2.connectedComponentsWithStats(mask)
            hits=[(x,y,w,h) for x,y,w,h,a in stats[1:] if 16*s<w<38*s and 1*s<h<8*s and w/h>3 and a/(w*h)>.65]
            if len(hits)==1:
                x,y,w,h=map(int,hits[0]);bounds=[bb[0]+x,bb[1]+y,bb[0]+x+w,bb[1]+y+h]
                nodes.append(v.node('challenge-settings/decrease','减少次数',bounds=bb,source='pixel_geometry',effect='configuration',enabled=count>1,glyph_bounds=bounds))
    for n in walk(children):
        if n.get('key')=='challenge-settings/auto-refill' and n.get('checked') is not None:
            n.update(actions=['click'],enabled=True,effect='configuration',source='pixel_geometry')
    return nodes


def enrich(v,im,page,children,close,detail,state):
    extra=[]
    if page=='guide.training':
        data,extra=training_state(v,im,close,detail);state=dict(training=data)
    elif page=='commissions':
        data,extra=commissions_state(v,im,close,children);state=dict(commissions=data)
    elif page.startswith('honor.'):
        data,extra=honor_state(v,im,close,children,page);state=dict(honor=data)
    elif page in ('cavern','echo') and state:
        extra=cavern_controls(v,im,close,children,state)
    children.extend(extra)
    return state
