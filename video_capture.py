"""Read-only scrcpy 3.3.4 H.264 -> RAM -> fresh JPEG. No audio/control/video file.
Uses the installed server and documented framed protocol; preserves ADB screenshot
metadata so the existing validated tap mapper can independently check the display.
"""
import os,socket,struct,subprocess,threading,time,uuid,json
from pathlib import Path
import av
from PIL import Image
import sys
from paths import SCRIPTS, SERIAL
sys.path.insert(0,str(SCRIPTS))
import adb_screenshot


class VideoCapture:
    def __init__(self,serial):
        self.serial=serial;self.sock=None;self.process=None;self.cond=threading.Condition()
        self.frame=None;self.sequence=0;self.error=None;self.closed=False
        self.abstract='scrcpy_'+uuid.uuid4().hex[:8]
        # scrcpy SCID must be a positive 31-bit hex value.
        self.scid=f'{int(self.abstract[-8:],16)&0x7fffffff:08x}';self.abstract='scrcpy_'+self.scid
        self.forward_owned=False

    def adb(self,*args):return adb_screenshot.adb(self.serial,*args)

    def start(self):
        forwards=self.adb('forward','--list').decode()
        if 'tcp:27183' in forwards:raise ValueError('scrcpy_forward_in_use')
        self.adb('push',os.environ.get('HSR_UI_SCRCPY_SERVER','/usr/share/scrcpy/scrcpy-server'),'/data/local/tmp/hsr-ui-scrcpy.jar')
        self.adb('forward','--no-rebind','tcp:27183','localabstract:'+self.abstract)
        self.forward_owned=True
        args=['adb','-s',self.serial,'shell','CLASSPATH=/data/local/tmp/hsr-ui-scrcpy.jar',
              'app_process','/','com.genymobile.scrcpy.Server','3.3.4','scid='+self.scid,
              'tunnel_forward=true','audio=false','control=false','cleanup=true',
              'send_device_meta=false','send_dummy_byte=true','send_codec_meta=true','send_frame_meta=true',
              'max_size=0','max_fps=15','video_bit_rate=12000000','log_level=warn']
        self.process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            try:
                sock=socket.create_connection(('127.0.0.1',27183),timeout=.3)
                b=sock.recv(1)
                if b==b'\x00':self.sock=sock;break
                sock.close()
            except (OSError,socket.timeout):pass
            time.sleep(.05)
        if self.sock is None:
            self.close();raise ValueError('scrcpy_video_connect_failed')
        self.sock.settimeout(5)
        codec,w,h=struct.unpack('>III',self.read(12))
        if codec!=int.from_bytes(b'h264','big'):self.close();raise ValueError('unsupported_video_codec')
        self.dimensions=[w,h];self.thread=threading.Thread(target=self.reader,daemon=True);self.thread.start()

    def read(self,n):
        out=b''
        while len(out)<n:
            block=self.sock.recv(n-len(out))
            if not block:raise EOFError('video_disconnected')
            out+=block
        return out

    def reader(self):
        codec=av.CodecContext.create('h264','r');codec.thread_count=2
        prefix=b'';base=None
        try:
            while not self.closed:
                pts,size=struct.unpack('>QI',self.read(12))
                if size>32*1024*1024:raise ValueError('invalid_video_packet')
                data=self.read(size);arrival=time.monotonic()
                if pts>>63:prefix=data;continue
                pts=pts&((1<<62)-1)
                if base is None:base=(arrival,pts)
                lag=(arrival-base[0])-(pts-base[1])/1e6
                # No queue: decode sequentially and replace only the newest frame.
                for frame in codec.decode(av.Packet(prefix+data)):
                    prefix=b''
                    with self.cond:
                        self.frame=frame;self.arrival=arrival;self.lag=lag
                        self.sequence+=1;self.cond.notify_all()
        except Exception as exc:
            with self.cond:self.error=str(exc);self.cond.notify_all()

    def capture(self,path):
        begin=time.perf_counter()
        if self.sock is None:self.start()
        before=adb_screenshot.display_state(self.serial)
        with self.cond:
            seq=self.sequence;deadline=time.monotonic()+3
            while self.sequence<=seq and self.error is None and time.monotonic()<deadline:
                self.cond.wait(min(.2,max(0,deadline-time.monotonic())))
            if self.error:raise ValueError(self.error)
            if self.sequence<=seq:raise ValueError('no_fresh_video_frame')
            frame=self.frame;arrival=self.arrival;lag=self.lag;sequence=self.sequence
        image=frame.to_image()
        after=adb_screenshot.display_state(self.serial)
        if before!=after or [after['width'],after['height']]!=list(image.size):
            raise ValueError('video_display_changed')
        age=time.monotonic()-arrival
        if age>.5 or lag>.35:raise ValueError('video_frame_backlog_or_stale')
        metadata=dict(schema=adb_screenshot.SCHEMA,serial=self.serial,native_size=list(image.size),display=after,
                      capture_source='scrcpy_h264',frame_sequence=sequence,frame_age_seconds=age)
        exif=Image.Exif();exif[270]=json.dumps(metadata,separators=(',',':'))
        # Screenshot persistence is JPEG only. Video and decoder buffers stay in RAM.
        path=Path(path);temp=path.with_suffix('.jpg.tmp')
        image.save(temp,format='JPEG',quality=75,subsampling=2,optimize=False,progressive=False,exif=exif)
        temp.replace(path)
        return dict(path=str(path),display_verified=True,native_size=list(image.size),bytes=path.stat().st_size,
                    capture_source='scrcpy_h264',frame_age_ms=age*1000,backlog_ms=lag*1000,
                    capture_ms=(time.perf_counter()-begin)*1000)

    def close(self):
        self.closed=True
        if self.sock:
            try:self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.sock.close();self.sock=None
        if self.process:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        if self.forward_owned:
            forwards=self.adb('forward','--list').decode().splitlines()
            if any(self.serial in row and 'tcp:27183' in row and self.abstract in row for row in forwards):
                self.adb('forward','--remove','tcp:27183')
            self.forward_owned=False


if __name__=='__main__':
    if not SERIAL:raise SystemExit('HSR_UI_SERIAL is required')
    v=VideoCapture(SERIAL)
    try:
        for i in range(4):print(json.dumps(v.capture(Path(__file__).parent/f'results/video-{i}.jpg')),flush=True)
    finally:v.close()
