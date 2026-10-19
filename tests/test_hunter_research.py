"""Adversarial research correctness checks, never evidence of predictive edge."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from hunter_research import (
    ResearchConfig, _evaluate, benchmark, causal_features, chronological_splits,
    eligible_indices, feature_frame, fit_parameters, movement_events, score_signals, session_inventory,
    validate_bars,
)


def minute_bars(start="2026-10-12T13:30:00Z", periods=120):
    index = pd.date_range(start, periods=periods, freq="min")
    rng = np.random.default_rng(16)
    close = 100+np.cumsum(rng.normal(0, .035, periods))
    opening = np.r_[100., close[:-1]]
    return pd.DataFrame({"Open": opening, "High": np.maximum(opening, close)+.04,
                         "Low": np.minimum(opening, close)-.04,
                         "Close": close, "Volume": rng.integers(100, 500, periods)}, index=index)


def rth_days(count=8):
    return pd.concat([minute_bars(pd.Timestamp(day).tz_localize("America/New_York").replace(hour=9, minute=30).tz_convert("UTC"), 390)
                      for day in pd.bdate_range("2026-10-01", periods=count)])


class ResearchValidationTests(unittest.TestCase):
    def test_rejects_naive_duplicate_unsorted_and_subminute_timestamps(self):
        bars = minute_bars()
        for index in (bars.index.tz_localize(None), bars.index[::-1],
                      bars.index+pd.Timedelta(seconds=1),
                      bars.index[:1].append(bars.index[:-1])):
            bad = bars.copy()
            bad.index = index
            with self.assertRaises(ValueError):
                validate_bars(bad)

    def test_timestamp_resolution_does_not_change_observable_horizons(self):
        bars = minute_bars()
        features = feature_frame(bars)
        indices = list(range(30, 100))
        expected = eligible_indices(bars, features, indices, ResearchConfig())
        bars.index = bars.index.as_unit("us")
        self.assertEqual(expected, eligible_indices(bars, feature_frame(bars), indices, ResearchConfig()))

    def test_parameter_fit_ignores_invalid_training_features(self):
        features = pd.DataFrame({"rvol": [1.1, 1.3, 10000.], "valid": [True, True, False]})
        result = fit_parameters(features, [0, 1, 2], {"rvol_quantile": .5})
        self.assertAlmostEqual(result["rvol"], 1.2)

    def test_future_mutation_does_not_change_features_or_decision_prefix(self):
        bars = rth_days(2)
        index = 80
        expected = causal_features(bars, index)
        mutated = bars.copy()
        mutated.iloc[index+1:, :4] *= 100
        mutated.iloc[index+1:, 4] = 0
        pd.testing.assert_series_equal(pd.Series(expected), pd.Series(causal_features(mutated, index)))
        pd.testing.assert_series_equal(feature_frame(bars).iloc[index],
                                       feature_frame(mutated).iloc[index])
        pd.testing.assert_series_equal(feature_frame(bars.iloc[:index+1]).iloc[-1],
                                       feature_frame(bars).iloc[index])

    def test_opening_range_is_unknown_before_completed_15_minutes(self):
        bars = minute_bars(periods=90)
        features = feature_frame(bars)
        self.assertTrue(features.opening_high.iloc[:14].isna().all())
        # 09:44 bar closes at 09:45; it is already a completed opening range.
        # The conservative public feature becomes available at the 09:45 bar.
        self.assertTrue(np.isnan(features.opening_high.iloc[14]))
        self.assertEqual(features.opening_high.iloc[15], bars.High.iloc[:15].max())
        bars.iloc[5, bars.columns.get_loc("Volume")] = 0
        features = feature_frame(bars)
        self.assertTrue(features.opening_high.isna().all())

    def test_invalid_prior_session_extreme_cannot_survive_as_level(self):
        index = pd.date_range("2026-10-11T22:00:00Z", periods=1380, freq="min")
        first = minute_bars(index[0], len(index))
        second = minute_bars("2026-10-12T22:00:00Z", 60)
        data = pd.concat([first, second])
        self.assertEqual(feature_frame(data).prior_high.iloc[-1], first.High.max())
        data.iloc[100, data.columns.get_loc("High")] = 1000000
        data.iloc[100, data.columns.get_loc("Volume")] = 0
        features = feature_frame(data)
        self.assertTrue(np.isnan(features.prior_high.iloc[-1]))
        self.assertLess(features.level_high.iloc[-1], 200)

    def test_splits_are_chronological_embargoed_and_exclude_current_session(self):
        bars = rth_days()
        as_of = bars.index[-1]+pd.Timedelta(seconds=30)  # Last minute not complete.
        splits, inventory = chronological_splits(bars, "rth", as_of, 10)
        self.assertFalse(inventory[-1]["complete"])
        self.assertLess(max(splits["train"])+10, min(splits["validation"]))
        self.assertLess(max(splits["validation"])+10, min(splits["test"]))
        self.assertTrue(set(splits["train"]).isdisjoint(splits["validation"]))
        current = str(bars.index[-1].tz_convert("America/New_York").date())
        self.assertNotIn(current, [str(bars.index[i].tz_convert("America/New_York").date()) for i in splits["test"]])

    def test_dst_session_boundaries_use_wall_clock_hours(self):
        # Fall-back was Nov 1; the Sunday 18:00 open is 23:00 UTC.
        bars = minute_bars("2026-11-01T23:00:00Z", 1380)
        inventory = session_inventory(bars, "all", pd.Timestamp("2026-11-02T23:00:00Z"))
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]["session"], "2026-11-02")
        self.assertTrue(inventory[0]["complete"])
        spring = minute_bars("2026-03-08T22:00:00Z", 1380)
        self.assertTrue(session_inventory(spring, "all", pd.Timestamp("2026-03-09T22:00:00Z"))[0]["complete"])


class EventScoringTests(unittest.TestCase):
    def setUp(self):
        self.bars = minute_bars()
        self.config = ResearchConfig(bootstrap_samples=50)
        self.indices = list(range(30, 90))
        self.event = {"event_id": 0, "anchor_index": 35, "onset_index": 38,
                      "target_index": 40, "direction": 1,
                      "onset_time": (self.bars.index[38]+pd.Timedelta(minutes=1)).isoformat(),
                      "target_time": (self.bars.index[40]+pd.Timedelta(minutes=1)).isoformat()}

    def signal(self, index, direction=1):
        return {"index": index, "direction": direction,
                "detected_at": (self.bars.index[index]+pd.Timedelta(minutes=1)).isoformat()}

    def test_one_to_one_matching_misses_and_late_target_bar_rejected(self):
        other = {**self.event, "event_id": 1, "anchor_index": 50,
                 "onset_index": 53, "target_index": 55,
                 "onset_time": (self.bars.index[53]+pd.Timedelta(minutes=1)).isoformat()}
        signals = [self.signal(35), self.signal(36), self.signal(40)]
        result = score_signals([self.event, other], signals, self.bars,
                               self.indices, "rth", self.config)
        self.assertEqual(result["matched_events"], 1)
        self.assertEqual(result["precision"], 1/3)
        self.assertEqual(result["recall"], .5)
        self.assertEqual(result["missed_events"], 1)
        self.assertEqual(result["false_alarms"], 2)
        self.assertEqual(result["median_lead_minutes"], 3)
        self.assertEqual(signals[-1]["event_id"], None)

    def test_delay_can_destroy_apparent_early_detection(self):
        zero = score_signals([self.event], [self.signal(35)], self.bars,
                             self.indices, "rth", self.config)
        delayed = score_signals([self.event], [self.signal(35)], self.bars,
                                self.indices, "rth", self.config,
                                availability_delay_minutes=5)
        self.assertEqual(zero["early_event_recall"], 1)
        self.assertEqual(delayed["early_event_recall"], 0)
        self.assertEqual(delayed["missed_events"], 1)

    def test_post_onset_pre_target_trigger_does_not_count_as_early(self):
        result = score_signals([self.event], [self.signal(39)], self.bars,
                               self.indices, "rth", self.config)
        self.assertEqual(result["precision"], 1)
        self.assertEqual(result["early_precision"], 0)
        self.assertEqual(result["early_event_recall"], 0)
        self.assertEqual(result["median_lead_minutes"], -1)

    def test_future_outage_censors_outcome_but_never_reschedules_signal(self):
        data = self.bars.copy()
        data.iloc[35, data.columns.get_loc("Volume")] = 0
        features = feature_frame(data)
        with patch("hunter_research.candidate_signal", return_value=1):
            metrics, _, signals = _evaluate(data, features, self.indices,
                                            "pre_level", {}, "rth", self.config)
        self.assertEqual(signals[0]["index"], 30)
        self.assertFalse(signals[0]["outcome_observable"])
        self.assertGreater(metrics["censored_signals"], 0)
        self.assertEqual(metrics["candidate_signals_total"], len(signals))

    def test_no_signal_baseline_does_not_get_vacuous_perfect_precision(self):
        first = score_signals([self.event], [], self.bars, self.indices, "rth", self.config)
        second = score_signals([self.event], [], self.bars, self.indices, "rth", self.config)
        self.assertIsNone(first["precision"])
        self.assertEqual(first["recall"], 0)
        self.assertEqual(first["false_alarms"], 0)
        self.assertEqual(first["missed_events"], 1)
        self.assertEqual(first["session_bootstrap_95"], second["session_bootstrap_95"])

    def test_ambiguous_intrabar_two_sided_event_is_excluded(self):
        bars = pd.DataFrame({"Open": [100.]*50, "High": [100.01]*50,
                             "Low": [99.99]*50, "Close": [100.]*50,
                             "Volume": [100.]*50}, index=self.bars.index[:50])
        bars.iloc[31, bars.columns.get_loc("High")] = 101
        bars.iloc[31, bars.columns.get_loc("Low")] = 99
        features = feature_frame(bars)
        self.assertEqual(movement_events(bars, features, [30], self.config), [])


class HoldoutIntegrityTests(unittest.TestCase):
    def test_holdout_values_cannot_change_fit_shortlist_or_selection(self):
        bars = rth_days()
        as_of = pd.Timestamp("2026-10-20T00:00:00Z")
        grid = [{"id": "pre", "method": "pre_level", "params": {"rvol_quantile": .5}},
                {"id": "acc", "method": "acceleration", "params": {"rvol_quantile": .75}}]
        config = ResearchConfig(bootstrap_samples=10)
        with patch("hunter_research.parameter_grid", return_value=grid):
            original, _ = benchmark(bars, "fixture", "rth", as_of, config)
        splits, _ = chronological_splits(bars, "rth", as_of, config.horizon)
        mutated = bars.copy()
        first_test_session_start = (min(splits["test"])//390)*390
        mutated.iloc[first_test_session_start:, :4] *= 10
        mutated.iloc[first_test_session_start:, 4] *= 100
        with patch("hunter_research.parameter_grid", return_value=grid):
            changed, _ = benchmark(mutated, "fixture", "rth", as_of, config)
        self.assertEqual(original["selected"], changed["selected"])
        self.assertEqual(original["parameter_search_train_only"], changed["parameter_search_train_only"])
        self.assertEqual(original["validation_shortlist"], changed["validation_shortlist"])
        self.assertEqual(original["status"], "NOT READY")
        self.assertIn("10", original["holdout_availability_delay_sensitivity"])


if __name__ == "__main__":
    unittest.main()
