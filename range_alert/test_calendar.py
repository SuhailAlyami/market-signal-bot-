"""Trading-day vs holiday behaviour of every scheduled job, using the official NYSE calendar. No network:
any market-data fetch on a non-session day fails the test."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT/'range_alert'), str(ROOT/'shadow_tradingagents')]
import daily_range as D  # noqa: E402
import evaluate_range as E  # noqa: E402
import run_shadow as S  # noqa: E402

UTC = timezone.utc
NO_NET = mock.patch('urllib.request.urlopen', side_effect=AssertionError('network used on a non-session day'))
# 13:13 UTC = pre-open (08:13 NY in winter); 21:37 UTC = after close.
HOLIDAYS = ['2026-11-26', '2026-12-25', '2027-01-01', '2027-01-18']
WEEKEND = ['2026-11-14', '2026-11-15']


def at(day, hh, mm):
    y, m, d = map(int, day.split('-'))
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def fake_closes(symbol, before, rng='3mo'):
    return [(date(2026, 10, 1+i), 6000.0+i) for i in range(25)]


class CalendarTests(unittest.TestCase):
    def test_calendar_knows_holidays_and_half_days(self):
        for d in HOLIDAYS + WEEKEND:
            self.assertFalse(D.CAL.is_session(d), d)
        for d in ('2026-11-25', '2026-11-27', '2026-12-24', '2026-12-31'):
            self.assertTrue(D.CAL.is_session(d), d)

    def test_morning_alert_silent_on_holidays_and_weekends(self):
        with NO_NET:
            for d in HOLIDAYS + WEEKEND:
                self.assertIsNone(D.build(now=at(d, 13, 13)), d)

    def test_evening_target_is_last_closed_session_so_holidays_add_nothing_new(self):
        # Delivery is deduplicated per evaluated session, so on a holiday/weekend the target is a session
        # that was already delivered and nothing new is sent.
        self.assertEqual(E.last_closed(at('2026-11-26', 21, 37)), '2026-11-25')   # Thanksgiving
        self.assertEqual(E.last_closed(at('2026-11-15', 21, 37)), '2026-11-13')   # Sunday
        self.assertEqual(E.last_closed(at('2026-12-25', 21, 37)), '2026-12-24')   # Christmas

    def test_evening_target_waits_for_early_close_not_later(self):
        # 2026-11-27 closes 13:00 New York = 18:00 UTC; it becomes the target from 18:15 UTC.
        self.assertEqual(E.last_closed(at('2026-11-27', 18, 10)), '2026-11-25')
        self.assertEqual(E.last_closed(at('2026-11-27', 18, 20)), '2026-11-27')

    def test_shadow_run_skips_holidays_and_weekends(self):
        with NO_NET, tempfile.TemporaryDirectory() as tmp:
            for d in HOLIDAYS + WEEKEND:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(S.main(tmp, now=at(d, 11, 7)), 0)
                self.assertIn('NO_SESSION_TODAY', buf.getvalue(), d)

    def test_morning_call_never_sent_after_the_open_unforced(self):
        with NO_NET:
            self.assertEqual(D.build(now=at('2026-11-17', 15, 0)), 'LATE')   # 10:00 New York

    def test_notes_half_day(self):
        notes = D.calendar_notes(date(2026, 11, 27))
        self.assertTrue(any('جلسة قصيرة' in n and '13:00' in n and '21:00' in n for n in notes), notes)
        self.assertEqual(D.calendar_notes(date(2026, 11, 24)), [])

    def test_notes_day_before_holiday(self):
        notes = D.calendar_notes(date(2026, 11, 25))
        self.assertTrue(any('2026-11-26' in n and 'الجلسة التالية 2026-11-27' in n for n in notes), notes)
        notes = D.calendar_notes(date(2027, 1, 15))  # Friday before MLK Monday: weekend is not listed as a holiday
        self.assertTrue(any('2027-01-18' in n and '2027-01-16' not in n for n in notes), notes)
        self.assertEqual(D.calendar_notes(date(2026, 11, 20)), [])  # ordinary Friday

    def test_morning_message_includes_notes_on_half_day(self):
        with mock.patch.object(D, 'closes', fake_closes), \
             mock.patch.object(D, 'last_close', lambda s, b: (date(2026, 11, 25), 16.0)):
            msg = D.build(now=at('2026-11-27', 13, 13))
        self.assertIn('جلسة قصيرة', msg)


if __name__ == '__main__':
    unittest.main()
