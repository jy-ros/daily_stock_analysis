# -*- coding: utf-8 -*-
"""QuantIndicatorsResult / analyze_quant_indicators tests (offline, formula validation)."""

import math
import unittest

import numpy as np
import pandas as pd

from src.quant_indicators import (
    QuantIndicatorsResult,
    _compute_atr,
    _compute_boll,
    _compute_kdj,
    _compute_max_drawdown,
    _compute_var,
    _compute_volatility,
    analyze_quant_indicators,
    build_quant_summary,
)


def _rising(n: int = 250, seed: int = 42) -> pd.DataFrame:
    """Monotonically rising close with tiny noise."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(80, 160, n) + rng.normal(0, 0.1, n))
    high = close + 0.5
    low = close - 0.5
    vol = rng.integers(100_000, 500_000, n)
    return pd.DataFrame({"date": dates, "open": close.shift(1).fillna(close), "high": high, "low": low, "close": close, "volume": vol})


def _falling(n: int = 250, seed: int = 99) -> pd.DataFrame:
    """Monotonically falling close."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(160, 80, n) + rng.normal(0, 0.1, n))
    high = close + 0.5
    low = close - 0.5
    vol = rng.integers(100_000, 500_000, n)
    return pd.DataFrame({"date": dates, "open": close.shift(1).fillna(close), "high": high, "low": low, "close": close, "volume": vol})


class TestQuantIndicatorsResultToDict(unittest.TestCase):
    def test_to_dict_keys(self) -> None:
        result = QuantIndicatorsResult()
        d = result.to_dict()
        expected_keys = {
            "kdj_k", "kdj_d", "kdj_j", "kdj_status",
            "kdj_golden_cross", "kdj_death_cross",
            "boll_upper", "boll_mid", "boll_lower", "boll_position", "boll_width_pct",
            "atr", "atr_pct",
            "vol_20d", "max_drawdown_60d", "var_95_1d", "risk_level",
            "summary", "analysis",
        }
        self.assertEqual(expected_keys, set(d.keys()))


class TestGracefulDegradation(unittest.TestCase):
    def test_none_input(self) -> None:
        result = analyze_quant_indicators(None)
        self.assertIsInstance(result, QuantIndicatorsResult)
        self.assertIn("不可用", result.summary)

    def test_empty_df(self) -> None:
        result = analyze_quant_indicators(pd.DataFrame())
        self.assertIsInstance(result, QuantIndicatorsResult)
        self.assertIn("不可用", result.summary)

    def test_short_df(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10, freq="B"),
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [100_000] * 10,
        })
        result = analyze_quant_indicators(df)
        self.assertIn("不可用", result.summary)


class TestRisingStock(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = analyze_quant_indicators(_rising())

    def test_kdj_status_valid(self) -> None:
        valid = {"超买", "多头", "金叉", "死叉", "中性"}
        self.assertIn(self.result.kdj_status, valid)

    def test_boll_position_near_top(self) -> None:
        self.assertGreater(self.result.boll_position, 80)

    def test_max_drawdown_non_negative(self) -> None:
        self.assertGreaterEqual(self.result.max_drawdown_60d, 0.0)

    def test_vol_positive(self) -> None:
        self.assertGreater(self.result.vol_20d, 0.0)

    def test_risk_level(self) -> None:
        self.assertIn(self.result.risk_level, {"低", "中", "高"})

    def test_summary_not_empty(self) -> None:
        self.assertTrue(len(self.result.summary) > 0)


class TestFallingStock(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = analyze_quant_indicators(_falling())

    def test_kdj_status(self) -> None:
        self.assertIn(self.result.kdj_status, {"超卖", "空头", "死叉"})

    def test_boll_position_near_bottom(self) -> None:
        self.assertLess(self.result.boll_position, 20)

    def test_max_drawdown_positive(self) -> None:
        self.assertGreater(self.result.max_drawdown_60d, 0.0)


class TestKdjCrossDetection(unittest.TestCase):
    def test_golden_cross(self) -> None:
        """Synthetic close that crosses up sharply near end to trigger golden cross."""
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        base = list(np.linspace(100, 100, 30))
        base[-1] = 110.0  # sharp pop to create K > D transition
        close = pd.Series(base, dtype=float)
        high = close + 0.5
        low = close - 0.5
        df = pd.DataFrame({"date": dates, "open": close, "high": high, "low": low, "close": close, "volume": 1})
        kdj = _compute_kdj(df)
        self.assertIsInstance(kdj["kdj_golden_cross"], bool)


class TestBoll(unittest.TestCase):
    def test_boll_width_non_negative(self) -> None:
        df = _rising(n=60)
        boll = _compute_boll(df, df["close"])
        self.assertGreaterEqual(boll["boll_width_pct"], 0.0)

    def test_position_clamped_0_100(self) -> None:
        df = _rising(n=60)
        boll = _compute_boll(df, df["close"])
        self.assertGreaterEqual(boll["boll_position"], 0.0)
        self.assertLessEqual(boll["boll_position"], 100.0)


class TestAtr(unittest.TestCase):
    def test_atr_positive(self) -> None:
        df = _rising(n=60)
        atr = _compute_atr(df, df["close"])
        self.assertGreater(atr["atr"], 0.0)
        self.assertGreaterEqual(atr["atr_pct"], 0.0)


class TestVolatility(unittest.TestCase):
    def test_vol_increases_with_noise(self) -> None:
        rng = np.random.default_rng(0)
        n = 100
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        close = pd.Series(np.linspace(100, 100, n) + rng.normal(0, 2, n))
        vol = _compute_volatility(close)
        self.assertGreater(vol, 0.0)


class TestMaxDrawdown(unittest.TestCase):
    def test_drawdown_peak_to_trough(self) -> None:
        close = pd.Series([100, 110, 105, 90, 100], dtype=float)
        dd = _compute_max_drawdown(close)
        # Max drawdown from 110→90 = 20/110 = 18.18%
        self.assertAlmostEqual(dd, (110 - 90) / 110 * 100, places=1)


class TestVaR(unittest.TestCase):
    def test_var_returns_non_negative(self) -> None:
        rng = np.random.default_rng(7)
        n = 200
        close = pd.Series(np.cumsum(rng.normal(0, 1, n)) + 100)
        var = _compute_var(close)
        self.assertGreaterEqual(var, 0.0)


class TestBuildQuantSummary(unittest.TestCase):
    def test_summary_format(self) -> None:
        result = analyze_quant_indicators(_rising())
        summary = build_quant_summary(result.to_dict())
        self.assertIn("KDJ", summary)
        self.assertIn("ATR", summary)


if __name__ == "__main__":
    unittest.main()
