# -*- coding: utf-8 -*-
"""Benchmark comparison tests (offline)."""

import unittest

from src.benchmark import (
    compute_alpha,
    compute_benchmark_return_pct,
    get_benchmark_code_for_stock,
)
from src.core.backtest_engine import BacktestEngine


class TestBenchmarkCodeMapping(unittest.TestCase):
    def test_cn_stock(self) -> None:
        self.assertEqual(get_benchmark_code_for_stock("600519"), "000300")

    def test_cn_explicit_market(self) -> None:
        self.assertEqual(get_benchmark_code_for_stock("600519", "cn"), "000300")

    def test_hk_market(self) -> None:
        self.assertEqual(get_benchmark_code_for_stock("00700", "hk"), "HSI")

    def test_us_market(self) -> None:
        self.assertEqual(get_benchmark_code_for_stock("AAPL", "us"), "SPX")


class TestComputeBenchmarkReturn(unittest.TestCase):
    def test_basic_return(self) -> None:
        closes = [100.0, 105.0, 110.0]
        result = compute_benchmark_return_pct(closes, start_index=0, end_index=2)
        self.assertAlmostEqual(result, 10.0, places=2)

    def test_empty_list(self) -> None:
        self.assertIsNone(compute_benchmark_return_pct([]))

    def test_single_element(self) -> None:
        self.assertIsNone(compute_benchmark_return_pct([100.0]))

    def test_none_prices(self) -> None:
        self.assertIsNone(compute_benchmark_return_pct([None, 100.0]))

    def test_negative_start_price(self) -> None:
        self.assertIsNone(compute_benchmark_return_pct([-100.0, 100.0]))


class TestComputeAlpha(unittest.TestCase):
    def test_positive_alpha(self) -> None:
        self.assertAlmostEqual(compute_alpha(15.0, 10.0), 5.0)

    def test_negative_alpha(self) -> None:
        self.assertAlmostEqual(compute_alpha(5.0, 10.0), -5.0)

    def test_none_stock_return(self) -> None:
        self.assertIsNone(compute_alpha(None, 10.0))

    def test_none_benchmark_return(self) -> None:
        self.assertIsNone(compute_alpha(10.0, None))


class TestBacktestEngineBenchmark(unittest.TestCase):
    def test_benchmark_basic(self) -> None:
        closes = [100.0, 102.0, 104.0, 106.0, 108.0]
        result = BacktestEngine.evaluate_benchmark(
            stock_return_pct=10.0,
            benchmark_closes=closes,
            eval_window_days=5,
        )
        self.assertAlmostEqual(result["benchmark_return_pct"], 8.0, places=2)
        self.assertAlmostEqual(result["alpha_pct"], 2.0, places=2)

    def test_benchmark_empty_closes(self) -> None:
        result = BacktestEngine.evaluate_benchmark(
            stock_return_pct=10.0,
            benchmark_closes=[],
            eval_window_days=5,
        )
        self.assertIsNone(result["benchmark_return_pct"])
        self.assertIsNone(result["alpha_pct"])

    def test_benchmark_none_stock_return(self) -> None:
        closes = [100.0, 105.0]
        result = BacktestEngine.evaluate_benchmark(
            stock_return_pct=None,
            benchmark_closes=closes,
            eval_window_days=1,
        )
        self.assertAlmostEqual(result["benchmark_return_pct"], 5.0, places=2)
        self.assertIsNone(result["alpha_pct"])


if __name__ == "__main__":
    unittest.main()
