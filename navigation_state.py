"""Map navigation candidates and measured field HP; no hidden game-state claims."""
import cv2
import numpy as np
import re
from cavern_state import aligned_box, clean, evidence


def read_map(v,im,close):
    s=im.shape[0]/1440;box=lambda b:aligned_box(b,close,s)
    labels=v.ocr(im,box([1500,290,2160,1380]),'map.panel',min_height=20,max_height=80)
    actions=v.ocr(im,box([1540,1190,2160,1380]),'map.actions',min_height=20,max_height=75)
    header=v.ocr(im,box([1585,195,2130,290]),'map.selected-name',min_height=20,max_height=70)
    texts=[q['name'] for q in labels]
    # A marker is only a candidate until the selected point's own type confirms it.
    anchor_type=next((q for q in labels if clean(q['name']) in ['界域定锚','空间锚点']),None)
    teleport=next((q for q in actions if clean(q['name'])=='传送'),None)
    anchor_icon=v.sprites.match('IconMapMazePortal',box([1485,190,1605,305]),(70,90),threshold=.92) if teleport else None
    anchor_confirmed=bool(anchor_type or (anchor_icon and anchor_icon['accepted']))
    nodes=[];markers=[]
    if teleport:
        nodes.append(v.node('map/teleport','传送',bounds=teleport['bounds'],source='roi_ocr',
                            effect='navigation' if anchor_confirmed else 'unverified_destination',
                            target_kind='space_anchor' if anchor_confirmed else None,ocr_score=teleport['score']))
    else:
        # Measure blue components on the map canvas, excluding the side panel/HUD.
        hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
        mask=((hsv[:,:,0]>=80)&(hsv[:,:,0]<=112)&(hsv[:,:,1]>120)&(hsv[:,:,2]>150)).astype(np.uint8)
        region=np.zeros_like(mask)
        l,t,r,b=[round(x*s) for x in box([140,285,1480,1260])];region[t:b,l:r]=1
        mask=cv2.morphologyEx(mask*region,cv2.MORPH_CLOSE,np.ones((max(1,round(3*s)),)*2,np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        for x,y,w,h,area in sorted(stats[1:],key=lambda a:(a[0],a[1])):
            if not (20*s<=w<=78*s and 25*s<=h<=86*s and area>95*s*s and .4<w/h<1.8):continue
            bounds=list(map(int,[x,y,x+w,y+h]));key='map/blue-marker/'+str(len(markers)+1)
            markers.append(dict(key=key,bounds=bounds,kind=None,source='pixel_geometry'))
            nodes.append(v.node(key,'蓝色地图标记 '+str(len(markers)),'button',bounds,'pixel_geometry',True,effect='navigation',
                                semantic_status='candidate_verify_selected_point_type'))
        for i,q in enumerate(labels):
            if q['score']>=.90 and 2<=len(clean(q['name']))<=12:
                nodes.append(v.node('map/region/'+q['name'],q['name'],'button',q['bounds'],'roi_ocr',True,effect='navigation',ocr_score=q['score']))
    return dict(map=dict(visible_panel_text=texts,blue_markers=markers,
                         selected_point_type='space_anchor' if anchor_confirmed else None,
                         selected_point_type_evidence=evidence(anchor_type) if anchor_type else (anchor_icon if anchor_confirmed else None),
                         selected_point_name=' / '.join(q['name'] for q in header) or None,teleport_visible=teleport is not None)),nodes


def read_field(v,im):
    # Reuse the verified exploration-HUD frame/fill method from the existing
    # hsr-party-hud prototype; the source Sprite was NOT proven to be this bar.
    s=im.shape[0]/1440
    normalized=cv2.resize(im,(round(im.shape[1]/s),1440),interpolation=cv2.INTER_AREA) if s!=1 else im
    h,w=normalized.shape[:2]
    dark=(np.max(normalized,axis=2)<65).astype(np.uint8)*255
    region=np.zeros_like(dark);region[round(h*.18):round(h*.65),round(w*.72):]=255
    opened=cv2.morphologyEx(cv2.bitwise_and(dark,region),cv2.MORPH_OPEN,np.ones((1,80),np.uint8))
    _,_,stats,_=cv2.connectedComponentsWithStats(opened)
    lines=sorted([tuple(map(int,a[:4])) for a in stats[1:] if 100<a[2]<220 and a[3]<=13],key=lambda a:(a[1],a[0]))
    pairs=[a for a in lines if 5<=a[3]<=10]
    for x,y,width,height in lines:
        for bx,by,bw,bh in lines:
            if height<=4 and bh<=4 and 4<=by-y<=9 and abs(x-bx)<=2 and abs(width-bw)<=3:
                pairs.append((x,y,width,by+bh-y))
    coherent=[p for p in set(pairs) if sum(abs(p[0]-q[0])<=3 and abs(p[2]-q[2])<=3 and abs(p[1]-q[1])>30 for q in set(pairs))>=1]
    bars=[]
    for p in sorted(coherent,key=lambda p:p[1]):
        if not bars or p[1]-bars[-1][1]>20:bars.append(p)
    if len(bars)>4:bars=[]
    # Scenery can connect a dark frame to its surroundings. Probe missing rows
    # in an already observed repeated layout, requiring both border and cyan fill.
    if 2<=len(bars)<4:
        gaps=[b[1]-a[1] for a,b in zip(bars,bars[1:]) if 110<=b[1]-a[1]<=155]
        if gaps:
            gap=round(float(np.median(gaps)));x=round(float(np.median([p[0] for p in bars])))
            width=max(p[2] for p in bars);height=round(float(np.median([p[3] for p in bars])))
            first=bars[0][1]
            for y in range(first,round(h*.65),gap):
                if any(abs(y-p[1])<5 for p in bars):continue
                patch=normalized[y:y+height,x:x+width].astype(float)
                if patch.shape[:2]!=(height,width):continue
                b,g,r=[patch[:,:,c] for c in range(3)]
                cyan=(b>130)&(g>130)&(b-r>8)&(g-r>8)
                borders=(np.mean(np.max(patch[0],axis=1)<85)>.75 and np.mean(np.max(patch[-1],axis=1)<85)>.75)
                if borders and np.mean(cyan[1:-1])>.08:bars.append((x,y,width,height))
            bars.sort(key=lambda p:p[1])
            if len(bars)>4:bars=[]
    if bars:
        widths=[p[2] for p in bars]
        shared=max(dict.fromkeys(widths),key=widths.count)
        bars=[(x,y,shared if abs(width-shared)<=3 else width,height) for x,y,width,height in bars]
    slots=[];nodes=[]
    for i,(x,y,width,height) in enumerate(bars,1):
        left,top,right,bottom=x+1,y+1,x+width-1,y+height-1
        patch=normalized[top:bottom,left:right].astype(float)
        b,g,r=[patch[:,:,c] for c in range(3)]
        cyan=(b>130)&(g>130)&(b-r>8)&(g-r>8)
        # Live bars also have a white highlight at their filled left edge.
        fill_color=cyan|(np.min(patch,axis=2)>200)
        filled=np.mean(fill_color,axis=0)>=.4;indices=np.flatnonzero(filled);end=0
        if len(indices) and indices[0]<=3:
            gap=0
            for col in range(int(indices[0]),len(filled)):
                if filled[col]:end=col+1;gap=0
                else:
                    gap+=1
                    if gap>2:break
        full=(len(filled)-end)<=2
        name_lines=v.recognize_line(im,[x+25,y-62,x+160,y-6],'field.party-name.'+str(i))
        name=name_lines[0]['name'] if len(name_lines)==1 else None
        bounds=[round(a*s) for a in [x,y,x+width,y+height]]
        item=dict(slot=i,name=name,name_evidence=evidence(name_lines[0]) if name_lines else None,
                  hp_bounds=bounds,hp_fill_fraction_visual=round(end/len(filled),3),visually_full=full,
                  full_tolerance_pixels=2,exact_hp=None,source='pixel_geometry')
        slots.append(item)
        nodes.append(v.node('party/slot/'+str(i),(name or '角色 '+str(i))+' HP','status',bounds,'pixel_geometry',False,
                            hp_fill_fraction_visual=item['hp_fill_fraction_visual'],visually_full=full))
    return dict(party=dict(visible_slots=len(slots),slots=slots,
                          all_four_visually_full=all(q['visually_full'] for q in slots) if len(slots)==4 else None),uid=read_uid(v,im)),nodes


def read_uid(v,im):
    """Read the visible account label; never infer identity from a prior frame.

    The same label remains visible under the monthly-supply overlay. Keeping
    this read separate lets a caller verify identity before claiming that overlay.
    Only already-recognized field/supply pages call this bounded reader.
    """
    lines=v.recognize_line(im,[45,1375,340,1435],'account.uid')
    if len(lines)!=1 or lines[0].get('score',0)<.95:return None
    match=re.fullmatch(r'UID[:：·.]?(\d{9})',clean(lines[0]['name']))
    return match.group(1) if match else None


def read_team(v,im,close):
    s=im.shape[0]/1440;box=lambda b:aligned_box(b,close,s)
    # Sparse, low-contrast numeral tabs need recognition-only crops, not detection.
    tabs=[]
    for i,cx in enumerate([650,808,981,1153,1326,1498],1):
        tabs+=v.recognize_line(im,box([cx-45,40,cx+45,115]),'team.preset.'+str(i))
    footer=v.ocr(im,box([1080,1250,2120,1365]),'team.footer',min_height=20,max_height=65)
    active=True if any(clean(q['name'])=='已启用' for q in footer) else False if any(clean(q['name'])=='启用队伍' for q in footer) else None
    start=next((q for q in footer if clean(q['name'])=='开始挑战' and q['score']>=.90),None)
    nodes=[];selected=[];presets=[]
    for q in tabs:
        if not re.fullmatch(r'0?[1-9]|10',clean(q['name'])):continue
        x0,y0,x1,y1=q['bounds'];cx=(x0+x1)/2
        by=round(box([0,0,0,142])[3]*s)
        l=max(0,round(cx-65*s));r=min(im.shape[1],round(cx+65*s))
        patch=im[max(0,by-round(10*s)):min(im.shape[0],by+round(5*s)),l:r]
        white=(np.min(patch,axis=2)>210) if patch.size else np.zeros((1,1),bool)
        checked=bool(np.any(np.mean(white,axis=1)>.7))
        number=int(clean(q['name']));presets.append(dict(number=number,selected=checked))
        if checked:selected.append(number)
        nodes.append(v.node('team/preset/'+str(number),'队伍 '+str(number),'tab',q['bounds'],'roi_ocr',True,
                            selected=checked,effect='configuration',ocr_score=q['score']))
    names=[]
    for i,b in enumerate([[230,925,450,1000],[700,1000,915,1080],[1280,945,1485,1020],[1690,985,1900,1060]],1):
        lines=v.recognize_line(im,box(b),'team.member.'+str(i))
        line=next((q for q in lines if not re.search(r'\d|毁灭|虚无|丰饶|巡猎|存护|同谐|智识|记忆|欢愉',q['name'])),None)
        if line is None:
            lines=v.ocr(im,box(b),'team.member-detection.'+str(i),min_height=24,max_height=65)
            line=next((q for q in lines if not re.search(r'\d|毁灭|虚无|丰饶|巡猎|存护|同谐|智识|记忆|欢愉',q['name'])),None)
        names.append(dict(slot=i,name=line['name'] if line else None,evidence=evidence(line)))
    # This footer variant is the challenge-entry team screen, not the regular
    # preset editor. Require the visible label and a complete observed party.
    if start and len(selected)==1 and all(q['name'] for q in names):
        nodes.append(v.node('team/start-challenge','开始挑战',bounds=start['bounds'],source='roi_ocr',
                            effect='challenge_resource_use',ocr_score=start['score']))
    return dict(team=dict(selected_preset=selected[0] if len(selected)==1 else None,
                          selected_preset_active=active,presets=presets,members=names)),nodes
