"""Complete causal ES rule plans; research performance remains unvalidated."""
from datetime import datetime
import math

from hunter_research import DEFAULT_PARAMS
from strategy_rules import features as causal_features,VERSION


def complete_plan(event, frame, tick_size=0.25):
    if event.get('symbol') not in ('ES', 'ES=F','SPX') or event.get('state') != 'TRIGGER':
        return None, 'not_confirmed_es'
    try:
        # Use only the event's completed bar and its past, never later/partial bars.
        end = datetime.fromisoformat(event['bar_end'])
        if end.tzinfo is None: return None, 'naive_bar_time'
        import pandas as pd
        start = pd.Timestamp(end)-pd.Timedelta(minutes=1)
        index = frame.index.get_loc(start)
        features = causal_features(frame, index)
        if features is None: return None, 'insufficient_causal_history'
        sign = 1 if event['direction']=='UP' else -1 if event['direction']=='DOWN' else 0
        if not sign: return None, 'invalid_direction'
        atr = float(features['atr']); price = float(features['close'])
        if (not all(math.isfinite(x) and x>0 for x in (atr,price)) or
            features['rvol'] < DEFAULT_PARAMS['rvol'] or
            sign*features['trend_5'] <= DEFAULT_PARAMS['trend'] or
            sign*features['trend_15'] < 0 or sign*features['move'] <= 0):
            return None, 'confirmation_filters_failed'
        stop = float(event['invalidation'])
        if not math.isfinite(tick_size) or tick_size<=0:return None,'invalid_tick_size'
        low = math.floor((price-0.05*atr)/tick_size)*tick_size
        high = math.ceil((price+0.05*atr)/tick_size)*tick_size
        stop = (math.floor(stop/tick_size) if sign>0 else math.ceil(stop/tick_size))*tick_size
        risk = high-stop if sign>0 else stop-low
        if not tick_size <= risk <= 2*atr or not (stop<low if sign>0 else stop>high):
            return None, 'risk_or_entry_invalid'
        anchor = high if sign>0 else low
        targets = [anchor+sign*risk, anchor+sign*2*risk]
        if min(targets)<=0: return None,'nonpositive_target'
        return {**event, 'symbol':'SPX' if event['symbol']=='SPX' else 'ES=F', 'signal_status':'COMPLETE',
            'notify_eligible':True,'analysis_only':True,'research_readiness':'NOT_READY',
            'entry_zone':[low,high],'stop_loss':stop,'targets':targets,
            'reason': ('تأكيد إغلاقين خلف المستوى بهامش 0.1 ATR؛ '
                       f"حجم نسبي {features['rvol']:.2f} واتجاه 5 و15 دقيقة متوافق. "
                       'الدخول ±0.05 ATR، والهدفان 1R و2R؛ قاعدة تجريبية غير مثبتة الأداء.'),
            'rule_version':VERSION,'plan_atr':atr}, None
    except (KeyError,ValueError,TypeError,OverflowError):
        return None,'incomplete_or_invalid_plan_inputs'
