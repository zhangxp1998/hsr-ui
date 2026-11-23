"""Echo-of-War navigation. Candidates never imply a material's identity or stock."""
import re
import cv2
import numpy as np
from cavern_state import clean,evidence


def read_unlock_prompt(v,im):
    lines=v.ocr(im,[590,480,1610,735],'echo.unlock.body',min_height=22,max_height=85)
    title=next((q for q in lines if clean(q['name'])=='提示' and q['score']>=.9),None)
    body=next((q for q in lines if clean(q['name'])=='提前解锁并挑战历战余响可能会影响剧情体验,是否继续?' and q['score']>=.9),None)
    if not title or not body:return None
    footer=v.ocr(im,[700,850,1550,960],'echo.unlock.buttons',min_height=22,max_height=70)
    nodes=[]
    for name,key,effect in [('取消','cancel','navigation'),('确认','confirm','early_unlock')]:
        q=next((q for q in footer if q['name']==name and q['score']>=.9),None)
        if q:nodes.append(v.node('echo/unlock/'+key,name,bounds=q['bounds'],source='roi_ocr',effect=effect))
    return dict(page='echo.unlock',label='历战余响提前解锁确认',
                state=dict(early_unlock=dict(story_order_warning=True)),nodes=nodes,
                evidence=[evidence(title),evidence(body)])


def guide_weekly_nodes(v,im,children,layout):
    s=im.shape[0]/1440;extra=[]
    # These panels are established by the five-Sprite guide layout gate.
    for key,name,box in [('categories','指南类别',layout['subtab_roi']),
                         ('entries','副本列表',np.array([780,400,2000,1160])*s)]:
        if box is None:continue
        for direction,word in [('up','上'),('down','下')]:
            n=v.node('guide/scroll/'+key+'/'+direction,name+'向'+word+'滚动',
                     'scrollbar',box,'observed_layout',False,effect='navigation',scroll_direction=direction)
            n['actions']=['scroll'];extra.append(n)
    sub=next((n for g in children for n in g.get('children',[])
              if n.get('key')=='sub/历战余响' and n.get('selected') is True),None)
    if not sub:return extra
    content=next((g for g in children if g.get('key')=='content'),None)
    for row in content.get('children',[]) if content else []:
        entry=next((n for n in row['children'] if n.get('name')=='进入'),None)
        if entry is None or entry.get('semantic_status')=='row_title_unreadable_scroll':continue
        cy=(entry['bounds'][1]+entry['bounds'][3])/2
        l,t,r,b=round(995*s),round(max(395*s,cy-85*s)),round(1145*s),round(min(1170*s,cy+90*s))
        patch=im[t:b,l:r]
        if not patch.size:continue
        hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
        mask=((hsv[:,:,0]>=115)&(hsv[:,:,0]<=165)&(hsv[:,:,1]>65)&(hsv[:,:,2]>75)).astype(np.uint8)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((max(1,round(7*s)),)*2,np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        candidates=[q for q in stats[1:] if 98*s<q[2]<125*s and 98*s<q[3]<125*s and
                    .85<q[2]/q[3]<1.15 and q[4]/(q[2]*q[3])>.35]
        if len(candidates)!=1:continue
        x,y,w,h,_=map(int,candidates[0])
        row['children'].append(v.node(row['key']+'/material','查看首项材料库存',
                     bounds=[l+x,t+y,l+x+w,t+y+h],source='pixel_geometry',effect='inspect_inventory',
                     semantic_status='material_identity_requires_tooltip'))
    return extra


def read_material_popup(v,im):
    s=im.shape[0]/1440
    close=v.sprites.match('CommonCloseIcon@3x',[1710,220,1940,660],(44,76),invert=True)
    if not close or not close['accepted']:return None
    dx=(close['bounds'][0]+close['bounds'][2])/2/s-1819
    dy=(close['bounds'][1]+close['bounds'][3])/2/s-445
    box=lambda q:np.array(q)+[dx,dy,dx,dy]
    title=v.ocr(im,box([840,392,1730,485]),'material.title',min_height=26,max_height=75)
    names=[q for q in title if q['score']>=.9 and re.fullmatch(r'[\u3400-\u9fff·「」]{2,24}',clean(q['name']))]
    kind=v.ocr(im,box([840,492,1730,565]),'material.kind',min_height=20,max_height=65)
    trace=next((q for q in kind if clean(q['name'])=='行迹升级的高阶素材。' and q['score']>=.9),None)
    if len(names)!=1 or not trace:return None
    owned=v.ocr(im,[380,800,800,1220],'material.owned',min_height=20,max_height=65)
    stock=[(q,int(m[1])) for q in owned if q['score']>=.9 and
           (m:=re.fullmatch(r'当前持有[:：](\d+)',clean(q['name'])))]
    count=stock[0][1] if len(stock)==1 else None
    node=v.sprite_node('material/close','关闭材料详情',close,effect='navigation')
    return dict(page='item.material',label='行迹高阶素材',
                state=dict(material=dict(name=names[0]['name'],owned_count=count,
                           kind='advanced_trace_material',stock_verified=count is not None)),
                nodes=[node],evidence=[close,evidence(names[0]),evidence(trace),
                                      evidence(stock[0][0]) if len(stock)==1 else None])
