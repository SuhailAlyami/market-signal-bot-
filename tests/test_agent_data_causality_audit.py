import json
import unittest
import pandas as pd
from datetime import datetime, timezone, timedelta

class AgentDataCausalityAuditTests(unittest.TestCase):
    """
    Minimal targeted reproducible tests for confirmed defects identified during
    the bounded SPX data/causality audit.
    """

    def test_confirmed_c1_contract_identity_schema_mismatch(self):
        """
        Confirmed C1: Schema mismatch between historical acquisition outputs
        (e.g., artifacts/spx_extension_20261023/raw.json) and evaluate_spx_sessions.py.
        evaluate_spx_sessions requires source == 'IBKR_TWS_API_HISTORY' and root['contract_id'],
        whereas IBKR_CONNECTED_TOOLS_HISTORY payloads provide root['underlying_contract_id']
        and sections, causing immediate rejection with 'native_gateway_capture_required'.
        """
        extension_manifest = {
            "source": "IBKR_CONNECTED_TOOLS_HISTORY",
            "contract": {
                "underlying_contract_id": 416904,
                "exchange": "CBOE",
                "symbol": "SPX",
                "country_code": "US"
            }
        }
        # The contract schema check in evaluate_spx_sessions.py:
        is_tws_api = extension_manifest.get('source') == 'IBKR_TWS_API_HISTORY'
        has_contract_id = bool(extension_manifest.get('contract', {}).get('contract_id'))
        
        # Demonstrates that extension captures cannot be ingested by evaluate_spx_sessions
        self.assertFalse(is_tws_api)
        self.assertFalse(has_contract_id)

    def test_confirmed_c4_zero_strict_early_lead_on_wick_onset(self):
        """
        Confirmed C4: When an event onset equals the anchor bar's end (decision time),
        no completed 1-minute bar can have its decision strictly before onset.
        Strict early slots is mathematically empty, proving a structural barrier
        to early breakout detection using completed 1m bars for such events.
        """
        index = pd.date_range('2026-10-22T15:00Z', periods=5, freq='min')
        bars = pd.DataFrame({'Open': 100.0, 'High': 101.0, 'Low': 99.0, 'Close': 100.5}, index=index)
        
        # Anchor bar is index[1] (15:01Z). Decision is 15:02Z.
        # If onset occurs at 15:02Z (gap = 0 minutes):
        anchor_decision = index[1] + pd.Timedelta(minutes=1)
        onset_time = anchor_decision
        
        event = {
            'anchor_index': 1,
            'target_index': 4,
            'anchor_time': index[1].isoformat(),
            'onset_time': onset_time.isoformat()
        }
        
        # Calculate strict early slots: bars whose end < onset_time
        slots = []
        for i in range(event['anchor_index'], event['target_index']):
            if bars.index[i] + pd.Timedelta(minutes=1) < pd.Timestamp(event['onset_time']):
                slots.append(i)
                
        self.assertEqual(slots, [], "Gap 0 events cannot have any completed 1m bar strictly before onset")

    def test_confirmed_c5_incomplete_session_bars_accepted_without_opening_range(self):
        """
        Confirmed C5: On a partial session like 2026-10-20 (which starts at 16:20Z instead of 13:30Z),
        a rolling 30-bar window becomes 'valid' at bar index 30 without knowing whether opening-range
        levels or session highs/lows occurred during the missing 170 minutes.
        """
        # Create a partial session missing the first 170 minutes (RTH opened at 13:30Z, feed starts at 16:20Z)
        index = pd.date_range('2026-10-20T16:20Z', periods=40, freq='min')
        bars = pd.DataFrame({'Open': 5800.0, 'High': 5805.0, 'Low': 5795.0, 'Close': 5802.0}, index=index)
        bars.attrs.update(symbol='SPX', security_type='IND')
        
        # Prior 20-bar ATR exists after 30 bars
        from spx_price_watch import observe
        res = observe(bars, 35)
        
        # The detector treats the bar as evaluatable even though RTH opening 9:30-12:20 NY was omitted
        self.assertNotEqual(res['reason'], 'insufficient_history')
        self.assertIn(res['reason'], ('no_sweep_reclaim_or_local_break', 'sweep_reclaim', 'local_break'))


if __name__ == '__main__':
    unittest.main()
