"""Sprite-first visual semantics for a bounded, versioned Star Rail daily UI corpus.
This is NOT Android/native accessibility. No coordinates are accepted from callers.
"""
from pathlib import Path
import hashlib, json, sys, time, copy, re
from paths import ROOT
from sprite_assets import load_assets
from recognize_roi import GuideRecognizer, locate_layout, make_tabs, feature, cv2, np, Image
from cavern_state import aligned_box, read_cavern_state
from daily_state import enrich
from navigation_state import read_map, read_field, read_team
from result_state import read_reward_popup, read_challenge_result
from supply_state import read_supply
from login_state import read_login
from battle_state import read_battle
from weekly_state import read_unlock_prompt, guide_weekly_nodes, read_material_popup


def digest(x):
    return hashlib.sha256(x).hexdigest()


class Sprites:
    def __init__(self):
        self.assets = load_assets()
        self.assets['ShopActivityIconStable']=dict(self.assets['ShopActivityIcon'], crop_normalized=[0,0,1,.65], original_asset='ShopActivityIcon')
        self.bases, self.pyramids = {}, {}
        self.matches, self.features = {}, {}

    def begin(self, im):
        self.im=im;self.matches={};self.features={}
        self.scale=im.shape[0]/1440

    def match(self, name, box, heights=(52,90), invert=False, threshold=.80):
        key=(name,tuple(box),heights,invert)
        if key in self.matches:return self.matches[key]
        if name not in self.assets:return None
        if name not in self.bases:
            a=np.array(Image.open(self.assets[name]['path']).convert('RGBA'))
            if self.assets[name].get('crop_normalized'):
                ah,aw=a.shape[:2];l,t,r,b=[round(v*z) for v,z in zip(self.assets[name]['crop_normalized'],[aw,ah,aw,ah])];a=a[t:b,l:r]
            self.bases[name]=cv2.cvtColor((a[:,:,:3]*(a[:,:,3:4]/255)).astype(np.uint8),cv2.COLOR_RGB2BGR)
        s=self.scale;h,w=self.im.shape[:2]
        l,t,r,b=tuple(round(v*s) for v in box)
        l,t,r,b=max(0,l),max(0,t),min(w,r),min(h,b)
        region=(l,t,r,b)
        if r<=l or b<=t:return None
        if region not in self.features:
            self.features[region]=feature(cv2.resize(self.im[t:b,l:r],None,fx=.5,fy=.5,interpolation=cv2.INTER_AREA))
        target=self.features[region]
        pkey=(name,s,heights)
        if pkey not in self.pyramids:
            base=self.bases[name];levels=[]
            for nh in range(heights[0],heights[1]+1,2):
                q=nh*s*.5/base.shape[0]
                levels.append(feature(cv2.resize(base,None,fx=q,fy=q,interpolation=cv2.INTER_AREA)))
            self.pyramids[pkey]=levels
        best=None
        for temp in self.pyramids[pkey]:
            th,tw=temp.shape
            if th>target.shape[0] or tw>target.shape[1]:continue
            response=cv2.matchTemplate(target,temp,cv2.TM_CCOEFF_NORMED)
            scoremap=np.abs(response) if invert else response
            _,score,_,(x,y)=cv2.minMaxLoc(scoremap)
            if best is None or score>best['score']:
                bb=[l+2*x,t+2*y,l+2*(x+tw),t+2*(y+th)]
                pix=self.im[bb[1]:bb[3],bb[0]:bb[2]]
                bright=float(np.percentile(cv2.cvtColor(pix,cv2.COLOR_BGR2GRAY),95))
                best=dict(asset=name,score=float(score),signed_ncc=float(response[y,x]),bounds=bb,
                          bright95=bright,accepted=bool(score>=threshold and bright>150),
                          source=self.assets[name].get('source','original_sprite'),
                          sha256=digest(Path(self.assets[name]['path']).read_bytes()))
                if self.assets[name].get('crop_normalized'):
                    best.update(crop_normalized=self.assets[name]['crop_normalized'],original_asset=self.assets[name]['original_asset'])
        self.matches[key]=best
        return best


class Vision:
    def __init__(self):
        self.sprites=Sprites(); self.guide=GuideRecognizer(reuse_ocr=True)
        self.ocr_cache={}

    def recognize_line(self,im,box,tag):
        s=im.shape[0]/1440
        l,t,r,b=[round(v*s) for v in box]
        if not (0<=l<r<=im.shape[1] and 0<=t<b<=im.shape[0]):return []
        crop=np.ascontiguousarray(im[t:b,l:r]);key=('line',tag,(l,t,r,b),digest(crop.tobytes()))
        if key in self.ocr_cache:
            self.ocr_meta.append(dict(tag=tag,bounds=[l,t,r,b],cache=True,mode='recognition_only'))
            return copy.deepcopy(self.ocr_cache[key])
        start=time.perf_counter();rec=self.guide.get_recognition_engine().recognize_txt([crop])
        result=[dict(name=rec.txts[0],score=float(rec.scores[0]),bounds=[l,t,r,b],source='layout_roi_ocr')] if len(rec.txts) and rec.scores[0]>=.90 else []
        self.ocr_cache[key]=copy.deepcopy(result)
        if len(self.ocr_cache)>64:self.ocr_cache.pop(next(iter(self.ocr_cache)))
        self.ocr_meta.append(dict(tag=tag,bounds=[l,t,r,b],cache=False,mode='recognition_only',ms=(time.perf_counter()-start)*1000))
        return result

    def ocr(self, im, box, tag, min_height=12, max_height=200):
        s=im.shape[0]/1440
        l,t,r,b=[round(v*s) for v in box]
        l,t,r,b=max(0,l),max(0,t),min(im.shape[1],r),min(im.shape[0],b)
        crop=np.ascontiguousarray(im[t:b,l:r])
        if crop.size==0:return []
        key=(tag,tuple([l,t,r,b]),digest(crop.tobytes()))
        if key in self.ocr_cache:
            result=copy.deepcopy(self.ocr_cache[key]);self.ocr_meta.append(dict(tag=tag,bounds=[l,t,r,b],cache=True,lines=len(result)));return result
        start=time.perf_counter(); eng=self.guide.get_engine();receng=self.guide.get_recognition_engine()
        # Keep CUDA convolution tensor shape stable across very different small ROIs.
        # Otherwise repeated tall/narrow -> short/wide transitions cost hundreds of ms.
        # Normalize smaller screenshots to the calibrated glyph size before
        # detection; otherwise a readable scaled header can yield no boxes.
        ratio=min(max(1.,1/s),960/max(crop.shape[:2]))
        resized=cv2.resize(crop,None,fx=ratio,fy=ratio,
                           interpolation=cv2.INTER_CUBIC if ratio>1 else cv2.INTER_AREA) if ratio!=1 else crop
        canvas=np.zeros((960,960,3),np.uint8)
        canvas[:resized.shape[0],:resized.shape[1]]=resized
        det=eng(canvas,use_det=True,use_cls=False,use_rec=False)
        keep=[];crops=[]
        for raw in ([] if det.boxes is None else det.boxes):
            raw=np.asarray(raw)/ratio
            poly=np.array(raw,float)+[l,t];a=poly.min(axis=0);z=poly.max(axis=0)
            if min_height*s <= z[1]-a[1] <= max_height*s and a[1]>=t+2*s and z[1]<=b-2*s:
                keep.append(dict(bounds=[*a,*z],source='roi_ocr'))
                crops.extend(eng.crop_text_regions(crop,np.asarray([raw])))
        if crops:
            rec=receng.recognize_txt(crops)
            for q,txt,score in zip(keep,rec.txts,rec.scores):q.update(name=txt,score=float(score))
        result=[q for q in keep if q.get('score',0)>=.65]
        self.ocr_cache[key]=copy.deepcopy(result)
        if len(self.ocr_cache)>64:self.ocr_cache.pop(next(iter(self.ocr_cache)))
        self.ocr_meta.append(dict(tag=tag,bounds=[l,t,r,b],cache=False,lines=len(result),ms=(time.perf_counter()-start)*1000))
        return result

    def node(self,key,name,role='button',bounds=None,source=None,action=True,**more):
        return dict(key=key,name=name,role=role,bounds=[round(float(x)) for x in bounds] if bounds is not None else None,
                    source=source,actions=['click'] if action else [],enabled=more.pop('enabled',None),**more)

    def group(self,key,name,children,role='group',**more):
        return dict(key=key,name=name,role=role,children=children,**more)

    def sprite_node(self,key,name,match,**more):
        return self.node(key,name,bounds=match['bounds'],source=match.get('source','original_sprite'),evidence=match,**more)

    def text_nodes(self,lines,prefix,buttons=(),parent=None):
        nodes=[]
        for i,q in enumerate(lines):
            act=q['name'] in buttons
            # Read-only text remains readable; text is never assumed to be a button globally.
            effect='navigation' if q['name'] in ['前往','查看','进入','追踪','关闭','奖励','任务','本周任务','本期任务'] else 'state_change'
            nodes.append(self.node(f'{prefix}/{i}-{q["name"]}',q['name'],'button' if act else 'text',q['bounds'],q['source'],act,
                ocr_score=q['score'],effect=effect if act else None))
        return nodes

    def analyze(self,path,detail='navigation'):
        start=time.perf_counter();im=cv2.imread(str(path)) if not isinstance(path,np.ndarray) else path
        if im is None:raise ValueError('JPEG cannot be decoded')
        h,w=im.shape[:2];s=h/1440;self.sprites.begin(im);self.ocr_meta=[]
        m=self.sprites.match
        children=[];page='unknown';label='未知或切换中';gate=[];route_ms=None;state=None
        # Aspect ratio is part of this calibrated layout profile, not a universal guess.
        if abs(w/h-2200/1440)>.02:
            return dict(page=page,label=label,reason='unsupported_aspect_ratio',tree=self.group('root',label,[]),timing_ms={'total':(time.perf_counter()-start)*1000},ocr=[])
        close=m('CommonCloseIcon@3x',(1980,0,2200,170),(44,76))
        hasclose=close and close['accepted']
        g1=m('DailyQuestExploreIcon',(200,210,1100,365),(58,80),True) if hasclose else None
        g2=m('DailyQuestPracticeIcon',(200,210,1100,365),(58,80),True) if g1 and g1['accepted'] else None
        layout=None
        if g2 and g2['accepted']:
            # All five identities and independent close anchor gate guide geometry.
            matches=[]
            for rec in self.guide.matcher.records:
                if rec['id']=='close':q=close
                else:q=m(rec['asset_name'],(170,200,1120,370),(56,84),True)
                if not q:continue
                matches.append(dict(q,id=rec['id'],label=rec['label'],role=rec['role'],selected_candidate=q['signed_ncc']<0))
            layout=locate_layout(im,matches,self.guide.profile)
            if layout['accepted']:
                page='guide.'+layout['selected_main_tab'];label=layout['selected_main_label'];gate=matches;route_ms=(time.perf_counter()-start)*1000
                tabs=[self.sprite_node('main/'+q['id'],q['label'],q,role='tab',selected=q['selected_candidate'],effect='navigation') for q in matches if q['role']=='main_tab' and q['accepted']]
                children.append(self.group('main','指南主页签',tabs,'tablist'))
                if layout['subtab_roi']:
                    # Geometry from measured sprite positions, not fixed absolute pixels.
                    box=np.array(layout['subtab_roi'])/s
                    lines=self.ocr(im,box,'guide.subtabs',min_height=43,max_height=64)
                    lines=[q for q in lines if 232 <= (q['bounds'][0]-layout['offset'][0])/layout['scale'] <= 278]
                    rr=[dict(text=q['name'],score=q['score'],bounds=q['bounds'],polygon=[]) for q in lines]
                    sub,selected=make_tabs(im,rr,layout)
                    nodes=[self.node('sub/'+q['raw_text'],q['raw_text'],'tab',q['text_bounds'],'roi_ocr',True,selected=q['selected'],effect='navigation',layout_bounds=q['row_bounds_candidate']) for q in sub]
                    children.append(self.group('sub','指南子页签',nodes,'tablist'))
                    # Dynamic action labels only, not large illustrative/content panels.
                    actions=self.ocr(im,(1710,380,2025,1130),'guide.actions',min_height=24,max_height=62)
                    # Parent names are read only for rows which actually contain an action.
                    body=[]
                    for i,q in enumerate(actions):
                        if q['name'] not in ['进入','前往','查看','传送']:continue
                        cy=(q['bounds'][1]+q['bounds'][3])/2/s
                        parent_name='内容行 '+str(i+1)
                        # The two recommendation entries have an above-row header.
                        refy=cy-125 if q['name']=='进入' else cy
                        names=self.ocr(im,(780,max(355,refy-50),1320,refy+48),'guide.row.'+str(i),min_height=22,max_height=65)
                        if names:parent_name=' / '.join(x['name'] for x in names)
                        n=self.node('content/'+parent_name+'/'+q['name'],q['name'],bounds=q['bounds'],source='roi_ocr',effect='navigation',ocr_score=q['score'])
                        if not names:n['semantic_status']='row_title_unreadable_scroll'
                        body.append(self.group('content/'+parent_name,parent_name,[n]))
                    children.append(self.group('content','当前子页内容',body))
                    if page=='guide.survival':
                        children+=guide_weekly_nodes(self,im,children,layout)
        gate_ms=(time.perf_counter()-start)*1000
        if page=='unknown':
            # Header sprites distinguish phone menu from full pages and field.
            pg=m('DailyQuestIcon',(1230,990,1500,1160),(64,100)) if hasclose else None
            pa=m('AssignmentIcon',(1810,430,2020,600),(64,100)) if pg and pg['accepted'] else None
            if pa and pa['accepted']:
                page='phone';label='手机菜单';gate=[pg,pa,close];route_ms=(time.perf_counter()-start)*1000
                apps=[('guide','指南','DailyQuestIcon',0,3),('commissions','委托','AssignmentIcon',3,0),
                      ('travel','旅情事记','ActivityIcon',1,1),('synthesis','合成','SynthesisIcon',2,1),
                      ('achievements','成就','AchievementIcon',3,1),('messages','短信','MessagesIcon',0,2),
                      ('warp','跃迁','DrawcardIcon',2,2),('characters','角色','AvatarIcon',3,2),
                      ('map','导航','MapIcon',2,3),('tutorial','教学目录','TeachIcon',3,3),
                      ('team','编队','TeamIcon',0,4),('inventory','背包','InventoryIcon',1,4),
                      ('quests','任务','QuestIcon',2,4),('tools','游戏工具','ToolEntryIcon',3,4)]
                # Align each grid cell to the detected guide anchor; independent per-icon match.
                gc=np.array([(pg['bounds'][0]+pg['bounds'][2])/2,(pg['bounds'][1]+pg['bounds'][3])/2])/s
                dx,dy=gc-np.array([1373,1072])
                buttons=[]
                for key,name,asset,col,row in apps:
                    cx=1373+185*col+dx;cy=513+186*row+dy
                    q=m(asset,(cx-72,cy-72,cx+72,cy+72),(64,102))
                    if q and q['accepted']:buttons.append(self.sprite_node('app/'+key,name,q,effect='navigation'))
                # Missing original honor variant is explicitly OCR, never mislabeled sprite.
                lines=self.ocr(im,(1470+dx,922+dy,1650+dx,1002+dy),'phone.honor',min_height=18,max_height=45)
                if not any(q['name']=='无名勋礼' for q in lines):
                    lines=self.recognize_line(im,(1470+dx,922+dy,1650+dx,1002+dy),'phone.honor-line')
                buttons+=self.text_nodes(lines,'app.honor',['无名勋礼'])
                for n in buttons:
                    if n['name']=='无名勋礼':n.update(key='app/honor',effect='navigation')
                children.append(self.group('apps','应用',buttons))
            else:
                ca=m('AssignmentIcon',(30,20,140,135),(44,90)) if hasclose else None
                if ca and ca['accepted']:
                    page='commissions';label='委托';gate=[ca,close];route_ms=(time.perf_counter()-start)*1000
                    lines=self.ocr(im,(200,240,1370,345),'commissions.tabs',min_height=22,max_height=65)
                    children.append(self.group('tabs','委托类别',self.text_nodes(lines,'tabs',['专属材料','经验材料/信用点','合成材料']),'tablist'))
                    lines=self.ocr(im,(160,330,740,1190),'commissions.list',min_height=25,max_height=65)
                    children.append(self.group('list','委托列表',self.text_nodes(lines,'commissions')))
                    lines=self.ocr(im,(1000,1140,2080,1260),'commissions.actions',min_height=20,max_height=65)
                    children+=self.text_nodes(lines,'action',['领取奖励','再次派遣','一键领取'])
                elif hasclose:
                    # Only a small header is OCR fallback when an original icon isn't verified.
                    title=self.ocr(im,(140,30,430,135),'page.header',min_height=20,max_height=65)
                    texts=[q['name'] for q in title]
                    if '导航' in texts:
                        marker=m('MapIcon',(25,10,140,140),(40,90),True)
                        if marker and marker['accepted']:
                            page='map';label='导航';gate=[marker,close,dict(source='roi_ocr',lines=texts)]
                            route_ms=(time.perf_counter()-start)*1000
                            state,extra=read_map(self,im,close);children+=extra
                    elif any('旅情事记' in x for x in texts):
                        marker=m('ActivityIcon',(25,10,150,160),(44,90),True)
                        if marker and marker['accepted']:
                            page='travel';label='旅情事记';gate=[marker,close,dict(source='roi_ocr',lines=texts)]
                            route_ms=(time.perf_counter()-start)*1000
                            children+=self.text_nodes(title,'travel.header')
                    elif any(x=='队伍' for x in texts):
                        marker=m('TeamIcon',(25,10,180,170),(40,90),True)
                        if marker and marker['accepted']:
                            page='team';label='队伍';gate=[marker,close,dict(source='roi_ocr',lines=texts)]
                            route_ms=(time.perf_counter()-start)*1000
                            state,extra=read_team(self,im,close);children+=extra
                    elif any(x in ('侵蚀隧洞','历战余响') for x in texts):
                        page='echo' if '历战余响' in texts else 'cavern';label='历战余响' if page=='echo' else '侵蚀隧洞';gate=[close,dict(source='roi_ocr',lines=texts)];route_ms=(time.perf_counter()-start)*1000
                        lines=self.ocr(im,(1360,130,2120,285),'cavern.title',min_height=20,max_height=65)
                        children+=self.text_nodes(lines,'title')
                        # Difficulty choices identified from their visible numeral text.
                        lines=self.ocr(im,(130,140,260,1080),'cavern.difficulty',min_height=22,max_height=65)
                        children.append(self.group('difficulties','难度',self.text_nodes(lines,'difficulty',['I','II','III','IV','V','VI','Ⅱ','Ⅲ','Ⅳ','Ⅴ','Ⅵ']),'tablist'))
                        lines=self.ocr(im,aligned_box([1450,1220,2140,1390],close,s),'cavern.challenge',min_height=16,max_height=70)
                        children+=self.text_nodes([q for q in lines if q['name']=='挑战'],'challenge',['挑战'])
                        for n in children:
                            if n.get('name')=='挑战':n['effect']='challenge_preparation_or_resource_use'
                        state,state_nodes=read_cavern_state(self,im,close,lines,page)
                        children+=state_nodes
                        if page=='echo' and state['challenge']['weekly_rewards_remaining']==0:
                            for n in children:
                                if n.get('name')=='挑战':n['effect']='challenge_without_weekly_rewards'
                    elif any('无名勋礼' in x for x in texts):
                        tasks=any(x=='任务' for x in texts);page='honor.tasks' if tasks else 'honor.rewards';label='无名勋礼·'+('任务' if tasks else '奖励');gate=[close,dict(source='roi_ocr',lines=texts)];route_ms=(time.perf_counter()-start)*1000
                        # Header-confirmed left rail; bounds are observed layout candidates.
                        rail=[]
                        for k,n,box in [('rewards','奖励',[60,185,140,265]),('tasks','任务',[68,345,132,420])]:
                            rail.append(self.node('main/'+k,n,'tab',np.array(box)*s+np.tile(np.array([(close['bounds'][0]+close['bounds'][2])/2,(close['bounds'][1]+close['bounds'][3])/2])-np.array([2118,84])*s,2),'observed_layout',True,selected=(k=='tasks')==tasks,effect='navigation'))
                        children.append(self.group('main','勋礼页签',rail,'tablist'))
                        if tasks:
                            lines=self.ocr(im,(280,530,530,1010),'honor.subtabs',min_height=30,max_height=65)
                            ns=self.text_nodes(lines,'sub',['本周任务','本期任务'])
                            for n in ns:
                                if n['actions']:
                                    y=round((n['bounds'][1]+n['bounds'][3])/2);p=im[y,round(222*s)];n.update(role='tab',selected=bool(int(p[2])>140 and int(p[1])>120))
                            children.append(self.group('sub','任务周期',ns,'tablist'))
                            actions=self.ocr(im,(1810,475,1950,1135),'honor.actions',min_height=23,max_height=60)
                            rows=[]
                            for i,q in enumerate(actions):
                                if q['name'] not in ['追踪','领取']:continue
                                y=(q['bounds'][1]+q['bounds'][3])/2/s
                                names=self.ocr(im,(660,y-60,1535,y+12),'honor.row.'+str(i),min_height=25,max_height=65)
                                name=' / '.join(x['name'] for x in names) or '任务行 '+str(i+1)
                                rows.append(self.group('task/'+name,name,[self.node('task/'+name+'/'+q['name'],q['name'],bounds=q['bounds'],source='roi_ocr',effect='navigation' if q['name']=='追踪' else 'claim')]))
                            children.append(self.group('tasks','当前任务',rows))
                        else:
                            lines=self.ocr(im,(1320,1200,2110,1310),'honor.actions',min_height=22,max_height=65)
                            children+=self.text_nodes(lines,'action',['一键领取','解锁无名客的荣勋'])
        if page=='unknown' and not hasclose:
            # Battle results and item rewards have no close icon. A dark
            # overlay prior keeps these OCR gates off ordinary bright fields.
            top=im[round(80*s):round(180*s),round(600*s):round(1600*s)]
            if top.size and np.median(cv2.cvtColor(top,cv2.COLOR_BGR2GRAY))<90:
                overlay=read_reward_popup(self,im) or read_challenge_result(self,im)
                if overlay:
                    page=overlay['page'];label=overlay['label'];gate=overlay['evidence']
                    state=overlay['state'];children+=overlay['nodes']
                    route_ms=(time.perf_counter()-start)*1000
        if page=='unknown' and not hasclose:
            phone=m('PhoneIcon',(10,20,150,190),(58,90),threshold=.70)
            g=m('DailyQuestIcon',(1590,0,1850,160),(58,90)) if phone and phone['accepted'] else None
            # Notification badges occlude the upper-right of the original guide Sprite.
            # A lower NCC is accepted only with a measured red badge plus both other HUD anchors.
            if g and not g['accepted'] and g['score']>=.72:
                l,t,r,b=g['bounds'];x0=max(l,round(r-22*s));x1=min(w,round(r+38*s))
                y0=max(0,round(t-26*s));y1=min(h,round(t+38*s))
                patch=im[y0:y1,x0:x1].astype(np.int16)
                red=(patch[:,:,2]>140)&(patch[:,:,2]>patch[:,:,1]*1.6)&(patch[:,:,2]>patch[:,:,0]*1.6)
                fraction=float(red.mean()) if red.size else 0.
                if fraction>=.1:
                    g=dict(g,accepted=True,badge_occlusion=True,badge_red_fraction=round(fraction,3),
                           acceptance='red_badge_and_phone_inventory_anchors')
            inv=m('InventoryIcon',(1750,0,1950,160),(58,94)) if g and g['accepted'] else None
            if inv and inv['accepted']:
                page='field';label='主界面';gate=[phone,g,inv];route_ms=(time.perf_counter()-start)*1000
                ns=[self.sprite_node('phone','手机菜单',phone,effect='navigation'),self.sprite_node('guide','指南',g,effect='navigation'),self.sprite_node('inventory','背包',inv,effect='navigation')]
                for key,name,asset,box in [('travel','旅情事记','ActivityIcon',(1280,0,1500,160)),('warp','跃迁','DrawcardIcon',(1510,0,1740,160)),('team','编队','TeamIcon',(1880,0,2060,160)),('characters','角色','AvatarIcon',(2000,0,2200,160))]:
                    q=m(asset,box,(58,94),threshold=.78 if key=='travel' else .80)
                    if q and q['accepted']:ns.append(self.sprite_node(key,name,q,effect='navigation'))
                for key,name,asset,box,heights in [
                    ('honor','无名勋礼','BPiPhone',(1410,0,1580,160),(64,98)),
                    ('shop','商店','ShopActivityIconStable',(1175,0,1335,165),(38,62)),
                    ('tutorial','教学目录','TeachIcon',(285,35,410,175),(58,98))]:
                    q=m(asset,box,heights,threshold=.76 if key=='tutorial' else .80)
                    if q and q['accepted']:ns.append(self.sprite_node(key,name,q,effect='navigation'))
                children.append(self.group('hud','主界面入口',ns))
                state,extra=read_field(self,im);children+=extra
        if page=='unknown' and not hasclose:
            supply=read_supply(self,im)
            if supply:
                page='supply.monthly';label='列车补给';gate=supply['evidence']
                state=supply['state'];children+=supply['nodes']
                route_ms=(time.perf_counter()-start)*1000
        if page=='unknown':
            # Light-background guide modals do not satisfy the dark reward prior.
            overlay=read_unlock_prompt(self,im) or read_material_popup(self,im)
            if overlay:
                page=overlay['page'];label=overlay['label'];gate=overlay['evidence']
                state=overlay['state'];children=overlay['nodes'];hasclose=False
                route_ms=(time.perf_counter()-start)*1000
        if page=='unknown' and not hasclose:
            battle=read_battle(self,im)
            if battle:
                page=battle['page'];label=battle['label'];gate=battle['evidence']
                state=battle['state'];children=battle['nodes']
                route_ms=(time.perf_counter()-start)*1000
        if page=='unknown' and not hasclose:
            login=read_login(self,im)
            if login:
                page=login['page'];label=login['label'];gate=login['evidence']
                state=login['state'];children=login['nodes']
                route_ms=(time.perf_counter()-start)*1000
        if page!='unknown' and hasclose:
            state=enrich(self,im,page,children,close,detail,state)
            children.append(self.sprite_node('close','关闭',close,effect='navigation'))
        # Unknown pages have no click references, even if an isolated glyph matched.
        return dict(schema='hsr-visual-tree-v1',page=page,label=label,dimensions=[w,h],native_accessibility=False,
                    coverage='bounded daily-navigation controls; not every decorative/item/hidden control',
                    tree=self.group('root',label,children,'application'),page_evidence=gate,ocr=self.ocr_meta,
                    timing_ms=dict(total=(time.perf_counter()-start)*1000,page_route=route_ms if route_ms is not None else (time.perf_counter()-start)*1000),
                    reason='matched_profile' if page!='unknown' else 'unrecognized_dimmed_or_transition',
                    **({'state':state} if state is not None else {}))


def walk(root):
    for n in root.get('children',[]):
        yield n
        yield from walk(n)


if __name__=='__main__':
    from output import compact_scores
    v=Vision()
    for p in sys.argv[1:]:
        r=v.analyze(p,'content')
        out=Path(__file__).parent/'results';out.mkdir(exist_ok=True)
        (out/(Path(p).stem+'.json')).write_text(json.dumps(compact_scores(r),ensure_ascii=False,indent=2))
        print(Path(p).name,r['page'],round(r['timing_ms']['total'],1),[(n['name'],n.get('source')) for n in walk(r['tree']) if n.get('actions')],flush=True)
