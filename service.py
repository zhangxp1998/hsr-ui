"""Local, serialized semantic UI service. Socket owner-only; no listening TCP port."""
import argparse, fcntl, importlib.util, json, os, select, socket, subprocess, sys, time, uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
from paths import ROOT, SCRIPTS, SERIAL, GAME_PACKAGE
from output import compact_scores, agent_response, output_format
STATE=HERE/'.state'; STATE.mkdir(exist_ok=True,mode=0o700)
SOCKET=str(STATE/'ui.sock')
sys.path.insert(0,str(SCRIPTS))


def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


class Service:
    def __init__(self):
        from vision import Vision, walk
        import adb_screenshot
        self.vision=None;self.walk=walk;self.capture_module=adb_screenshot
        self.tap=module('tablet_tap',SCRIPTS/'hsr-tablet-tap.py')
        self.current={};self.records={};self.video=None

    def capture(self):
        t=time.perf_counter();self.tap.validate_tablet(SERIAL)
        # Foreground + lock status are checked before capture, not inferred from a stale tree.
        state=self.capture_module.adb(SERIAL,'shell',
            'dumpsys window displays | grep mCurrentFocus; dumpsys trust | head -3').decode()
        if GAME_PACKAGE not in state or 'deviceLocked=1' in state:
            self.release()
            raise ValueError('game_not_foreground_or_device_locked')
        name=STATE/('capture-'+uuid.uuid4().hex[:12]+'.jpg')
        try:
            if self.video is None:
                from video_capture import VideoCapture
                self.video=VideoCapture(SERIAL)
            meta=self.video.capture(name)
        except Exception as exc:
            reason=str(exc);self.close_video()
            meta=self.capture_module.capture(SERIAL,name)
            meta.update(capture_source='adb_jpeg_helper_fallback',fallback_reason=reason)
        if not meta['display_verified']:raise ValueError('unverified_display')
        return name,dict(capture_and_validation=(time.perf_counter()-t)*1000,capture_source=meta.get('capture_source'),frame_age_ms=meta.get('frame_age_ms'),fallback_reason=meta.get('fallback_reason'))

    def close_video(self):
        if self.video:
            self.video.close();self.video=None

    def release(self):
        self.close_video()
        self.current.clear()

    @staticmethod
    def target_delta(a,b,node,target):
        """Compare the same canvas pixels, tolerating only small OCR box jitter.

        Resizing two independently cropped glyphs turns 1px detector jitter into
        a different-looking button. Geometry/semantics still must agree first.
        """
        from vision import cv2,np
        if a is None or b is None:raise ValueError('missing_observation_image')
        if a.shape!=b.shape:raise ValueError('display_geometry_changed')
        for key in ('name','role','actions','effect','checked','selected','enabled','value','scroll_direction'):
            if node.get(key)!=target.get(key):raise ValueError('target_semantics_changed_reobserve')
        x=np.asarray(node['bounds'],dtype=int);y=np.asarray(target['bounds'],dtype=int)
        tolerance=max(2,round(6*a.shape[0]/1440))
        if np.max(np.abs(x-y))>tolerance:raise ValueError('target_geometry_changed_reobserve')
        l,t=np.minimum(x[:2],y[:2]);r,d=np.maximum(x[2:],y[2:])
        if not (0<=l<r<=a.shape[1] and 0<=t<d<=a.shape[0]):raise ValueError('invalid_target_bounds')
        def patch(im):return cv2.resize(cv2.cvtColor(im[t:d,l:r],cv2.COLOR_BGR2GRAY),(96,48)).astype(float)
        delta=float(np.mean(np.abs(patch(a)-patch(b))))
        if delta>14:raise ValueError('target_appearance_changed_reobserve')
        return delta

    def observe(self,req,owner,internal=False):
        t=time.perf_counter();live=req.get('action')=='observe';timing={}
        if live:path,timing=self.capture()
        else:
            path=Path(req['image']).resolve()
            if path.suffix.lower() not in ('.jpg','.jpeg'):raise ValueError('JPEG_required')
        if self.vision is None:
            from vision import Vision
            self.vision=Vision()
        result=self.vision.analyze(path,req.get('detail','navigation'))
        obs=uuid.uuid4().hex
        nodes={}
        for n in self.walk(result['tree']):
            if n.get('actions'):
                ref=obs[:8]+'-'+str(len(nodes)+1)
                n['ref']=ref;nodes[ref]=n
        result.update(observationId=obs,image=str(path),live=live,expires_in_seconds=90 if live else None)
        result['timing_ms'].update(timing)
        result['timing_ms']['service_total']=(time.perf_counter()-t)*1000
        if not internal:
            self.current[owner]=obs
            self.records[obs]=dict(owner=owner,created=time.monotonic(),result=result,nodes=nodes)
            if len(self.records)>32:self.records.pop(next(iter(self.records)))
        return result

    @staticmethod
    def selection(tree):
        from vision import walk
        return sorted(n['key'] for n in walk(tree) if n.get('role')=='tab' and n.get('selected') is True)

    def signature(self,observation):
        # Ignore pixels, scores and timers: require stable semantic controls/state.
        return (observation['page'],[(n.get('key'),n.get('name'),n.get('selected'),
                    n.get('checked'),n.get('value'),n.get('enabled')) for n in self.walk(observation['tree'])])

    def validate_reference(self,req,owner):
        obs=req.get('observationId');record=self.records.get(obs)
        if not record or self.current.get(owner)!=obs or record['owner']!=owner:
            raise ValueError('stale_or_unknown_observation')
        if not record['result']['live']:raise ValueError('replay_observation_cannot_click')
        if time.monotonic()-record['created']>90:raise ValueError('observation_expired')
        if req.get('ref') not in record['nodes']:raise ValueError('unknown_node_reference')
        return record,record['nodes'][req['ref']]

    def click(self,req,owner,alive=lambda:True):
        t=time.perf_counter();record,node=self.validate_reference(req,owner)
        fresh=self.observe(dict(action='observe'),owner,internal=True)
        old=record['result']
        if fresh['page']!=old['page'] or fresh['page']=='unknown':raise ValueError('page_changed_reobserve')
        if old['page']=='login.title' and old.get('state',{}).get('login',{}).get('server') != fresh.get('state',{}).get('login',{}).get('server'):
            raise ValueError('login_server_changed_reobserve')
        if old.get('state',{}).get('uid') is not None and old['state']['uid'] != fresh.get('state',{}).get('uid'):
            raise ValueError('account_uid_changed_reobserve')
        if self.selection(fresh['tree'])!=self.selection(old['tree']):raise ValueError('selected_tabs_changed_reobserve')
        candidates=[n for n in self.walk(fresh['tree']) if n.get('key')==node['key'] and n.get('actions')]
        if len(candidates)!=1:raise ValueError('node_missing_or_ambiguous_reobserve')
        target=candidates[0]
        if target.get('selected') is True:raise ValueError('tab_already_selected')
        if target.get('enabled') is False:raise ValueError('node_disabled')
        action=req.get('action','click')
        if action not in target.get('actions',[]):raise ValueError('node_does_not_support_action')
        # The target must still look like the observed target, not just share text.
        from vision import cv2,np
        a=cv2.imread(old['image']);b=cv2.imread(fresh['image'])
        delta=self.target_delta(a,b,node,target)
        size=self.tap.screenshot_size(fresh['image'])
        image_point=self.tap.choose_point(target['bounds'],size)
        point,native=self.tap.map_to_device(image_point,size,fresh['image'],SERIAL)
        if not alive():raise ValueError('caller_cancelled_before_action')
        validation=(time.perf_counter()-t)*1000
        if req.get('dryRun'):
            return dict(tapped=False,validated=True,node=target,point=point,timing_ms=dict(validation=validation,total=validation))
        # Consume even on an ADB error: never retry a potentially sent tap implicitly.
        self.current.pop(owner,None)
        t2=time.perf_counter()
        if action=='scroll':
            l,u,r,d=target['bounds'];direction=target.get('scroll_direction')
            if direction not in ('up','down'):raise ValueError('invalid_scroll_direction')
            # Keep overlapping full rows: a half-panel fling clipped the next
            # dungeon title even while its material tile was fully visible.
            fraction=.14 if '/entries/' in target['key'] else .25
            x=round(l+(r-l)*.75);lo=round(u+(d-u)*(.5-fraction));hi=round(u+(d-u)*(.5+fraction))
            start,end=((x,hi),(x,lo)) if direction=='down' else ((x,lo),(x,hi))
            p1,_=self.tap.map_to_device(start,size,fresh['image'],SERIAL)
            p2,_=self.tap.map_to_device(end,size,fresh['image'],SERIAL)
            self.capture_module.adb(SERIAL,'shell','input','swipe',*map(str,(*p1,*p2,450)),timeout=15)
        else:
            self.capture_module.adb(SERIAL,'shell','input','tap',str(point[0]),str(point[1]),timeout=15)
        tapms=(time.perf_counter()-t2)*1000
        # Capture time naturally covers much of the UI transition. Bounded retries only.
        time.sleep(.08)
        after=None;previous=None;settled=False;changed=False;attempt=-1
        original_signature=self.signature(old)
        for attempt in range(6):
            if not alive():break
            after=self.observe(dict(action='observe'),owner)
            signature=self.signature(after)
            changed=signature!=original_signature
            if after['page']!='unknown' and changed and signature==previous:
                settled=True;break
            previous=signature
            time.sleep(.12)
        return dict(tapped=action=='click',scrolled=action=='scroll',node_key=target['key'],name=target['name'],effect=target.get('effect'),
                    target_image_delta=delta,point=point,observation=after,
                    settled=settled,transition_observed=changed,settle_attempts=attempt+1,
                    timing_ms=dict(preclick_validation=validation,input=tapms,total=(time.perf_counter()-t)*1000))

    def handle(self,req,alive):
        owner=req.get('_owner','cli')
        action=req.get('action')
        if action=='status':return dict(ready=True,pid=os.getpid(),device=SERIAL,socket=SOCKET,video_active=self.video is not None)
        if action=='release':self.release();return dict(released=True)
        if action in ('analyze','observe'):return self.observe(req,owner)
        if action in ('click','scroll'):return self.click(req,owner,alive)
        raise ValueError('unsupported_action')


def serve():
    lock=open(STATE/'daemon.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if Path(SOCKET).exists():Path(SOCKET).unlink()
    server=socket.socket(socket.AF_UNIX);server.bind(SOCKET);os.chmod(SOCKET,0o600);server.listen(8);server.settimeout(30)
    service=None;last_request=time.monotonic()
    try:
        while True:
            try:conn,_=server.accept()
            except socket.timeout:
                if service:service.close_video()
                if time.monotonic()-last_request>900:break
                continue
            last_request=time.monotonic()
            with conn:
                conn.settimeout(90);data=b''
                try:
                    while b'\n' not in data:
                        block=conn.recv(4096)
                        if not block:raise ValueError('disconnected')
                        data+=block
                        if len(data)>65536:raise ValueError('oversized_request')
                    req=json.loads(data.split(b'\n',1)[0])
                    if service is None:service=Service()
                    def alive():
                        readable,_,_=select.select([conn],[],[],0)
                        return not readable or bool(conn.recv(1,socket.MSG_PEEK))
                    result=service.handle(req,alive)
                    response=dict(ok=True,result=result)
                except Exception as e:response=dict(ok=False,error=str(e),error_type=type(e).__name__)
                try:conn.sendall(json.dumps(compact_scores(response),ensure_ascii=False).encode()+b'\n')
                except (BrokenPipeError,ConnectionResetError):pass
    finally:
        if service:service.release()
        server.close();Path(SOCKET).unlink(missing_ok=True)


def request(req):
    """Internal full-fidelity RPC for the web console and local integrations.

    Public CLI/plugin consumers are projected only in the entry point below.
    """
    sock=socket.socket(socket.AF_UNIX);sock.settimeout(90)
    try:sock.connect(SOCKET)
    except (FileNotFoundError,ConnectionRefusedError):
        sock.close()
        with open(STATE/'startup.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            test=socket.socket(socket.AF_UNIX)
            try:test.connect(SOCKET)
            except (FileNotFoundError,ConnectionRefusedError):
                log=open(STATE/'worker.log','ab')
                subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            finally:test.close()
        for _ in range(100):
            time.sleep(.03);sock=socket.socket(socket.AF_UNIX);sock.settimeout(90)
            try:sock.connect(SOCKET);break
            except (FileNotFoundError,ConnectionRefusedError):sock.close()
        else:raise RuntimeError('worker_start_failed')
    with sock:
        sock.sendall(json.dumps(req).encode()+b'\n');data=b''
        while b'\n' not in data:
            block=sock.recv(65536)
            if not block:raise RuntimeError('worker_disconnected')
            data+=block
        return json.loads(data.split(b'\n',1)[0])


if __name__=='__main__':
    if '--serve' in sys.argv:serve()
    else:
        t=time.perf_counter()
        try:
            req=json.loads(sys.stdin.read())
            output_format(req)  # Reject invalid output modes before any action.
            r=request(req);r['client_ms']=(time.perf_counter()-t)*1000
            r=agent_response(r,req)
        except Exception as e:r=dict(ok=False,error=str(e))
        print(json.dumps(compact_scores(r),ensure_ascii=False,separators=(',',':')))
