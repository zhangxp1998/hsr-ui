#!/usr/bin/env python3
"""Loopback-only semantic HSR console; no raw tap or screenshot HTTP endpoint."""
from __future__ import annotations

import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from service import request as ui_request, SERIAL
from paths import SCRIPTS

IDLE_SECONDS = 60
FRAME_SECONDS = 0.8
REFERENCE_SECONDS = 10
OWNER_SLOTS = 16
LOG = logging.getLogger('hsr-web')


def walk(node):
    yield node
    for child in node.get('children', []):
        yield from walk(child)


class Tablet:
    def __init__(self):
        self.env = dict(os.environ)
        self.brightness_owned = False

    def run(self, args, timeout=20):
        p = subprocess.run(args, env=self.env, capture_output=True, text=True,
                           timeout=timeout)
        if p.returncode:
            # Unlock helper reports only a safe status; never request credentials.
            raise RuntimeError((p.stderr or p.stdout or 'device command failed').strip()[:800])
        return p.stdout.strip()

    def adb(self, *args):
        return self.run(['/usr/bin/adb', '-s', SERIAL, *args])

    def brightness(self, action):
        return json.loads(self.run([sys.executable, str(SCRIPTS / 'tcl-tablet-brightness.py'),
                                    '--serial', SERIAL, action], timeout=45))

    def prepare(self):
        if not SERIAL:
            raise RuntimeError('Set HSR_UI_SERIAL before connecting')
        devices = self.run(['/usr/bin/adb', 'devices', '-l'])
        model='model:'+os.environ.get('HSR_UI_MODEL','9469X')
        product='device:'+os.environ.get('HSR_UI_PRODUCT','Bellona_WF_GL')
        matches = [s.split() for s in devices.splitlines()
                   if model in s.split() and product in s.split()]
        if len(matches) != 1 or matches[0][:2] != [SERIAL, 'device']:
            raise RuntimeError('TCL 平板未唯一连接；请检查 ADB 隧道和设备')
        unlock = os.environ.get('HSR_UI_UNLOCK_HELPER')
        if not unlock and 'deviceLocked=0' not in self.adb('shell', 'dumpsys', 'trust')[:2000]:
            raise RuntimeError('Unlock manually or configure HSR_UI_UNLOCK_HELPER')
        self.brightness('start')  # Refuses another run's saved brightness session.
        self.brightness_owned = True
        self.adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
        if unlock:
            self.run([unlock, 'unlock'], timeout=45)
        if 'deviceLocked=0' not in self.adb('shell', 'dumpsys', 'trust')[:2000]:
            raise RuntimeError('平板解锁未核实；不会自动重试 PIN')

    def lock(self):
        self.adb('shell', 'input', 'keyevent', 'KEYCODE_SLEEP')
        for _ in range(8):
            trust = self.adb('shell', 'dumpsys', 'trust')[:2000]
            power = self.adb('shell', 'dumpsys', 'power')
            locked = 'deviceLocked=1' in trust
            asleep = 'mWakefulness=Asleep' in power or 'mWakefulness=Dozing' in power
            if locked and asleep:
                return {'locked': True, 'sleeping': True}
            time.sleep(0.25)
        raise RuntimeError('锁屏命令已发出，但锁屏 / 休眠状态未同时核实')

    def restore(self):
        if self.brightness_owned:
            result = self.brightness('finish')
            self.brightness_owned = False
            return result
        return None


class Console:
    def __init__(self, call=ui_request, tablet=None, clock=time.monotonic):
        self.call = call
        self.tablet = tablet or Tablet()
        self.clock = clock
        self.mu = threading.RLock()
        self.operation = threading.Lock()
        self.stop = threading.Event()
        self.mode = 'disconnected'
        self.message = '点击连接，开始实时观察'
        self.last_activity = 0.0
        self.session = 0
        self.sequence = 0
        self.owner_prefix = 'hsr-web:' + secrets.token_hex(6)
        self.snapshot = None
        self.captured_at = 0.0
        self.frames = OrderedDict()
        self.click_busy = False
        self.owns_device = False
        self.last_action = None
        self.last_lock = None
        self.threads = []

    def spawn(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        self.threads.append(t)
        t.start()
        return t

    def start(self):
        self.spawn(self.observe_loop)
        self.spawn(self.watchdog)

    def rpc(self, **req):
        answer = self.call(req)
        if not answer.get('ok'):
            raise RuntimeError(answer.get('error', 'UI service error'))
        return answer['result']

    def state(self):
        # Reads, HTTP polls, and browser reloads never count as activity.
        with self.mu:
            remaining = max(0, IDLE_SECONDS - (self.clock() - self.last_activity))
            return dict(mode=self.mode, message=self.message, device=SERIAL,
                        idle_seconds=IDLE_SECONDS,
                        remaining_seconds=round(remaining, 1) if self.mode in ('connecting', 'connected') else 0,
                        snapshot=self.snapshot,
                        frame_age_ms=round((self.clock() - self.captured_at) * 1000) if self.snapshot else None,
                        click_busy=self.click_busy, last_action=self.last_action,
                        last_lock=self.last_lock)

    def activity(self):
        with self.mu:
            if self.mode == 'connected':
                self.last_activity = self.clock()
            return {'accepted': self.mode == 'connected'}

    def connect(self):
        with self.mu:
            if self.mode in ('connecting', 'connected', 'locking'):
                raise ValueError('连接正在使用或收尾，请稍候')
            self.session += 1
            epoch = self.session
            self.mode = 'connecting'
            self.message = '正在连接平板并核实解锁状态…'
            self.last_activity = self.clock()
            self.snapshot = None
            self.frames.clear()
            self.last_action = None
            self.last_lock = None
        self.spawn(lambda: self._connect(epoch))
        return {'connecting': True}

    def _connect(self, epoch):
        try:
            with self.operation:
                status = self.rpc(action='status')
                if status.get('video_active'):
                    raise RuntimeError('识别服务正被其他任务使用，未接管平板')
                # Brightness helper is a second guard against another tablet run.
                with self.mu:
                    if self.session != epoch or self.mode != 'connecting':
                        return
                self.tablet.prepare()
                with self.mu:
                    self.owns_device = True
                    if self.session == epoch and self.mode == 'connecting':
                        self.mode = 'connected'
                        self.message = '实时连接 · 点击蓝色节点可操作平板'
        except Exception as exc:
            with self.mu:
                owned = self.owns_device or self.tablet.brightness_owned
                if self.session == epoch and self.mode == 'connecting' and not owned:
                    self.mode = 'error'
                    self.message = str(exc)
            if owned:
                self.begin_lock('连接失败：' + str(exc), allow_connecting=True)
            LOG.warning('connect: %s', exc)

    def save_frame(self, result, owner):
        """Keep exact displayed references valid across polling, with bounded owners."""
        obs = result['observationId']
        for old, entry in list(self.frames.items()):
            if entry['owner'] == owner:
                self.frames.pop(old)
        self.frames[obs] = dict(owner=owner, at=self.clock(), result=result)
        while len(self.frames) > OWNER_SLOTS:
            self.frames.popitem(last=False)
        self.snapshot = {key: value for key, value in result.items()
                         if key not in ('image', 'page_evidence', 'ocr')}
        self.captured_at = self.clock()

    def observe_loop(self):
        while not self.stop.wait(FRAME_SECONDS):
            with self.mu:
                if self.mode != 'connected' or self.click_busy:
                    continue
                epoch = self.session
            try:
                with self.operation:
                    with self.mu:
                        if self.mode != 'connected' or self.click_busy or self.session != epoch:
                            continue
                        owner = f'{self.owner_prefix}:{self.sequence % OWNER_SLOTS}'
                        self.sequence += 1
                    result = self.rpc(action='observe', detail='content', _owner=owner)
                    with self.mu:
                        if self.mode == 'connected' and self.session == epoch:
                            self.save_frame(result, owner)
            except Exception as exc:
                LOG.warning('observe: %s', exc)
                self.begin_lock('观察已停止：' + str(exc))

    def click(self, obs, ref):
        with self.mu:
            if self.mode != 'connected' or self.click_busy:
                raise ValueError('设备未连接或仍在处理上一次点击')
            entry = self.frames.get(obs)
            if not entry or self.clock() - entry['at'] > REFERENCE_SECONDS:
                raise ValueError('画面已过期，请使用刷新后的节点')
            node = next((n for n in walk(entry['result']['tree']) if n.get('ref') == ref), None)
            if not node or not node.get('actions') or node.get('enabled') is False or node.get('selected') is True:
                raise ValueError('该节点不可点击')
            self.last_activity = self.clock()
            self.click_busy = True
            epoch = self.session
        try:
            with self.operation:
                with self.mu:
                    if self.mode != 'connected' or self.session != epoch:
                        raise ValueError('连接已结束')
                action='scroll' if node.get('actions')==['scroll'] else 'click'
                result = self.rpc(action=action, observationId=obs, ref=ref, _owner=entry['owner'])
                with self.mu:
                    self.frames.clear()  # Never reuse a pre-action tree.
                    self.last_action = {k: result.get(k) for k in
                                        ('tapped', 'name', 'node_key', 'settled', 'transition_observed', 'timing_ms')}
                    if self.mode == 'connected' and result.get('observation'):
                        self.save_frame(result['observation'], entry['owner'])
                    if self.mode == 'connected':
                        self.message = '已点击：' + str(result.get('name', node['name']))
                return {'tapped': result.get('tapped'), 'name': result.get('name')}
        except Exception as exc:
            with self.mu:
                self.frames.clear()
                self.message = '点击未确认，未自动重试：' + str(exc)
            raise
        finally:
            with self.mu:
                self.click_busy = False

    def begin_lock(self, reason, allow_connecting=True):
        with self.mu:
            if self.mode not in (('connected', 'connecting') if allow_connecting else ('connected',)):
                return {'locking': False}
            self.mode = 'locking'
            self.message = reason + '；正在锁屏并释放采集…'
            self.frames.clear()
        self.spawn(lambda: self._lock(reason))
        return {'locking': True}

    def _lock(self, reason):
        errors = []
        lock_result = None
        # A slow observation must not postpone KEYCODE_SLEEP behind the RPC mutex.
        if self.owns_device:
            try:
                lock_result = self.tablet.lock()
            except Exception as exc:
                errors.append(str(exc))
        with self.operation:
            if self.owns_device or self.tablet.brightness_owned:
                if not lock_result:
                    try:
                        lock_result = self.tablet.lock()
                    except Exception as exc:
                        errors.append(str(exc))
                try:
                    self.rpc(action='release', _owner=self.owner_prefix)
                except Exception as exc:
                    errors.append('采集释放：' + str(exc))
                try:
                    self.tablet.restore()
                except Exception as exc:
                    errors.append('亮度恢复：' + str(exc))
            with self.mu:
                self.mode = 'error' if errors else 'locked'
                self.last_lock = dict(reason=reason, verified=bool(lock_result), errors=errors,
                                      time=time.strftime('%Y-%m-%d %H:%M:%S'))
                self.message = '；'.join(errors) if errors else reason + ' · 已核实锁屏，采集已停止'
                self.owns_device = False
                self.snapshot = None
                self.frames.clear()
        LOG.info('lock: %s, verified=%s, errors=%s', reason, bool(lock_result), errors)

    def watchdog_tick(self):
        with self.mu:
            due = self.mode in ('connecting', 'connected') and self.clock() - self.last_activity >= IDLE_SECONDS
            if due:
                # The mode switch and deadline check share the activity mutex.
                return self.begin_lock('60 秒无操作，自动锁屏')
        return None

    def watchdog(self):
        while not self.stop.wait(0.2):
            self.watchdog_tick()

    def close(self):
        self.begin_lock('服务停止，自动锁屏')
        self.stop.set()
        for t in list(self.threads):
            if t is not threading.current_thread():
                t.join(timeout=8)


class WebHandler(BaseHTTPRequestHandler):
    server_version = 'HSRSemantic/1'

    def log_message(self, fmt, *args):
        if '/api/state' not in str(args):
            LOG.info(fmt, *args)

    def reply(self, status, body, mime='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def local_host(self):
        return self.headers.get('Host') in self.server.hosts

    def do_GET(self):
        if not self.local_host():
            return self.reply(403, {'error': 'Localhost only'})
        path = urlsplit(self.path).path
        if path == '/api/state':
            return self.reply(200, self.server.console.state())
        if path == '/api/bootstrap':
            return self.reply(200, {'token': self.server.token})
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in files:
            name, mime = files[path]
            return self.reply(200, (HERE / name).read_bytes(), mime)
        self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if (not self.local_host() or origin != 'http://' + self.headers.get('Host', '')
                or not secrets.compare_digest(self.headers.get('X-HSR-Token', ''), self.server.token)
                or self.headers.get_content_type() != 'application/json'):
            return self.reply(403, {'error': 'Same-origin token required'})
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 4096:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            route = urlsplit(self.path).path
            console = self.server.console
            if route == '/api/connect':
                result = console.connect()
            elif route == '/api/activity':
                result = console.activity()
            elif route == '/api/lock':
                result = console.begin_lock('手动锁屏')
            elif route == '/api/click':
                result = console.click(str(data.get('observationId', '')), str(data.get('ref', '')))
            else:
                return self.reply(404, {'error': 'Not found'})
            self.reply(200, result)
        except Exception as exc:
            LOG.warning('request: %s', exc)
            self.reply(409, {'error': str(exc)})


class WebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, console):
        super().__init__(('127.0.0.1', port), WebHandler)
        self.console = console
        self.token = secrets.token_urlsafe(32)
        self.hosts = {f'localhost:{port}', f'127.0.0.1:{port}'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    console = Console()
    server = WebServer(args.port, console)
    def halt(*_):
        console.spawn(server.shutdown)
    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    console.start()
    LOG.info('Serving http://localhost:%s (explicit connect; idle lock %ss)', args.port, IDLE_SECONDS)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        console.close()
        server.server_close()


if __name__ == '__main__':
    main()
