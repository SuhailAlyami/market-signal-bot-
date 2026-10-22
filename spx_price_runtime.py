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
        return events+super()._process_bar(symbol, data, index, now)
