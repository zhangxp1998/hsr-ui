"""Synthetic contracts; no account fixtures, models, device connection or input."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from output import agent_response, decision_state
from service import Service
from vision import walk


def observation():
    return dict(page='test.page', observationId='test-observation', live=True,
                state={'count': 0, 'enabled': False, 'unknown': None},
                tree={'key': 'root', 'children': [dict(key='content/one', name='Example card',
                children=[dict(key='button', ref='test-ref', name='Enter', role='button',
                               actions=['click'], effect='navigation', enabled=None,
                               bounds=[20, 20, 80, 60])])]})


class Contracts(unittest.TestCase):
    def test_compact_projection_preserves_meaning_not_geometry(self):
        full={'ok': True, 'result': observation()};original=copy.deepcopy(full)
        value=agent_response(full, {'action':'observe'})['result']
        self.assertEqual(value['nodes'][0], {'ref':'test-ref','name':'Example card / Enter','effect':'navigation'})
        self.assertEqual(value['state'], {'count':0,'enabled':False,'unknown':None})
        self.assertNotIn('tree',value);self.assertEqual(full,original)
        self.assertIn('tree',agent_response(full,{'format':'full'})['result'])

    def test_unknowns_and_unknown_pages(self):
        self.assertEqual(decision_state({'count':0,'checked':None,'claimed':False}),
                         {'count':0,'checked':None,'claimed':False})
        full={'ok':True,'result':observation()};full['result']['page']='unknown'
        self.assertEqual(agent_response(full,{'action':'observe'})['result']['nodes'],[])

    def test_scroll_and_uncertain_settling_remain_explicit(self):
        obs=observation();node=obs['tree']['children'][0]['children'][0]
        node['actions']=['scroll'];node['effect']='navigation'
        full={'ok':True,'result':dict(scrolled=True,settled=False,transition_observed=False,observation=obs)}
        out=agent_response(full,{'action':'scroll'})['result']
        self.assertFalse(out['settled']);self.assertTrue(out['scrolled'])
        self.assertEqual(out['observation']['nodes'][0]['actions'],['scroll'])

    def test_dry_run_never_advertises_a_fresh_internal_ref(self):
        node=observation()['tree']['children'][0]['children'][0]
        full={'ok':True,'result':dict(tapped=False,validated=True,node=node,point=[1,2])}
        out=agent_response(full,{'action':'click','dryRun':True})['result']
        self.assertTrue(out['validated']);self.assertNotIn('ref',out['node'])
        self.assertNotIn('point',out)

    def test_common_coordinate_comparison_accepts_jitter_not_changes(self):
        rng=np.random.default_rng(7);a=rng.integers(0,256,(1440,2200,3),dtype=np.uint8)
        node=observation()['tree']['children'][0]['children'][0]
        shifted=copy.deepcopy(node);shifted['bounds']=[22,21,82,61]
        self.assertEqual(Service.target_delta(a,a,node,shifted),0)
        moved=copy.deepcopy(node);moved['bounds']=[40,20,100,60]
        with self.assertRaisesRegex(ValueError,'geometry_changed'):Service.target_delta(a,a,node,moved)
        changed=copy.deepcopy(node);changed['effect']='purchase'
        with self.assertRaisesRegex(ValueError,'semantics_changed'):Service.target_delta(a,a,node,changed)
        erased=a.copy();erased[19:62,19:83]=0
        with self.assertRaisesRegex(ValueError,'appearance_changed'):Service.target_delta(a,erased,node,shifted)

    def make_service(self):
        original=observation();original['image']='synthetic.jpg'
        node=original['tree']['children'][0]['children'][0]
        svc=Service.__new__(Service);svc.walk=walk;svc.current={'owner':'test-observation'};svc.video=None
        svc.records={'test-observation':dict(owner='owner',created=time.monotonic(),result=original,nodes={'test-ref':node})}
        calls=[]
        svc.tap=SimpleNamespace(screenshot_size=lambda p:(2200,1440),
             choose_point=lambda b,s:(50,40),map_to_device=lambda p,s,f,serial:(p,s))
        svc.capture_module=SimpleNamespace(adb=lambda *a,**k:calls.append(a))
        after=copy.deepcopy(original);after['page']='test.after'
        svc.observe=lambda req,owner,internal=False:copy.deepcopy(original if internal else after)
        return svc,calls

    def test_reference_owner_replay_expiry(self):
        svc,calls=self.make_service();req={'observationId':'test-observation','ref':'test-ref'}
        with self.assertRaisesRegex(ValueError,'stale'):svc.validate_reference(req,'different-owner')
        record=svc.records['test-observation'];record['result']['live']=False
        with self.assertRaisesRegex(ValueError,'replay'):svc.validate_reference(req,'owner')
        record['result']['live']=True;record['created']-=91
        with self.assertRaisesRegex(ValueError,'expired'):svc.validate_reference(req,'owner')
        self.assertEqual(calls,[])

    def test_login_server_cannot_change_between_observation_and_input(self):
        svc,calls=self.make_service()
        old=svc.records['test-observation']['result']
        old['page']='login.title';old['state']={'login':{'server':'Asia'}}
        fresh=copy.deepcopy(old);fresh['state']['login']['server']='Europe'
        svc.observe=lambda *a,**k:fresh
        with self.assertRaisesRegex(ValueError,'login_server_changed'):
            svc.click(dict(action='click',observationId='test-observation',ref='test-ref'),'owner')
        self.assertEqual(calls,[])

    def test_current_uid_cannot_change_or_disappear_before_input(self):
        for page in ('field','supply.monthly'):
            for uid in ('999999999',None):
                with self.subTest(page=page,uid=uid):
                    svc,calls=self.make_service();old=svc.records['test-observation']['result']
                    old['page']=page;old['state']={'uid':'888888888'}
                    fresh=copy.deepcopy(old);fresh['state']['uid']=uid
                    svc.observe=lambda *a,**k:fresh
                    with self.assertRaisesRegex(ValueError,'account_uid_changed'):
                        svc.click(dict(action='click',observationId='test-observation',ref='test-ref'),'owner')
                    self.assertEqual(calls,[])

    def test_cancel_dry_run_and_one_input_consumption(self):
        req=dict(action='click',observationId='test-observation',ref='test-ref')
        canvas=np.zeros((1440,2200,3),dtype=np.uint8)
        with patch('cv2.imread',return_value=canvas),patch('service.time.sleep'):
            svc,calls=self.make_service()
            self.assertTrue(svc.click(dict(req,dryRun=True),'owner')['validated']);self.assertEqual(calls,[])
            with self.assertRaisesRegex(ValueError,'cancelled'):svc.click(req,'owner',alive=lambda:False)
            self.assertEqual(calls,[])
            self.assertTrue(svc.click(req,'owner')['tapped']);self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'stale'):svc.click(req,'owner')
            self.assertEqual(len(calls),1)

    def test_idle_close_does_not_revoke_refs_but_release_does(self):
        svc,calls=self.make_service();svc.close_video();self.assertTrue(svc.current)
        svc.release();self.assertEqual(svc.current,{})

    def test_unconfigured_device_fails_before_adb(self):
        p=Path(__file__).resolve().parents[1]/'scripts/hsr-tablet-tap.py'
        sys.path.insert(0,str(p.parent));spec=importlib.util.spec_from_file_location('tap_test',p)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with patch.object(mod.subprocess,'run',side_effect=AssertionError('ADB must not run')):
            with self.assertRaisesRegex(ValueError,'HSR_UI_SERIAL'):mod.validate_tablet('')


if __name__=='__main__':unittest.main(verbosity=2)
