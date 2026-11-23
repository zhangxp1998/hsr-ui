"""Contract tests for idle protection, exact rendered references and HTTP isolation."""
import copy
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import server

sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import Console, WebServer, OWNER_SLOTS


class DeviceConfigurationTest(unittest.TestCase):
    def test_missing_serial_never_reaches_adb(self):
        tablet=server.Tablet()
        with patch.object(server,'SERIAL',''), patch.object(tablet,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'HSR_UI_SERIAL'):tablet.prepare()
            run.assert_not_called()

    def test_locked_device_without_unlock_helper_does_not_dim_or_unlock(self):
        tablet=server.Tablet()
        with patch.object(server,'SERIAL','test-device'), \
             patch.dict(server.os.environ,{'HSR_UI_MODEL':'9469X','HSR_UI_PRODUCT':'Bellona_WF_GL','HSR_UI_UNLOCK_HELPER':''}), \
             patch.object(tablet,'run',return_value='test-device device model:9469X device:Bellona_WF_GL'), \
             patch.object(tablet,'adb',return_value='deviceLocked=1'), \
             patch.object(tablet,'brightness') as brightness:
            with self.assertRaisesRegex(RuntimeError,'Unlock manually'):tablet.prepare()
            brightness.assert_not_called();self.assertFalse(tablet.brightness_owned)

    def test_already_unlocked_device_needs_no_unlock_helper(self):
        tablet=server.Tablet()
        with patch.object(server,'SERIAL','test-device'), \
             patch.dict(server.os.environ,{'HSR_UI_MODEL':'9469X','HSR_UI_PRODUCT':'Bellona_WF_GL','HSR_UI_UNLOCK_HELPER':''}), \
             patch.object(tablet,'run',return_value='test-device device model:9469X device:Bellona_WF_GL') as run, \
             patch.object(tablet,'adb',return_value='deviceLocked=0'), \
             patch.object(tablet,'brightness') as brightness:
            tablet.prepare();brightness.assert_called_once_with('start')
            self.assertTrue(tablet.brightness_owned);self.assertEqual(run.call_count,1)


def frame(obs):
    return dict(observationId=obs, image='/private/frame.jpg', page='phone', dimensions=[2200, 1440],
                tree=dict(key='root', children=[dict(key='guide', name='指南', actions=['click'],
                                                   ref=obs+'-1', bounds=[1, 1, 10, 10])]))


class Tablet:
    brightness_owned = False
    def __init__(self):
        self.calls = []
    def prepare(self):
        self.brightness_owned = True
        self.calls.append('prepare')
    def lock(self):
        self.calls.append('lock')
        return {'locked': True}
    def restore(self):
        self.calls.append('restore')
        self.brightness_owned = False


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.requests = []
        self.tablet = Tablet()
        def rpc(req):
            self.requests.append(copy.deepcopy(req))
            if req['action'] == 'click':
                return {'ok': True, 'result': {'tapped': True, 'name': '指南', 'observation': frame('after')}}
            return {'ok': True, 'result': {'video_active': False}}
        self.c = Console(rpc, self.tablet, lambda: self.now)
        self.c.mode = 'connected'
        self.c.owns_device = True
        self.c.last_activity = self.now

    def tearDown(self):
        for t in self.c.threads:
            t.join(2)

    def test_poll_and_reload_do_not_extend_deadline(self):
        self.now = 159.9
        for _ in range(100):
            self.assertAlmostEqual(self.c.state()['remaining_seconds'], 0.1)
        self.assertIsNone(self.c.watchdog_tick())
        self.now = 160
        self.c.watchdog_tick()
        for t in self.c.threads: t.join(2)
        self.assertEqual(self.tablet.calls, ['lock', 'restore'])
        self.assertEqual(self.c.mode, 'locked')
        self.assertTrue(self.c.last_lock['verified'])
        self.assertIsNone(self.c.snapshot)

    def test_human_activity_extends_deadline(self):
        self.now = 155
        self.assertTrue(self.c.activity()['accepted'])
        self.now = 160
        self.assertEqual(self.c.state()['remaining_seconds'], 55)
        self.assertIsNone(self.c.watchdog_tick())

    def test_disconnected_server_does_not_lock_another_task(self):
        self.c.mode = 'disconnected'
        self.now = 10000
        self.assertIsNone(self.c.watchdog_tick())
        self.assertFalse(self.c.activity()['accepted'])
        self.assertEqual(self.tablet.calls, [])

    def test_click_keeps_exact_displayed_reference_across_poll(self):
        self.c.save_frame(frame('old'), 'slot0')
        self.c.save_frame(frame('new'), 'slot1')
        self.c.click('old', 'old-1')
        self.assertEqual(self.requests[0], dict(action='click', observationId='old', ref='old-1', _owner='slot0'))
        self.assertNotIn('new', self.c.frames)
        self.assertEqual(self.c.snapshot['observationId'], 'after')
        self.assertNotIn('image', self.c.snapshot)

    def test_scroll_node_dispatches_semantic_scroll_with_exact_reference(self):
        f=frame('scroll');f['tree']['children'][0]['actions']=['scroll']
        self.c.save_frame(f,'slot0')
        self.c.click('scroll','scroll-1')
        self.assertEqual(self.requests[0],dict(action='scroll',observationId='scroll',ref='scroll-1',_owner='slot0'))

    def test_stale_and_unknown_nodes_never_tap(self):
        self.c.save_frame(frame('a'), 'slot0')
        with self.assertRaises(ValueError): self.c.click('a', 'arbitrary-ref')
        self.now += 11
        with self.assertRaises(ValueError): self.c.click('a', 'a-1')
        self.assertEqual(self.requests, [])

    def test_disabled_and_selected_nodes_never_tap(self):
        for field in ('enabled', 'selected'):
            f = frame('a'); f['tree']['children'][0][field] = field == 'selected'
            self.c.save_frame(f, 'slot0')
            with self.assertRaises(ValueError): self.c.click('a', 'a-1')
        self.assertEqual(self.requests, [])

    def test_failed_click_never_retries(self):
        self.c.save_frame(frame('a'), 'slot0')
        def failed(req):
            self.requests.append(req)
            return {'ok': False, 'error': 'page_changed_reobserve'}
        self.c.call = failed
        with self.assertRaises(RuntimeError): self.c.click('a', 'a-1')
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.c.click_busy)
        self.assertEqual(len(self.c.frames), 0)

    def test_history_bounded_and_rotating_owner_replaces_old_frame(self):
        for i in range(40): self.c.save_frame(frame(str(i)), 'slot'+str(i % OWNER_SLOTS))
        self.assertEqual(len(self.c.frames), OWNER_SLOTS)
        self.assertNotIn('0', self.c.frames)
        self.assertEqual(len(set(f['owner'] for f in self.c.frames.values())), OWNER_SLOTS)

    def test_idle_lock_does_not_wait_for_slow_capture(self):
        self.c.operation.acquire()
        self.c.begin_lock('test')
        for _ in range(100):
            if 'lock' in self.tablet.calls: break
            threading.Event().wait(.005)
        self.assertIn('lock', self.tablet.calls)
        self.assertEqual(self.c.mode, 'locking')
        self.assertFalse(self.c.activity()['accepted'])
        self.c.operation.release()

    def test_connect_completion_after_cancel_is_locked(self):
        self.c.mode = 'connecting'
        self.c.owns_device = False
        self.c.operation.acquire()
        self.c.begin_lock('cancel connect')
        self.tablet.brightness_owned = True
        self.c.owns_device = True
        self.c.operation.release()
        for t in self.c.threads: t.join(2)
        self.assertEqual(self.tablet.calls, ['lock', 'restore'])
        self.assertEqual(self.c.mode, 'locked')


class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.c = Console(lambda req: {'ok': True, 'result': {}}, Tablet())
        self.server = WebServer(0, self.c)
        self.port = self.server.server_port
        self.host = f'127.0.0.1:{self.port}'
        self.server.hosts = {self.host}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        conn.request(method, path, body=body, headers=headers or {})
        res = conn.getresponse(); result = res.status, res.read(); conn.close(); return result

    def test_get_is_inert_and_localhost_only(self):
        self.assertEqual(self.request('GET', '/api/state')[0], 200)
        self.assertEqual(self.c.mode, 'disconnected')
        self.assertEqual(self.request('GET', '/', {'Host': 'evil.example'})[0], 403)

    def test_click_requires_same_origin_and_token(self):
        h = {'Content-Type': 'application/json', 'Origin': 'https://evil.example', 'X-HSR-Token': self.server.token}
        self.assertEqual(self.request('POST', '/api/connect', h, '{}')[0], 403)
        h['Origin'] = 'http://' + self.host; h.pop('X-HSR-Token')
        self.assertEqual(self.request('POST', '/api/connect', h, '{}')[0], 403)
        self.assertEqual(self.c.mode, 'disconnected')

    def test_only_semantic_endpoints_and_no_file_access(self):
        h = {'Content-Type': 'application/json', 'Origin': 'http://' + self.host, 'X-HSR-Token': self.server.token}
        self.assertEqual(self.request('POST', '/api/tap', h, '{"x":1,"y":2}')[0], 404)
        self.assertEqual(self.request('GET', '/../service.py')[0], 404)
        self.assertEqual(self.request('GET', '/api/bootstrap')[0], 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
