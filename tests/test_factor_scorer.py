# -*- coding: utf-8 -*-
"""FactorScorer tests (offline)."""

import unittest

from src.factor_scorer import (
    CompositeFactorScore,
    FactorWeights,
    _score_atr,
    _score_boll,
    _score_kdj,
    _score_vol_risk,
    compute_composite_factor_score,
)


class TestKdjScoring(unittest.TestCase):
    def test_overbought_low_score(self) -> None:
        score, reason, level = _score_kdj("超买", 95, 110)
        self.assertLess(score, 40)
        self.assertEqual(level, "偏空")

    def test_oversold_high_score(self) -> None:
        score, reason, level = _score_kdj("超卖", 5, -10)
        self.assertGreater(score, 60)
        self.assertEqual(level, "偏多")

    def test_golden_cross(self) -> None:
        score, reason, level = _score_kdj("金叉", 60, 70)
        self.assertGreater(score, 60)

    def test_death_cross(self) -> None:
        score, reason, level = _score_kdj("死叉", 40, 30)
        self.assertLess(score, 40)


class TestBollScoring(unittest.TestCase):
    def test_near_lower_band(self) -> None:
        score, reason, level = _score_boll(10, 20)
        self.assertGreater(score, 70)

    def test_near_upper_band(self) -> None:
        score, reason, level = _score_boll(90, 20)
        self.assertLess(score, 30)

    def test_narrow_bandwidth_bonus(self) -> None:
        score1, _, _ = _score_boll(50, 5)
        score2, _, _ = _score_boll(50, 30)
        self.assertGreater(score1, score2)


class TestVolRiskScoring(unittest.TestCase):
    def test_low_risk_high_score(self) -> None:
        score, reason, level = _score_vol_risk("低", 20, 5)
        self.assertGreater(score, 60)

    def test_high_risk_low_score(self) -> None:
        score, reason, level = _score_vol_risk("高", 60, 25)
        self.assertLess(score, 30)

    def test_large_drawdown_penalty(self) -> None:
        score1, _, _ = _score_vol_risk("中", 35, 5)
        score2, _, _ = _score_vol_risk("中", 35, 25)
        self.assertGreater(score1, score2)


class TestAtrScoring(unittest.TestCase):
    def test_high_atr_low_score(self) -> None:
        score, reason, level = _score_atr(7)
        self.assertLess(score, 40)

    def test_low_atr_high_score(self) -> None:
        score, reason, level = _score_atr(1)
        self.assertGreater(score, 60)


class TestCompositeScoring(unittest.TestCase):
    def test_none_quant(self) -> None:
        result = compute_composite_factor_score(None)
        self.assertIsInstance(result, CompositeFactorScore)
        self.assertEqual(result.total_score, 50.0)

    def test_bullish_quant(self) -> None:
        quant = {
            "kdj_status": "金叉", "kdj_k": 60, "kdj_j": 70,
            "boll_position": 30, "boll_width_pct": 15,
            "risk_level": "低", "vol_20d": 20, "max_drawdown_60d": 5,
            "atr_pct": 1.5,
        }
        result = compute_composite_factor_score(quant)
        self.assertGreater(result.total_score, 60)
        self.assertTrue(len(result.factors) == 4)

    def test_bearish_quant(self) -> None:
        quant = {
            "kdj_status": "超买", "kdj_k": 95, "kdj_j": 110,
            "boll_position": 90, "boll_width_pct": 30,
            "risk_level": "高", "vol_20d": 60, "max_drawdown_60d": 25,
            "atr_pct": 7,
        }
        result = compute_composite_factor_score(quant)
        self.assertLess(result.total_score, 40)
        self.assertTrue(len(result.risk_warnings) > 0)

    def test_custom_weights(self) -> None:
        quant = {
            "kdj_status": "金叉", "kdj_k": 60, "kdj_j": 70,
            "boll_position": 50, "boll_width_pct": 20,
            "risk_level": "低", "vol_20d": 20, "max_drawdown_60d": 5,
            "atr_pct": 2,
        }
        # All weight on KDJ → should match KDJ score
        w = FactorWeights(kdj_weight=100, boll_weight=0, vol_risk_weight=0, atr_weight=0)
        result = compute_composite_factor_score(quant, weights=w)
        kdj_score, _, _ = _score_kdj("金叉", 60, 70)
        self.assertAlmostEqual(result.total_score, kdj_score, places=1)


if __name__ == "__main__":
    unittest.main()
