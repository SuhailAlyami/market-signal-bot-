from datetime import datetime, timedelta, timezone
import pandas as pd
from early_globex_watch import detect_early, globex_active

UTC = timezone.utc

def test_sunday_globex_opens_at_18_et():
    assert not globex_active(datetime(2026, 10, 18, 21, 59, tzinfo=UTC))
    assert globex_active(datetime(2026, 10, 18, 22, 0, tzinfo=UTC))

def test_stale_bars_rejected():
    idx = pd.date_range("2026-10-18T22:00:00Z", periods=14, freq="5min")
    data = pd.DataFrame({"High": [100]*13+[105], "Low": [99]*14,
                         "Close": [99.5]*13+[104], "Volume": [100]*13+[250]}, index=idx)
    assert detect_early("ES=F", data, datetime(2026, 10, 18, 23, 10, tzinfo=UTC)) is not None
    assert detect_early("ES=F", data, datetime(2026, 10, 18, 23, 30, tzinfo=UTC)) is None

def test_incomplete_bar_never_used():
    idx = pd.date_range("2026-10-18T22:00:00Z", periods=14, freq="5min")
    data = pd.DataFrame({"High": [100]*13+[105], "Low": [99]*14,
                         "Close": [99.5]*13+[104], "Volume": [100]*13+[250]}, index=idx)
    assert detect_early("ES=F", data, datetime(2026, 10, 18, 23, 5, tzinfo=UTC)) is None
