"""Account identity requires a complete, current, confident visible UID label."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from navigation_state import read_uid


class Reader:
    def __init__(self,lines):self.lines=lines
    def recognize_line(self,*a,**k):return self.lines


class IdentityContract(unittest.TestCase):
    def test_current_complete_label(self):
        self.assertEqual(read_uid(Reader([dict(name='UID:888888888',score=.99)]),None),'888888888')
    def test_missing_or_ambiguous_label_is_unknown(self):
        line=dict(name='UID:888888888',score=.99)
        for lines in ([],[line,line]):self.assertIsNone(read_uid(Reader(lines),None))
    def test_low_confidence_is_unknown(self):
        self.assertIsNone(read_uid(Reader([dict(name='UID:888888888',score=.94)]),None))
    def test_digits_without_complete_uid_label_are_unknown(self):
        for text in ('888888888','UID:88888888','UID:8888888888','UID:88888888O','otherUID:888888888'):
            self.assertIsNone(read_uid(Reader([dict(name=text,score=.99)]),None))


if __name__=='__main__':unittest.main()
