# -*- coding: utf-8 -*-
"""基准对比工具：获取指数基准收益率、计算超额收益。

纯逻辑层 + 数据获取层分离：
- compute_benchmark_return_pct: 纯计算，接受价格序列
- get_benchmark_return_for_period: 获取指数数据并计算收益率（需网络）
- get_benchmark_code_for_stock: 根据股票代码返回对应市场基准指数代码
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# 各市场基准指数代码（通过 DataFetcherManager.get_daily_data 可获取）
BENCHMARK_INDEX_CODES: Dict[str, str] = {
    "cn": "000300",   # 沪深300
    "hk": "HSI",      # 恒生指数
    "us": "SPX",      # 标普500
    "jp": "N225",     # 日经225
    "kr": "KS11",     # KOSPI
}

BENCHMARK_NAMES: Dict[str, str] = {
    "cn": "沪深300",
    "hk": "恒生指数",
    "us": "标普500",
    "jp": "日经225",
    "kr": "KOSPI",
}


def get_benchmark_code_for_stock(stock_code: str, market: Optional[str] = None) -> str:
    """根据股票代码（或已知市场）返回基准指数代码。"""
    if market and market in BENCHMARK_INDEX_CODES:
        return BENCHMARK_INDEX_CODES[market]
    # 默认 A 股
    return BENCHMARK_INDEX_CODES["cn"]


def compute_benchmark_return_pct(
    benchmark_closes: List[Optional[float]],
    start_index: int = 0,
    end_index: Optional[int] = None,
) -> Optional[float]:
    """纯计算：从价格序列中计算基准收益率（%）。

    Args:
        benchmark_closes: 按日期排序的收盘价列表
        start_index: 起始 bar 索引（含）
        end_index: 结束 bar 索引（含），None 则取最后一条

    Returns:
        收益率（%），数据不足返回 None
    """
    if not benchmark_closes or len(benchmark_closes) < 2:
        return None
    if end_index is None:
        end_index = len(benchmark_closes) - 1
    if start_index < 0 or end_index <= start_index:
        return None
    if end_index >= len(benchmark_closes):
        return None

    start_price = benchmark_closes[start_index]
    end_price = benchmark_closes[end_index]

    if start_price is None or end_price is None:
        return None
    try:
        start_val = float(start_price)
        end_val = float(end_price)
    except (TypeError, ValueError):
        return None

    if start_val <= 0:
        return None

    return round((end_val - start_val) / start_val * 100, 4)


def compute_alpha(
    stock_return_pct: Optional[float],
    benchmark_return_pct: Optional[float],
) -> Optional[float]:
    """计算超额收益（alpha）= 股票收益 - 基准收益。"""
    if stock_return_pct is None or benchmark_return_pct is None:
        return None
    try:
        return round(float(stock_return_pct) - float(benchmark_return_pct), 4)
    except (TypeError, ValueError):
        return None


def get_benchmark_return_for_period(
    *,
    stock_code: str,
    market: Optional[str],
    analysis_date: date,
    eval_window_days: int,
    fetcher_manager: Any,
) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    """获取基准指数在回测窗口内的收益率。

    Args:
        stock_code: 股票代码（用于确定市场）
        market: 市场标识 (cn/hk/us/jp/kr)，可为 None
        analysis_date: 分析日期
        eval_window_days: 评估窗口天数（交易日）
        fetcher_manager: DataFetcherManager 实例

    Returns:
        (benchmark_code, benchmark_return_pct, alpha_pct)
        获取失败时对应值为 None
    """
    benchmark_code = get_benchmark_code_for_stock(stock_code, market)

    # 计算日期范围（多取几天以覆盖非交易日）
    start_date = analysis_date.strftime("%Y-%m-%d")
    end_date = (analysis_date + timedelta(days=eval_window_days + 10)).strftime("%Y-%m-%d")

    try:
        df, _source = fetcher_manager.get_daily_data(
            stock_code=benchmark_code,
            start_date=start_date,
            end_date=end_date,
            days=eval_window_days + 15,
        )
    except Exception as e:
        logger.debug("[benchmark] fetch failed for %s: %s", benchmark_code, e)
        return benchmark_code, None, None

    if df is None or df.empty or len(df) < 2:
        return benchmark_code, None, None

    closes = df["close"].tolist()
    benchmark_return = compute_benchmark_return_pct(closes, start_index=0, end_index=min(eval_window_days, len(closes) - 1))

    return benchmark_code, benchmark_return, None
