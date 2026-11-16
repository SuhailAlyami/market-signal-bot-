"""Send the shadow decision for a session to Telegram (no LLM key in this step)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'range_alert'))
from daily_range import send  # noqa: E402

AR = {'Buy': 'شراء', 'Overweight': 'زيادة', 'Hold': 'احتفاظ', 'Underweight': 'تخفيف', 'Sell': 'بيع', 'REVIEW': 'غير واضح'}
files = sorted(Path(sys.argv[1]).glob('*.json'))
if not files:
    print('NO_RECORD'); sys.exit(0)
r = json.loads(files[-1].read_text())
msg = (f"🤖 TradingAgents (تجريبي، لا ينفّذ أوامر) — SPY جلسة {r['session']}\n"
       f"القرار: {AR.get(r['signal'], r['signal'])} ({r['signal']})\n"
       f"بيانات حتى إغلاق {r['data_as_of_close']} | نموذج: {r['deep_model']}\n"
       "يُسجَّل للمقارنة لاحقًا مع حركة SPY الفعلية و\"صاعد دائمًا\". ليس توصية.")
print(msg)
if not send(msg):
    sys.exit(1)
