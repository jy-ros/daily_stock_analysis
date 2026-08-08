# -*- coding: utf-8 -*-
"""量化辅助指标（Phase 1）：KDJ / BOLL / ATR / 历史波动率 / 最大回撤 / VaR。

为技术面分析提供量化视角，作为 LLM 结构化结论之外的旁证。
输入沿用数据源标准化后的 OHLCV DataFrame（含 date/open/high/low/close/volume）。
约定：
- 数据不足时对应指标返回 0（或中性状态），不抛异常、不拖垮主流程。
- 百分数以百分号数值为单位；回撤 / VaR 以「亏损幅度」正值表示。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

KDJ_PERIOD = 9
KDJ_K_SMOOTH = 3
KDJ_D_SMOOTH = 3
BOLL_PERIOD = 20
BOLL_STD = 2.0
ATR_PERIOD = 14
VOL_PERIOD = 20
TRADING_DAYS_PER_YEAR = 252
MAX_DRAWDOWN_WINDOW = 60
VAR_CONFIDENCE = 0.05
RISK_HIGH_VOL = 50.0
RISK_MID_VOL = 30.0


def _to_float(value: Any) -> float:
    """安全转 float，None/NaN 归零。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(number):
        return 0.0
    return number


def _safe(number: float) -> float:
    return round(_to_float(number), 3)


def _latest(series: Optional[pd.Series]) -> float:
    if series is None or len(series) == 0:
        return 0.0
    return _to_float(series.iloc[-1])


@dataclass
class QuantIndicatorsResult:
    """量化辅助指标集（Phase 1）"""

    # KDJ (9,3,3)
    kdj_k: float = 0.0
    kdj_d: float = 0.0
    kdj_j: float = 0.0
    kdj_status: str = "中性"  # 超买 / 超卖 / 金叉 / 死叉 / 多头 / 空头
    kdj_golden_cross: bool = False
    kdj_death_cross: bool = False

    # BOLL (20, 2σ)
    boll_upper: float = 0.0
    boll_mid: float = 0.0
    boll_lower: float = 0.0
    boll_position: float = 50.0  # 当前价在带内百分位 0-100
    boll_width_pct: float = 0.0  # 带宽 / 中轨 * 100（波动收敛 / 扩张）

    # ATR
    atr: float = 0.0
    atr_pct: float = 0.0  # ATR / close * 100（日内波幅占比）

    # 波动率 / 风险
    vol_20d: float = 0.0  # 20 日年化历史波动率（%）
    max_drawdown_60d: float = 0.0  # 60 日最大回撤（%，正值）
    var_95_1d: float = 0.0  # 95% 单日 VaR（%，历史法，正值）
    risk_level: str = "低"  # 低 / 中 / 高

    # 汇总
    summary: str = ""  # 一句话量化视角描述

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kdj_k": self.kdj_k,
            "kdj_d": self.kdj_d,
            "kdj_j": self.kdj_j,
            "kdj_status": self.kdj_status,
            "kdj_golden_cross": self.kdj_golden_cross,
            "kdj_death_cross": self.kdj_death_cross,
            "boll_upper": self.boll_upper,
            "boll_mid": self.boll_mid,
            "boll_lower": self.boll_lower,
            "boll_position": self.boll_position,
            "boll_width_pct": self.boll_width_pct,
            "atr": self.atr,
            "atr_pct": self.atr_pct,
            "vol_20d": self.vol_20d,
            "max_drawdown_60d": self.max_drawdown_60d,
            "var_95_1d": self.var_95_1d,
            "risk_level": self.risk_level,
            "summary": self.summary,
        }


def _compute_kdj(df: pd.DataFrame) -> Dict[str, Any]:
    """KDJ(9,3,3) 主指标与金叉/死叉判定。"""
    output: Dict[str, Any] = {
        "kdj_k": 0.0,
        "kdj_d": 0.0,
        "kdj_j": 0.0,
        "kdj_status": "中性",
        "kdj_golden_cross": False,
        "kdj_death_cross": False,
    }
    if df is None or len(df) < KDJ_PERIOD + 2:
        return output

    lowest_low = df["low"].rolling(window=KDJ_PERIOD).min()
    highest_high = df["high"].rolling(window=KDJ_PERIOD).max()
    denominator = highest_high - lowest_low
    rsv = ((df["close"] - lowest_low) / denominator.mask(denominator == 0) * 100).fillna(50)
    k_value = rsv.ewm(alpha=1 / KDJ_K_SMOOTH, adjust=False).mean()
    d_value = k_value.ewm(alpha=1 / KDJ_D_SMOOTH, adjust=False).mean()
    j_value = 3 * k_value - 2 * d_value

    output["kdj_k"] = _latest(k_value)
    output["kdj_d"] = _latest(d_value)
    output["kdj_j"] = _latest(j_value)

    delta = (k_value - d_value).dropna()
    if len(delta) >= 2:
        prev_delta = _to_float(delta.iloc[-2])
        curr_delta = _to_float(delta.iloc[-1])
        if prev_delta <= 0 < curr_delta:
            output["kdj_golden_cross"] = True
        elif prev_delta >= 0 > curr_delta:
            output["kdj_death_cross"] = True

    k = output["kdj_k"]
    d = output["kdj_d"]
    j = output["kdj_j"]
    if k > 90 or j > 100:
        output["kdj_status"] = "超买"
    elif k < 10 or j < 0:
        output["kdj_status"] = "超卖"
    elif output["kdj_golden_cross"]:
        output["kdj_status"] = "金叉"
    elif output["kdj_death_cross"]:
        output["kdj_status"] = "死叉"
    elif k >= d:
        output["kdj_status"] = "多头"
    else:
        output["kdj_status"] = "空头"
    return output


def _compute_boll(df: pd.DataFrame, close: pd.Series) -> Dict[str, Any]:
    """BOLL(20, 2σ) 上/中/下轨、带内位置与带宽。"""
    output: Dict[str, Any] = {
        "boll_upper": 0.0,
        "boll_mid": 0.0,
        "boll_lower": 0.0,
        "boll_position": 50.0,
        "boll_width_pct": 0.0,
    }
    if df is None or len(df) < BOLL_PERIOD:
        return output

    mid = close.rolling(window=BOLL_PERIOD).mean()
    std = close.rolling(window=BOLL_PERIOD).std()
    upper = mid + BOLL_STD * std
    lower = mid - BOLL_STD * std

    output["boll_mid"] = _to_float(mid.iloc[-1])
    output["boll_upper"] = _to_float(upper.iloc[-1])
    output["boll_lower"] = _to_float(lower.iloc[-1])

    if output["boll_mid"] > 0:
        output["boll_width_pct"] = round(
            (output["boll_upper"] - output["boll_lower"]) / output["boll_mid"] * 100, 2
        )

    band_span = output["boll_upper"] - output["boll_lower"]
    if band_span > 0:
        close_latest = _to_float(close.iloc[-1])
        position = (close_latest - output["boll_lower"]) / band_span * 100
        output["boll_position"] = round(max(0.0, min(100.0, position)), 2)
    return output


def _compute_atr(df: pd.DataFrame, close: pd.Series) -> Dict[str, Any]:
    """ATR(14)（Wilder 口径）与 ATR 占收盘价比例。"""
    output: Dict[str, Any] = {"atr": 0.0, "atr_pct": 0.0}
    if df is None or len(df) < ATR_PERIOD + 1:
        return output

    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()

    output["atr"] = _latest(atr)
    close_latest = _to_float(close.iloc[-1])
    if close_latest > 0:
        output["atr_pct"] = round(output["atr"] / close_latest * 100, 2)
    return output


def _compute_volatility(close: pd.Series) -> float:
    """20 日年化历史波动率（%）。"""
    if close is None or len(close) < VOL_PERIOD:
        return 0.0
    returns = close.pct_change().dropna()
    daily = returns.tail(VOL_PERIOD).std()
    if pd.isna(daily):
        return 0.0
    return round(_to_float(daily) * (TRADING_DAYS_PER_YEAR ** 0.5) * 100, 3)


def _compute_max_drawdown(close: pd.Series) -> float:
    """60 日最大回撤（%）。"""
    if close is None or len(close) < 2:
        return 0.0
    window = close.tail(min(MAX_DRAWDOWN_WINDOW, len(close)))
    drawdown = (window - window.cummax()) / window.cummax()
    return round(max(0.0, -_to_float(drawdown.min()) * 100), 3)


def _compute_var(close: pd.Series) -> float:
    """95% 单日 VaR（历史法，%）。"""
    if close is None or len(close) < 2:
        return 0.0
    returns = close.pct_change().dropna()
    if len(returns) == 0:
        return 0.0
    var = -_to_float(returns.quantile(VAR_CONFIDENCE)) * 100
    return round(max(0.0, var), 3)


def _risk_level(vol_20d: float) -> str:
    if vol_20d >= RISK_HIGH_VOL:
        return "高"
    if vol_20d >= RISK_MID_VOL:
        return "中"
    return "低"


def build_quant_summary(quant: Dict[str, Any]) -> str:
    """由指标字典生成一句话量化视角描述（供 LLM prompt / 报告）。"""
    risk_level = quant.get("risk_level", "低")
    kdj_status = quant.get("kdj_status", "中性")
    boll_position = _to_float(quant.get("boll_position"))
    atr_pct = _to_float(quant.get("atr_pct"))
    vol_20d = _to_float(quant.get("vol_20d"))
    max_dd = _to_float(quant.get("max_drawdown_60d"))
    var_95 = _to_float(quant.get("var_95_1d"))
    return (
        f"KDJ 状态:{kdj_status}，布林带内位置 {boll_position:.0f}/100，"
        f"平均日内波幅 ATR {atr_pct:.1f}%，年化波动率 {vol_20d:.1f}%，"
        f"60日最大回撤 {max_dd:.1f}%，单日 95% VaR {var_95:.1f}%，风险等级:{risk_level}"
    )


def analyze_quant_indicators(df: Optional[pd.DataFrame]) -> QuantIndicatorsResult:
    """计算量化辅助指标；数据不足 / 异常时优雅降级，不抛异常。"""
    result = QuantIndicatorsResult()
    try:
        if df is None or df.empty or len(df) < 15:
            result.summary = "历史数据不足 15 根，量化指标不可用"
            return result

        close = df["close"].astype(float)

        kdj = _compute_kdj(df)
        boll = _compute_boll(df, close)
        atr = _compute_atr(df, close)

        result.kdj_k = _safe(kdj["kdj_k"])
        result.kdj_d = _safe(kdj["kdj_d"])
        result.kdj_j = _safe(kdj["kdj_j"])
        result.kdj_status = kdj["kdj_status"]
        result.kdj_golden_cross = bool(kdj["kdj_golden_cross"])
        result.kdj_death_cross = bool(kdj["kdj_death_cross"])

        result.boll_upper = _safe(boll["boll_upper"])
        result.boll_mid = _safe(boll["boll_mid"])
        result.boll_lower = _safe(boll["boll_lower"])
        result.boll_position = _safe(boll["boll_position"])
        result.boll_width_pct = _safe(boll["boll_width_pct"])

        result.atr = _safe(atr["atr"])
        result.atr_pct = _safe(atr["atr_pct"])
        result.vol_20d = _compute_volatility(close)
        result.max_drawdown_60d = _compute_max_drawdown(close)
        result.var_95_1d = _compute_var(close)
        result.risk_level = _risk_level(result.vol_20d)

        result.summary = build_quant_summary(result.to_dict())
        return result
    except Exception as e:
        logger.warning("[quant] analyze_quant_indicators degraded: %s", e)
        result.summary = "量化指标计算降级，本次不可用"
        return result