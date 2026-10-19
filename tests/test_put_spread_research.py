import unittest
from datetime import date, timedelta
from put_spread_research import Leg, evaluate

class PutSpreadTests(unittest.TestCase):
    def test_combination_can_lose_and_debit_reduces_credit(self):
        today=date(2026,10,19)
        legs=[Leg(100,"P","SELL",4),Leg(95,"P","BUY",2),
              Leg(110,"P","BUY",12),Leg(105,"P","SELL",8)]
        result=evaluate(legs,today+timedelta(days=45),today)
        self.assertEqual(result["dte"],45)
        self.assertEqual(result["net_credit_after_fees"],-200)
        self.assertLess(result["max_loss"],0)
    def test_rejects_non_45dte(self):
        today=date(2026,10,19)
        with self.assertRaises(ValueError):
            evaluate([Leg(100,"P","SELL",4)]*4,today+timedelta(days=1),today)
    def test_fees_reduce_profit(self):
        today=date(2026,10,19)
        legs=[Leg(100,"P","SELL",4),Leg(95,"P","BUY",2),
              Leg(110,"P","BUY",12),Leg(105,"P","SELL",8)]
        a=evaluate(legs,today+timedelta(days=45),today)
        b=evaluate(legs,today+timedelta(days=45),today,fee_per_contract=1)
        self.assertEqual(b["max_profit"],a["max_profit"]-4)

if __name__=="__main__":
    unittest.main()
