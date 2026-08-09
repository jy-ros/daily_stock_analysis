# -*- coding: utf-8 -*-
"""Tests for Phase 2.2: Portfolio simulation enhancement (fees/slippage, multi-day tracking, portfolio metrics)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
import unittest

from src.core.backtest_engine import (
    BacktestEngine,
    EvaluationConfig,
    PortfolioMetrics,
    TransactionCostConfig,
)


@dataclass(frozen=True)
class FakeBar:
    date: date
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]


class TestTransactionCostConfig(unittest.TestCase):
    def test_default_values(self):
        cfg = TransactionCostConfig()
        self.assertAlmostEqual(cfg.commission_rate, 0.0003)
        self.assertAlmostEqual(cfg.min_commission, 5.0)
        self.assertAlmostEqual(cfg.slippage_pct, 0.001)

    def test_custom_values(self):
        cfg = TransactionCostConfig(commission_rate=0.001, min_commission=10.0, slippage_pct=0.005)
        self.assertAlmostEqual(cfg.commission_rate, 0.001)
        self.assertAlmostEqual(cfg.min_commission, 10.0)
        self.assertAlmostEqual(cfg.slippage_pct, 0.005)


class TestComputeFeesAndSlippage(unittest.TestCase):
    def test_no_config_returns_zero(self):
        result = BacktestEngine._compute_fees_and_slippage(
            entry_price=100.0, exit_price=110.0, cost_config=None
        )
        self.assertAlmostEqual(result["total_fees"], 0.0)
        self.assertAlmostEqual(result["commission"], 0.0)
        self.assertAlmostEqual(result["slippage_cost"], 0.0)

    def test_commission_uses_min_when_proportional_is_lower(self):
        # entry 100 * 0.0003 = 0.03 < min_commission 5.0, so use 5.0
        cfg = TransactionCostConfig(commission_rate=0.0003, min_commission=5.0, slippage_pct=0.0)
        result = BacktestEngine._compute_fees_and_slippage(
            entry_price=100.0, exit_price=100.0, cost_config=cfg
        )
        # commission = 5.0 (entry) + 5.0 (exit) = 10.0
        self.assertAlmostEqual(result["commission"], 10.0)
        self.assertAlmostEqual(result["slippage_cost"], 0.0)
        self.assertAlmostEqual(result["total_fees"], 10.0)

    def test_commission_uses_proportional_when_higher(self):
        # entry 10000 * 0.0003 = 3.0 < 5.0 => still min
        # entry 100000 * 0.0003 = 30.0 > 5.0 => use proportional
        cfg = TransactionCostConfig(commission_rate=0.0003, min_commission=5.0, slippage_pct=0.0)
        result = BacktestEngine._compute_fees_and_slippage(
            entry_price=100000.0, exit_price=100000.0, cost_config=cfg
        )
        # commission = 30.0 (entry) + 30.0 (exit) = 60.0
        self.assertAlmostEqual(result["commission"], 60.0)

    def test_slippage_applied_to_both_sides(self):
        cfg = TransactionCostConfig(commission_rate=0.0, min_commission=0.0, slippage_pct=0.001)
        result = BacktestEngine._compute_fees_and_slippage(
            entry_price=100.0, exit_price=110.0, cost_config=cfg
        )
        # slippage = 100*0.001 + 110*0.001 = 0.1 + 0.11 = 0.21
        self.assertAlmostEqual(result["slippage_cost"], 0.21, places=4)
        self.assertAlmostEqual(result["total_fees"], 0.21, places=4)

    def test_combined_commission_and_slippage(self):
        cfg = TransactionCostConfig(commission_rate=0.0003, min_commission=5.0, slippage_pct=0.001)
        result = BacktestEngine._compute_fees_and_slippage(
            entry_price=100.0, exit_price=110.0, cost_config=cfg
        )
        # commission = 5.0 + 5.0 = 10.0
        # slippage = 0.1 + 0.11 = 0.21
        # total = 10.21
        self.assertAlmostEqual(result["total_fees"], 10.21, places=4)


class TestEvaluateSingleWithCostConfig(unittest.TestCase):
    """Test that evaluate_single returns new Phase 2.2 fields."""

    def setUp(self):
        self.config = EvaluationConfig(eval_window_days=5, neutral_band_pct=2.0)
        self.cost_config = TransactionCostConfig(
            commission_rate=0.0003, min_commission=5.0, slippage_pct=0.001
        )
        self.bars = [
            FakeBar(date=date(2025, 1, 2), high=105.0, low=99.0, close=103.0),
            FakeBar(date=date(2025, 1, 3), high=107.0, low=101.0, close=106.0),
            FakeBar(date=date(2025, 1, 6), high=108.0, low=102.0, close=104.0),
            FakeBar(date=date(2025, 1, 7), high=110.0, low=103.0, close=109.0),
            FakeBar(date=date(2025, 1, 8), high=112.0, low=105.0, close=111.0),
        ]

    def test_long_position_returns_phase22_fields(self):
        result = BacktestEngine.evaluate_single(
            operation_advice="买入",
            analysis_date=date(2025, 1, 1),
            start_price=100.0,
            forward_bars=self.bars,
            stop_loss=None,
            take_profit=None,
            config=self.config,
            cost_config=self.cost_config,
        )
        self.assertEqual(result["eval_status"], "completed")
        self.assertEqual(result["position_recommendation"], "long")
        self.assertIsNotNone(result["simulated_entry_date"])
        self.assertEqual(result["simulated_entry_date"], date(2025, 1, 1))
        self.assertIsNotNone(result["simulated_exit_date"])
        self.assertIsNotNone(result["holding_days"])
        self.assertEqual(result["holding_days"], 5)
        self.assertIsNotNone(result["transaction_costs"])
        self.assertIn("total_fees", result["transaction_costs"])
        self.assertIn("commission", result["transaction_costs"])
        self.assertIn("slippage_cost", result["transaction_costs"])
        self.assertIsNotNone(result["net_simulated_return_pct"])
        # Net return should be less than gross return due to fees
        gross = result["simulated_return_pct"]
        net = result["net_simulated_return_pct"]
        if gross is not None:
            self.assertLessEqual(net, gross)

    def test_cash_position_returns_none_for_new_fields(self):
        result = BacktestEngine.evaluate_single(
            operation_advice="卖出",
            analysis_date=date(2025, 1, 1),
            start_price=100.0,
            forward_bars=self.bars,
            stop_loss=None,
            take_profit=None,
            config=self.config,
            cost_config=self.cost_config,
        )
        self.assertEqual(result["position_recommendation"], "cash")
        self.assertIsNone(result["simulated_entry_date"])
        self.assertIsNone(result["simulated_exit_date"])
        self.assertIsNone(result["holding_days"])
        self.assertIsNone(result["transaction_costs"])
        self.assertIsNone(result["net_simulated_return_pct"])

    def test_no_cost_config_still_returns_new_fields(self):
        result = BacktestEngine.evaluate_single(
            operation_advice="买入",
            analysis_date=date(2025, 1, 1),
            start_price=100.0,
            forward_bars=self.bars,
            stop_loss=None,
            take_profit=None,
            config=self.config,
            cost_config=None,
        )
        # Even without cost_config, fields should be present
        self.assertIsNotNone(result["simulated_entry_date"])
        self.assertIsNotNone(result["holding_days"])
        # With no cost_config, net == gross
        self.assertEqual(result["net_simulated_return_pct"], result["simulated_return_pct"])
        self.assertEqual(result["transaction_costs"]["total_fees"], 0.0)

    def test_stop_loss_exit_date_matches_first_hit_date(self):
        bars_with_stop = [
            FakeBar(date=date(2025, 1, 2), high=105.0, low=95.0, close=96.0),  # low <= stop
            FakeBar(date=date(2025, 1, 3), high=107.0, low=101.0, close=106.0),
            FakeBar(date=date(2025, 1, 6), high=108.0, low=102.0, close=104.0),
            FakeBar(date=date(2025, 1, 7), high=110.0, low=103.0, close=109.0),
            FakeBar(date=date(2025, 1, 8), high=112.0, low=105.0, close=111.0),
        ]
        result = BacktestEngine.evaluate_single(
            operation_advice="买入",
            analysis_date=date(2025, 1, 1),
            start_price=100.0,
            forward_bars=bars_with_stop,
            stop_loss=97.0,
            take_profit=None,
            config=self.config,
            cost_config=self.cost_config,
        )
        self.assertTrue(result["hit_stop_loss"])
        self.assertEqual(result["first_hit"], "stop_loss")
        self.assertEqual(result["simulated_exit_date"], date(2025, 1, 2))
        self.assertEqual(result["holding_days"], 1)


class TestComputePortfolioMetrics(unittest.TestCase):
    """Test compute_portfolio_metrics aggregation."""

    def _make_result(self, **overrides):
        defaults = {
            "eval_status": "completed",
            "position_recommendation": "long",
            "simulated_return_pct": 5.0,
            "net_simulated_return_pct": 4.5,
            "holding_days": 5,
            "transaction_costs": {"total_fees": 50.0, "commission": 40.0, "slippage_cost": 10.0},
            "stock_return_pct": 5.0,
            "outcome": "win",
            "direction_correct": True,
            "hit_stop_loss": False,
            "hit_take_profit": False,
            "first_hit": "neither",
            "first_hit_trading_days": None,
            "operation_advice": "买入",
        }
        defaults.update(overrides)

        class Obj:
            pass

        obj = Obj()
        for k, v in defaults.items():
            setattr(obj, k, v)
        return obj

    def test_empty_results(self):
        metrics = BacktestEngine.compute_portfolio_metrics(results=[])
        self.assertEqual(metrics.total_trades, 0)
        self.assertIsNone(metrics.cumulative_net_return_pct)

    def test_single_trade(self):
        r = self._make_result(net_simulated_return_pct=5.0, holding_days=5, transaction_costs={"total_fees": 10.0})
        metrics = BacktestEngine.compute_portfolio_metrics(results=[r])
        self.assertEqual(metrics.total_trades, 1)
        self.assertAlmostEqual(metrics.cumulative_net_return_pct, 5.0)
        self.assertAlmostEqual(metrics.avg_net_return_pct, 5.0)
        self.assertEqual(metrics.net_win_count, 1)
        self.assertEqual(metrics.net_loss_count, 0)
        self.assertAlmostEqual(metrics.net_win_rate_pct, 100.0)

    def test_multiple_trades_cumulative(self):
        r1 = self._make_result(net_simulated_return_pct=10.0, holding_days=5, transaction_costs={"total_fees": 10.0})
        r2 = self._make_result(net_simulated_return_pct=-5.0, holding_days=3, transaction_costs={"total_fees": 8.0})
        r3 = self._make_result(net_simulated_return_pct=8.0, holding_days=7, transaction_costs={"total_fees": 12.0})
        metrics = BacktestEngine.compute_portfolio_metrics(results=[r1, r2, r3])
        self.assertEqual(metrics.total_trades, 3)
        # cumulative: (1+0.1)*(1-0.05)*(1+0.08) - 1 = 1.1*0.95*1.08 - 1 = 1.1286 - 1 = 12.86%
        self.assertAlmostEqual(metrics.cumulative_net_return_pct, 12.86, places=2)
        self.assertEqual(metrics.net_win_count, 2)
        self.assertEqual(metrics.net_loss_count, 1)
        self.assertAlmostEqual(metrics.net_win_rate_pct, 66.67, places=2)
        self.assertAlmostEqual(metrics.total_fees, 30.0)
        self.assertAlmostEqual(metrics.avg_holding_days, 5.0)

    def test_max_drawdown(self):
        # Trade 1: +10%, Trade 2: -20%, Trade 3: +15%
        r1 = self._make_result(net_simulated_return_pct=10.0, holding_days=5, transaction_costs={"total_fees": 5.0})
        r2 = self._make_result(net_simulated_return_pct=-20.0, holding_days=5, transaction_costs={"total_fees": 5.0})
        r3 = self._make_result(net_simulated_return_pct=15.0, holding_days=5, transaction_costs={"total_fees": 5.0})
        metrics = BacktestEngine.compute_portfolio_metrics(results=[r1, r2, r3])
        # equity: 100 -> 110 -> 88 -> 101.2
        # max drawdown from 110 to 88 = (110-88)/110 = 20%
        self.assertAlmostEqual(metrics.max_drawdown_pct, 20.0, places=2)

    def test_only_cash_positions_excluded(self):
        cash = self._make_result(position_recommendation="cash", net_simulated_return_pct=None)
        metrics = BacktestEngine.compute_portfolio_metrics(results=[cash])
        self.assertEqual(metrics.total_trades, 0)


class TestBacktestResultLikeProtocol(unittest.TestCase):
    """Verify that BacktestResultLike protocol accepts objects with new fields."""

    def test_protocol_satisfaction(self):
        class FakeResult:
            eval_status = "completed"
            position_recommendation = "long"
            outcome = "win"
            direction_correct = True
            stock_return_pct = 5.0
            simulated_return_pct = 4.5
            hit_stop_loss = False
            hit_take_profit = False
            first_hit = "neither"
            first_hit_trading_days = None
            operation_advice = "买入"
            net_simulated_return_pct = 4.0
            holding_days = 5
            transaction_costs = {"total_fees": 10.0}

        # Just verify it can be used as Sequence[BacktestResultLike]
        results = [FakeResult()]
        metrics = BacktestEngine.compute_portfolio_metrics(results=results)
        self.assertEqual(metrics.total_trades, 1)


if __name__ == "__main__":
    unittest.main()
