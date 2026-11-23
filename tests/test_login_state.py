"""Synthetic OCR contract tests, without game images or account identities."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from login_state import read_login


def line(name):
    return dict(name=name, score=.99, bounds=[2, 2, 18, 18], source='roi_ocr')


class Reader:
    def __init__(self):
        self.lines={'login.start':[line('开始游戏')], 'login.server':[line('Asia')],
                    'login.rail':[line(x) for x in ['公告','设置','登出']], 'login.entry':[]}
    def ocr(self,im,box,tag,**kwargs):return self.lines[tag]
    def node(self,key,name,**kwargs):return dict(key=key,name=name,**kwargs)


class LoginContract(unittest.TestCase):
    def setUp(self):self.v=Reader();self.im=np.full((20,20,3),255,dtype=np.uint8)
    def test_entry_retains_unknown_account(self):
        self.v.lines['login.start']=[];self.v.lines['login.entry']=[line('点击进入')]
        self.v.lines['login.server']=[]
        r=read_login(self.v,self.im)
        self.assertEqual(r['page'],'login.entry');self.assertIsNone(r['state']['login']['uid'])
        self.assertIsNone(r['state']['login']['server'])
        self.assertEqual(r['nodes'][0]['effect'],'enter_game')
    def test_server_is_observed_not_assumed(self):
        self.v.lines['login.server']=[line('Europe')]
        self.assertEqual(read_login(self.v,self.im)['state']['login']['server'],'Europe')
    def test_missing_or_ambiguous_anchor_refuses_action(self):
        for tag in ('login.start','login.server','login.rail'):
            with self.subTest(tag=tag):
                v=Reader();v.lines[tag]=[];self.assertIsNone(read_login(v,self.im))
        self.v.lines['login.server'].append(line('Europe'))
        self.assertIsNone(read_login(self.v,self.im))
    def test_low_confidence_or_dimmed_start_refuses_action(self):
        self.v.lines['login.start'][0]['score']=.89
        self.assertIsNone(read_login(self.v,self.im))
        self.assertIsNone(read_login(Reader(),self.im//3))


if __name__=='__main__':unittest.main()
