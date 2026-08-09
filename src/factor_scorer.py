# -*- coding: utf-8 -*-
"""技术因子加权评分器（Phase 3.1）。

将 KDJ / BOLL / ATR 等量化指标纳入综合评分，权重可配置。
默认在 _generate_signal 之后追加评分，与现有 signal_score 叠加。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FactorWeights:
    """各因子权重配置（总权重=100时各因子满分加起来为100）。"""
    kdj_weight: float = 30.0       # KDJ 满分权重
    boll_weight: float = 25.0      # BOLL 满分权重
    vol_risk_weight: float = 25.0  # 波动率/风险 满分权重
    atr_weight: float = 20.0       # ATR 满分权重

    @classmethod
    def default(cls) -> "FactorWeights":
        return cls()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FactorWeights":
        return cls(
            kdj_weight=float(d.get("kdj_weight", 30.0)),
            boll_weight=float(d.get("boll_weight", 25.0)),
            vol_risk_weight=float(d.get("vol_risk_weight", 25.0)),
            atr_weight=float(d.get("atr_weight", 20.0)),
        )


@dataclass
class FactorScoreResult:
    """单因子评分结果。"""
    factor: str
    score: float       # 0-100 归一化得分
    weight: float      # 权重
    weighted_score: float  # score * weight / 100
    reason: str        # 评分理由


@dataclass
class CompositeFactorScore:
    """多因子复合评分结果。"""
    total_score: float  # 加权总分（0-100）
    factors: List[FactorScoreResult] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)


def _score_kdj(kdj_status: str, kdj_k: float, kdj_j: float) -> tuple[float, str, str]:
    """KDJ 因子评分。返回 (score_0_100, reason, level)。"""
    status_scores = {
        "超买": (15, "超买区，短期回调风险加大", "偏空"),
        "超卖": (90, "超卖区，短期存在反弹机会", "偏多"),
        "金叉": (85, "金叉信号，短期偏多", "偏多"),
        "死叉": (20, "死叉信号，短期偏空", "偏空"),
        "多头": (70, "多头排列，趋势偏多", "偏多"),
        "空头": (25, "空头排列，趋势偏空", "偏空"),
        "中性": (50, "中性区间", "中性"),
    }
    score, reason, level = status_scores.get(kdj_status, (50, "未知状态", "中性"))
    return score, reason, level


def _score_boll(boll_position: float, boll_width_pct: float) -> tuple[float, str, str]:
    """BOLL 因子评分。返回 (score_0_100, reason, level)。"""
    reasons: List[str] = []
    base_score = 50.0

    # 带内位置评分：靠近下轨=偏多（超卖反弹），靠近上轨=偏空（超买回调）
    if boll_position <= 20:
        base_score = 85
        reasons.append(f"接近下轨({boll_position:.0f}/100)，超卖区间")
    elif boll_position <= 40:
        base_score = 65
        reasons.append(f"偏下轨({boll_position:.0f}/100)，偏多")
    elif boll_position >= 80:
        base_score = 20
        reasons.append(f"接近上轨({boll_position:.0f}/100)，超买区间")
    elif boll_position >= 60:
        base_score = 35
        reasons.append(f"偏上轨({boll_position:.0f}/100)，偏空")
    else:
        reasons.append(f"中轨附近({boll_position:.0f}/100)")

    # 带宽修正：极窄带宽加分（关注变盘方向）
    if 0 < boll_width_pct < 10:
        base_score = min(base_score + 10, 100)
        reasons.append(f"带宽仅 {boll_width_pct:.1f}%，波动收敛待变盘")

    level = "偏多" if base_score >= 60 else ("偏空" if base_score <= 40 else "中性")
    return base_score, "；".join(reasons), level


def _score_vol_risk(risk_level: str, vol_20d: float, max_drawdown_60d: float) -> tuple[float, str, str]:
    """波动率/风险因子评分。返回 (score_0_100, reason, level)。"""
    reasons: List[str] = []
    score = 50.0

    # 风险等级：低风险=高分（安全），高风险=低分（危险）
    risk_scores = {"低": 80, "中": 50, "高": 20}
    score = float(risk_scores.get(risk_level, 50))

    if risk_level == "高":
        reasons.append(f"高波动品种(年化{vol_20d:.1f}%)，风险较高")
    elif risk_level == "中":
        reasons.append(f"波动适中(年化{vol_20d:.1f}%)")
    else:
        reasons.append(f"低波动(年化{vol_20d:.1f}%)，相对安全")

    if max_drawdown_60d >= 20:
        score = max(score - 15, 0)
        reasons.append(f"60日最大回撤{max_drawdown_60d:.1f}%，回撤较大")
    elif max_drawdown_60d >= 10:
        score = max(score - 5, 0)
        reasons.append(f"60日最大回撤{max_drawdown_60d:.1f}%")

    level = "偏多" if score >= 60 else ("偏空" if score <= 40 else "中性")
    return score, "；".join(reasons), level


def _score_atr(atr_pct: float) -> tuple[float, str, str]:
    """ATR 波幅因子评分。返回 (score_0_100, reason, level)。"""
    # ATR 越大波动越大 → 对趋势交易来说中性偏负面（不确定性高）
    if atr_pct >= 6:
        score = 25
        reason = f"日内波幅{atr_pct:.1f}%，波动剧烈，操作难度高"
        level = "偏空"
    elif atr_pct >= 4:
        score = 40
        reason = f"日内波幅{atr_pct:.1f}%，波动较大"
        level = "偏空"
    elif atr_pct >= 2:
        score = 60
        reason = f"日内波幅{atr_pct:.1f}%，波动适中"
        level = "中性"
    else:
        score = 75
        reason = f"日内波幅{atr_pct:.1f}%，波动较小"
        level = "偏多"
    return score, reason, level


def compute_composite_factor_score(
    quant: Optional[Dict[str, Any]],
    weights: Optional[FactorWeights] = None,
) -> CompositeFactorScore:
    """基于量化指标计算复合因子评分。

    Args:
        quant: QuantIndicatorsResult.to_dict() 的输出，可为 None
        weights: 因子权重配置，None 使用默认值

    Returns:
        CompositeFactorScore 包含总分、各因子明细和分析理由
    """
    if weights is None:
        weights = FactorWeights.default()

    if not quant or not isinstance(quant, dict):
        return CompositeFactorScore(
            total_score=50.0,
            reasons=["量化指标不可用，使用中性基准分"],
        )

    factors: List[FactorScoreResult] = []
    all_reasons: List[str] = []
    risk_warnings: List[str] = []

    # KDJ
    kdj_score, kdj_reason, kdj_level = _score_kdj(
        quant.get("kdj_status", "中性"),
        float(quant.get("kdj_k", 50)),
        float(quant.get("kdj_j", 50)),
    )
    factors.append(FactorScoreResult(
        factor="KDJ",
        score=kdj_score,
        weight=weights.kdj_weight,
        weighted_score=kdj_score * weights.kdj_weight / 100,
        reason=kdj_reason,
    ))
    all_reasons.append(f"KDJ({kdj_level})：{kdj_reason}")

    # BOLL
    boll_score, boll_reason, boll_level = _score_boll(
        float(quant.get("boll_position", 50)),
        float(quant.get("boll_width_pct", 20)),
    )
    factors.append(FactorScoreResult(
        factor="BOLL",
        score=boll_score,
        weight=weights.boll_weight,
        weighted_score=boll_score * weights.boll_weight / 100,
        reason=boll_reason,
    ))
    all_reasons.append(f"BOLL({boll_level})：{boll_reason}")

    # 波动率/风险
    vol_score, vol_reason, vol_level = _score_vol_risk(
        quant.get("risk_level", "低"),
        float(quant.get("vol_20d", 0)),
        float(quant.get("max_drawdown_60d", 0)),
    )
    factors.append(FactorScoreResult(
        factor="波动率/风险",
        score=vol_score,
        weight=weights.vol_risk_weight,
        weighted_score=vol_score * weights.vol_risk_weight / 100,
        reason=vol_reason,
    ))
    all_reasons.append(f"风险({vol_level})：{vol_reason}")

    # ATR
    atr_score, atr_reason, atr_level = _score_atr(float(quant.get("atr_pct", 0)))
    factors.append(FactorScoreResult(
        factor="ATR",
        score=atr_score,
        weight=weights.atr_weight,
        weighted_score=atr_score * weights.atr_weight / 100,
        reason=atr_reason,
    ))
    all_reasons.append(f"ATR({atr_level})：{atr_reason}")

    # 汇总加权总分
    total_weighted = sum(f.weighted_score for f in factors)
    total_weight = weights.kdj_weight + weights.boll_weight + weights.vol_risk_weight + weights.atr_weight
    total_score = round(total_weighted / total_weight * 100, 2) if total_weight > 0 else 50.0

    # 风险警告
    max_dd = float(quant.get("max_drawdown_60d", 0))
    if max_dd >= 20:
        risk_warnings.append(f"60日最大回撤{max_dd:.1f}%，持仓风险较高")
    vol = float(quant.get("vol_20d", 0))
    if vol >= 50:
        risk_warnings.append(f"年化波动率{vol:.1f}%，属于高波动品种")

    return CompositeFactorScore(
        total_score=total_score,
        factors=factors,
        reasons=all_reasons,
        risk_warnings=risk_warnings,
    )
