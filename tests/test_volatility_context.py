import unittest,datetime,copy
from volatility_context import realized_volatility,prior_daily_context
class Tests(unittest.TestCase):
 def data(self):return {'time':[(datetime.date(2026,9,1)+datetime.timedelta(days=i)).isoformat()+'T13:30:00Z' for i in range(40)],'close':[100+i*.1 for i in range(40)]}
 def test_future_and_same_day_excluded(self):
  d=self.data();date=datetime.date(2026,9,25);a=prior_daily_context(d,date);d['close'][24:]=[10000]*16;self.assertEqual(a,prior_daily_context(d,date))
 def test_missing_iv_not_filled(self):self.assertIsNone(prior_daily_context(self.data(),datetime.date(2026,10,1))['iv_contract_decimal'])
 def test_invalid_prices(self):
  with self.assertRaises(ValueError):realized_volatility([100,0,110])
 def test_flat_price_zero(self):self.assertEqual(realized_volatility([100]*21),0)
if __name__=='__main__':unittest.main()
