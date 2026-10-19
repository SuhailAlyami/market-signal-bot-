import unittest
from fvg_bollinger_research import detect

class DetectorTests(unittest.TestCase):
    def test_no_future_leakage(self):
        bars=[dict(open=100,high=101,low=99,close=100,volume=100) for _ in range(24)]
        bars[22]=dict(open=100,high=101,low=99,close=100,volume=100)
        bars[23]=dict(open=101,high=121,low=101.5,close=120,volume=500)
        original=detect(bars,length=20)
        extended=detect(bars+[dict(open=1,high=2,low=0.5,close=1,volume=99999)],length=20)
        self.assertEqual(original,[s for s in extended if s.index < len(bars)])
        self.assertEqual(len(original),1)
        self.assertEqual(original[0].direction,"UP")
    def test_fvg_requirement(self):
        bars=[dict(open=100,high=101,low=99,close=100,volume=100) for _ in range(24)]
        bars[23]=dict(open=100,high=121,low=99,close=120,volume=500)
        self.assertEqual(len(detect(bars,length=20)),1)
        self.assertEqual(detect(bars,length=20,require_fvg=True),[])
    def test_zero_volume_rejected(self):
        bars=[dict(open=100,high=101,low=99,close=100,volume=0) for _ in range(24)]
        self.assertEqual(detect(bars),[])
    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            detect([],length=2)

if __name__=="__main__":
    unittest.main()
