"""SPX-only shadow lifecycle; an opposite setup cannot be blocked by old state."""
from datetime import timedelta

from hunter_runtime import HunterRuntime
from spx_price_watch import candidate, market_open


class SPXPriceRuntime(HunterRuntime):
    def __init__(self, state_path, journal_path):
        super().__init__(state_path, journal_path, symbols=('SPX',),
                         detector=candidate, market_is_open=market_open)

    def _process_bar(self, symbol, data, index, now):
        state = self.state['symbols'].setdefault(symbol, {})
        end = (data.index[index].to_pydatetime()+timedelta(minutes=1)).isoformat()
        if state.get('last_bar_end') and end <= state['last_bar_end']:
            return []
        active = state.get('active')
        found = candidate(data, index)
        events = []
        if active and found and found['direction'] != active['direction']:
            events.append(self._event(symbol, 'EXIT' if active['phase'] == 'TRIGGER'
                                      else 'INVALIDATION', active, now, end,
                                      float(data.iloc[index].Close), 'opposite_price_watch'))
            state.pop('active')
            state['cooldown_until'] = end
        transitions = events+super()._process_bar(symbol, data, index, now)
        # Distinguish a silent detector from a detected candidate held by the
        # lifecycle. This is evidence only; it cannot authorize a notification.
        phase = state.get('active', {}).get('phase')
        if found is None:
            reason = 'no_candidate'
        elif any(e['state'] == 'SETUP' for e in transitions):
            reason = 'setup_created'
        elif phase:
            reason = 'active_' + phase.lower()
        else:
            reason = 'cooldown'
        self._record({'record_type': 'candidate_disposition', 'symbol': symbol,
                      'bar_end': end, 'detected_at': now.isoformat(),
                      'candidate': found, 'reason': reason,
                      'transition_states': [e['state'] for e in transitions],
                      'active_state': phase, 'readiness': 'NOT_READY',
                      'delivery_blocker': 'research_notifications_disabled',
                      'notify_eligible': False, 'analysis_only': True})
        return transitions
