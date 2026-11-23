"""State contracts use synthetic pixels; real HUD fixtures remain private."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from battle_state import read_battle


class Reader:
    def __init__(self):
        self.pause=True;self.auto=True;self.turn='我方行动中';self.sprites=self
        self.assets={'IconAuto':{'path':'synthetic-original'}}
    def match(self,name,*a,**k):
        if not (self.pause if name=='IconBattlePause' else self.auto):return None
        return dict(accepted=True,bounds=[2110,50,2134,74] if name=='IconBattlePause' else [1960,50,1996,74])
    def ocr(self,*a,**k):
        return [dict(name=self.turn,score=.99,bounds=[1800,1280,2100,1340],source='roi_ocr')]
    def node(self,key,name,role,bounds,source,action,**more):
        return dict(key=key,name=name,role=role,bounds=bounds,source=source,actions=['click'] if action else [],**more)


class BattleContract(unittest.TestCase):
    def setUp(self):
        self.v=Reader();self.im=np.zeros((1440,2200,3),dtype=np.uint8)
        self.mask=patch('battle_state._alpha',return_value=np.full((20,32),255,np.uint8))
        self.mask.start();self.addCleanup(self.mask.stop)
    def test_missing_pause_or_turn_never_means_active(self):
        self.v.pause=False;self.assertIsNone(read_battle(self.v,self.im))
        self.v.pause=True;self.v.turn='挑战成功';self.assertIsNone(read_battle(self.v,self.im))
    def test_white_dark_and_missing_auto_are_unknown_not_off(self):
        for color in (255,80,0):
            self.im[50:74,1960:1996]=color;r=read_battle(self.v,self.im)
            self.assertIsNone(r['state']['battle']['auto_enabled']);self.assertEqual(r['nodes'],[])
        self.v.auto=False;r=read_battle(self.v,self.im)
        self.assertIsNone(r['state']['battle']['auto_enabled']);self.assertEqual(r['nodes'],[])
    def test_positive_gold_has_checked_state_not_result(self):
        self.im[50:74,1960:1996]=[140,215,235]
        r=read_battle(self.v,self.im)
        self.assertTrue(r['state']['battle']['auto_enabled']);self.assertTrue(r['nodes'][0]['checked'])
        self.assertNotIn('result',r['state'])


if __name__=='__main__':unittest.main()
