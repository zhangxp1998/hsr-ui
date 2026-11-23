import os,signal,time
from pathlib import Path
from service import request
r=request({'action':'status'});pid=r['result']['pid']
cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
assert str(Path(__file__).parent/'service.py').encode() in cmd and b'--serve' in cmd
request({'action':'release'})
os.kill(pid,signal.SIGTERM)
for _ in range(100):
    if not Path(f'/proc/{pid}/cmdline').exists():break
    time.sleep(.03)
print('Stopped owned transient vision worker',pid)
