import unittest
from cfd_causal_reference import Bar
from cfd_v4_event_audit import audit


def signal():
    bars=[Bar(i*60000,100,100.5,99.5,100) for i in range(30)]
    return bars+[Bar(1800000,100,102,99.9,101.9)]


class AuditTests(unittest.TestCase):
    def test_pending_then_target_next_open_reference(self):
        bars=signal()
        self.assertEqual(audit(bars)['counts']['pending'],1)
        result=audit(bars+[Bar(1860000,102,103.2,101.9,103)])
        self.assertEqual(result['counts']['target'],1)
        self.assertEqual(result['events'][0]['entry'],102)

    def test_gap_is_not_filled(self):
        result=audit(signal()+[Bar(1920000,102,104,101,103)])
        self.assertEqual(result['counts']['gap'],1)

    def test_unknown_same_bar_order_is_ambiguous(self):
        result=audit(signal()+[Bar(1860000,102,104,100,102)])
        self.assertEqual(result['counts']['ambiguous'],1)

    def test_invalid_input_order_rejected(self):
        bars=signal()
        with self.assertRaises(ValueError):
            audit(bars+[bars[-1]])

    def test_end_exclusive(self):
        self.assertEqual(audit(signal(),end_ms=1860000)['counts']['signals'],0)


if __name__ == '__main__':
    unittest.main()
