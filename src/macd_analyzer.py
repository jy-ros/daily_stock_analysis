"""
MACD 深度分析模块

提供：
1. 7日 MACD 趋势分析（连续上涨/下跌趋势检测）
2. 趋势加速/转折点检测（当日变化幅度扩大 >20%）
3. 金叉/死叉检测与标注
4. 顶背离/底背离检测（价格与 MACD 方向不一致）
5. 柱体强度过滤（噪音区屏蔽）
6. MACD 复合评分（5维度加权 0-100）
"""

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd


# 柱体强度阈值：|BAR| 低于平均 |BAR| 的此比例时判定为弱信号
_WEAK_BAR_RATIO = 0.05

# 背离检测窗口（向前看的周期数）
_DIVERGENCE_LOOKBACK = 30

# 复合评分各维度权重（总分 100）
_SCORE_WEIGHTS = {
    "dif_trend": 20,
    "bar_trend": 20,
    "cross": 20,
    "zero_axis": 20,
    "divergence": 20,
}


@dataclass
class MACDDayRecord:
    """单日 MACD 数据记录"""
    date: str
    dif: float
    dea: float
    bar: float
    bar_direction: str  # "red" (BAR>0, 红柱) or "green" (BAR<0, 绿柱)
    close: float
    change_pct: Optional[float] = None


@dataclass
class MACDTrendSignal:
    """MACD 趋势分析信号"""
    direction: str  # "upward", "downward", "neutral"
    streak: int = 0
    description: str = ""
    annotation: str = ""


@dataclass
class MACDTurningPoint:
    """转折点检测"""
    detected: bool = False
    day_index: int = -1
    acceleration_pct: float = 0.0
    description: str = ""
    annotation: str = ""


@dataclass
class MACDDivergence:
    """顶背离/底背离检测"""
    bearish_divergence: bool = False      # 顶背离（价格新高，DIF 未新高）
    bullish_divergence: bool = False       # 底背离（价格新低，DIF 未新低）
    description: str = ""
    annotation: str = ""


@dataclass
class MACDAnalysisResult:
    """MACD 完整分析结果"""
    # 7日 MACD 列表
    days: List[MACDDayRecord] = field(default_factory=list)

    # 趋势分析
    dif_trend: MACDTrendSignal = field(default_factory=lambda: MACDTrendSignal(direction="neutral"))
    bar_trend: MACDTrendSignal = field(default_factory=lambda: MACDTrendSignal(direction="neutral"))

    # 转折点
    turning_point: MACDTurningPoint = field(default_factory=lambda: MACDTurningPoint())

    # 金叉/死叉
    golden_cross: bool = False
    death_cross: bool = False
    cross_day: int = -1
    cross_description: str = ""

    # 背离
    divergence: MACDDivergence = field(default_factory=lambda: MACDDivergence())

    # 柱体强度
    bar_strength: float = 1.0       # 0~1, 越低表示信号越弱
    is_noisy: bool = False           # 是否处于噪音区

    # 复合评分
    composite_score: int = 50        # 0-100

    # 最新值
    latest_dif: float = 0.0
    latest_dea: float = 0.0
    latest_bar: float = 0.0
    dif_change_pct: Optional[float] = None
    bar_change_pct: Optional[float] = None

    # 综合标注
    annotations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "days": [
                {
                    "date": d.date,
                    "dif": round(d.dif, 4),
                    "dea": round(d.dea, 4),
                    "bar": round(d.bar, 4),
                    "bar_direction": d.bar_direction,
                    "close": round(d.close, 2),
                    "change_pct": d.change_pct,
                }
                for d in self.days
            ],
            "dif_trend": {
                "direction": self.dif_trend.direction,
                "streak": self.dif_trend.streak,
                "description": self.dif_trend.description,
            },
            "bar_trend": {
                "direction": self.bar_trend.direction,
                "streak": self.bar_trend.streak,
                "description": self.bar_trend.description,
            },
            "turning_point": {
                "detected": self.turning_point.detected,
                "acceleration_pct": round(self.turning_point.acceleration_pct, 2),
                "description": self.turning_point.description,
            },
            "golden_cross": self.golden_cross,
            "death_cross": self.death_cross,
            "cross_description": self.cross_description,
            "divergence": {
                "bearish": self.divergence.bearish_divergence,
                "bullish": self.divergence.bullish_divergence,
                "description": self.divergence.description,
            },
            "bar_strength": round(self.bar_strength, 4),
            "is_noisy": self.is_noisy,
            "composite_score": self.composite_score,
            "latest": {
                "dif": round(self.latest_dif, 4),
                "dea": round(self.latest_dea, 4),
                "bar": round(self.latest_bar, 4),
                "dif_change_pct": round(self.dif_change_pct, 2) if self.dif_change_pct is not None else None,
                "bar_change_pct": round(self.bar_change_pct, 2) if self.bar_change_pct is not None else None,
            },
            "annotations": self.annotations,
        }


# ============================================================
# 辅助函数
# ============================================================

def compute_change_pct(d1: float, d2: float) -> float:
    """计算 d1 相对 d2 的变化百分比。"""
    if d2 == 0:
        return 0.0
    return (d1 - d2) / abs(d2) * 100


def _find_local_extrema(values: List[float]) -> Tuple[List[int], List[int]]:
    """查找局部极大值和极小值的索引。"""
    if len(values) < 3:
        return [], []
    peaks: List[int] = []
    troughs: List[int] = []
    for i in range(1, len(values) - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            peaks.append(i)
        if values[i] < values[i - 1] and values[i] <= values[i + 1]:
            troughs.append(i)
    if values[-1] > values[-2]:
        peaks.append(len(values) - 1)
    elif values[-1] < values[-2]:
        troughs.append(len(values) - 1)
    return peaks, troughs


# ============================================================
# 核心检测函数
# ============================================================

def detect_dif_trend(dif_values: List[float], bar_values: List[float]) -> MACDTrendSignal:
    """检测 DIF 连续趋势。"""
    signal = MACDTrendSignal(direction="neutral", streak=0)
    if len(dif_values) < 3:
        return signal

    streak_up = 0
    streak_down = 0
    for i in range(len(dif_values) - 1, 0, -1):
        if dif_values[i] > dif_values[i - 1]:
            streak_up += 1
            streak_down = 0
        elif dif_values[i] < dif_values[i - 1]:
            streak_down += 1
            streak_up = 0
        else:
            break
        if streak_up >= 3:
            signal.direction = "upward"
            signal.streak = streak_up
        elif streak_down >= 3:
            signal.direction = "downward"
            signal.streak = streak_down

    if signal.direction == "upward" and signal.streak >= 3:
        signal.description = f"DIF 已连续 {signal.streak} 天上升"
        signal.annotation = (
            f"📈 MACD-DIF 连续 {signal.streak} 天上升，表明短期动能持续增强，"
            f"价格走势偏多。"
        )
    elif signal.direction == "downward" and signal.streak >= 3:
        signal.description = f"DIF 已连续 {signal.streak} 天下降"
        signal.annotation = (
            f"📉 MACD-DIF 连续 {signal.streak} 天下降，表明短期动能持续减弱，"
            f"价格走势偏空。"
        )
    return signal


def detect_bar_trend(bar_values: List[float]) -> MACDTrendSignal:
    """检测 MACD 柱体（带符号值）的连续趋势方向。"""
    signal = MACDTrendSignal(direction="neutral", streak=0)
    if len(bar_values) < 3:
        return signal

    streak_up = 0
    streak_down = 0
    for i in range(len(bar_values) - 1, 0, -1):
        if bar_values[i] > bar_values[i - 1]:
            streak_up += 1
            streak_down = 0
        elif bar_values[i] < bar_values[i - 1]:
            streak_down += 1
            streak_up = 0
        else:
            break

    latest_bar = bar_values[-1]
    is_red = latest_bar >= 0

    if streak_up >= 3:
        signal.direction = "upward"
        signal.streak = streak_up
        if is_red:
            signal.annotation = (
                f"📊 MACD 红柱连续 {streak_up} 天放大，多头力量持续增强。"
            )
        else:
            signal.annotation = (
                f"📊 MACD 绿柱连续 {streak_up} 天缩小（负值收窄），"
                f"空头力量减弱，偏多信号。"
            )
        signal.description = f"MACD 柱体连续 {streak_up} 天上升"
    elif streak_down >= 3:
        signal.direction = "downward"
        signal.streak = streak_down
        if is_red:
            signal.annotation = (
                f"📊 MACD 红柱连续 {streak_down} 天缩小，"
                f"多头力量减弱，偏空信号。"
            )
        else:
            signal.annotation = (
                f"📊 MACD 绿柱连续 {streak_down} 天放大，空头力量持续增强。"
            )
        signal.description = f"MACD 柱体连续 {streak_down} 天下降"
    return signal


def detect_turning_point(dif_values: List[float], dif_trend: MACDTrendSignal) -> MACDTurningPoint:
    """检测趋势加速/转折点（当日变化幅度扩大 >20%）。"""
    result = MACDTurningPoint(detected=False)
    if len(dif_values) < 3 or dif_trend.streak < 2:
        return result

    today_diff = dif_values[-1] - dif_values[-2]
    prev_diff = dif_values[-2] - dif_values[-3]
    if prev_diff == 0:
        return result

    acceleration = abs(today_diff / prev_diff)
    if today_diff * prev_diff > 0 and acceleration > 1.2:
        result.detected = True
        result.acceleration_pct = (acceleration - 1) * 100
        result.day_index = len(dif_values) - 1
        if today_diff > 0:
            result.description = (
                f"DIF 上升加速，当日变化幅度扩大 {result.acceleration_pct:.0f}%，"
                f"上涨动能显著增强。"
            )
            result.annotation = (
                f"⚡ MACD 趋势加速：DIF 上升幅度较前日扩大 {result.acceleration_pct:.0f}%，"
                f"上涨动能显著增强，可能出现趋势加速上涨的转折点。"
            )
        else:
            result.description = (
                f"DIF 下跌加速，当日变化幅度扩大 {result.acceleration_pct:.0f}%，"
                f"下跌动能显著增强。"
            )
            result.annotation = (
                f"⚡ MACD 趋势加速：DIF 下跌幅度较前日扩大 {result.acceleration_pct:.0f}%，"
                f"下跌动能显著增强，可能出现趋势加速下跌的转折点。"
            )
    return result


def detect_cross(
    dif_values: List[float],
    dea_values: List[float],
) -> Tuple[bool, bool, int, str]:
    """检测金叉/死叉。"""
    golden_cross = False
    death_cross = False
    cross_day = -1
    description = ""
    if len(dif_values) < 2:
        return golden_cross, death_cross, cross_day, description

    for i in range(len(dif_values) - 1, 0, -1):
        prev_diff = dif_values[i - 1] - dea_values[i - 1]
        curr_diff = dif_values[i] - dea_values[i]
        if prev_diff <= 0 < curr_diff and not golden_cross:
            golden_cross = True
            cross_day = i
            description = f"✅ 金叉出现（第{i + 1}天）：DIF 上穿 DEA，买入信号。"
            break
        elif prev_diff >= 0 > curr_diff and not death_cross:
            death_cross = True
            cross_day = i
            description = f"❌ 死叉出现（第{i + 1}天）：DIF 下穿 DEA，卖出信号。"
            break
    return golden_cross, death_cross, cross_day, description


def detect_divergence(
    df: pd.DataFrame,
    lookback: int = _DIVERGENCE_LOOKBACK,
) -> MACDDivergence:
    """
    检测 MACD 顶背离/底背离。

    顶背离：价格创近期新高，但 DIF 未创新高 → 上涨动能衰竭，看空。
    底背离：价格创近期新低，但 DIF 未创新低 → 下跌动能衰竭，看多。

    使用局部极值点比较法，避免趋势中的噪音。
    """
    result = MACDDivergence()

    window = df.tail(lookback).copy()
    if len(window) < 20:
        return result

    closes = [float(v) for v in window['close'].values]
    difs = [float(v) for v in window['MACD_DIF'].values]

    close_peaks, close_troughs = _find_local_extrema(closes)
    dif_peaks, dif_troughs = _find_local_extrema(difs)

    # === 顶背离检测 ===
    # 价格最近两个峰：最新峰 > 前一个峰，但 DIF 最新峰 < 前一个峰
    if len(close_peaks) >= 2 and len(dif_peaks) >= 2:
        latest_cp = close_peaks[-1]
        prev_cp = close_peaks[-2]
        latest_dp = dif_peaks[-1]
        # 找到 DIF 上前一个与价格前一个峰位置最接近的峰
        prev_dp_candidates = [p for p in dif_peaks if p < latest_dp]
        if prev_dp_candidates:
            prev_dp = prev_dp_candidates[-1]
            if (closes[latest_cp] > closes[prev_cp]
                    and difs[latest_dp] < difs[prev_dp]):
                result.bearish_divergence = True
                result.description = (
                    f"顶背离：价格创近期新高({closes[latest_cp]:.2f} > {closes[prev_cp]:.2f})，"
                    f"但 DIF 未同步创新高({difs[latest_dp]:.4f} < {difs[prev_dp]:.4f})，"
                    f"上涨动能衰竭，警惕回调。"
                )
                result.annotation = (
                    f"🚨 顶背离信号：价格创新高但 MACD DIF 未创新高，"
                    f"上涨动能衰竭，警惕回调风险。"
                )

    # === 底背离检测 ===
    if len(close_troughs) >= 2 and len(dif_troughs) >= 2:
        latest_ct = close_troughs[-1]
        prev_ct = close_troughs[-2]
        latest_dt = dif_troughs[-1]
        prev_dt_candidates = [t for t in dif_troughs if t < latest_dt]
        if prev_dt_candidates:
            prev_dt = prev_dt_candidates[-1]
            if (closes[latest_ct] < closes[prev_ct]
                    and difs[latest_dt] > difs[prev_dt]):
                result.bullish_divergence = True
                result.description = (
                    f"底背离：价格创近期新低({closes[latest_ct]:.2f} < {closes[prev_ct]:.2f})，"
                    f"但 DIF 未同步创新低({difs[latest_dt]:.4f} > {difs[prev_dt]:.4f})，"
                    f"下跌动能衰竭，关注反弹机会。"
                )
                result.annotation = (
                    f"💡 底背离信号：价格创新低但 MACD DIF 未创新低，"
                    f"下跌动能衰竭，关注反弹机会。"
                )

    return result


def compute_bar_strength(bars: List[float]) -> Tuple[float, bool]:
    """
    计算柱体强度并判断是否处于噪音区。

    柱体强度 = 当前 |BAR| / 平均 |BAR|
    当柱体强度低于 _WEAK_BAR_RATIO 时，标记为噪音区。
    """
    if not bars:
        return 1.0, False
    avg_abs_bar = statistics.mean(abs(b) for b in bars) if len(bars) > 1 else abs(bars[0])
    if avg_abs_bar == 0:
        return 0.0, True
    current_strength = abs(bars[-1]) / avg_abs_bar
    is_noisy = current_strength < _WEAK_BAR_RATIO
    return current_strength, is_noisy


def compute_composite_score(
    dif_trend: MACDTrendSignal,
    bar_trend: MACDTrendSignal,
    golden_cross: bool,
    death_cross: bool,
    dif: float,
    dea: float,
    divergence: MACDDivergence,
) -> int:
    """
    计算 MACD 复合评分（0-100）。

    5个维度各 20 分：
    - DIF 趋势：连续上升 >=3 天=20, <3 天=15, 中性=10, 下降<3 天=5, >=3 天=0
    - 柱体趋势：同上
    - 交叉信号：零轴金叉=20, 金叉=15, 无=10, 死叉=0
    - 零轴位置：DIF/DEA 均在零轴上=20, 混合=10, 均在零轴下=0
    - 背离：底背离=20, 无=10, 顶背离=0
    """
    score = 0

    # 1. DIF 趋势 (0-20)
    if dif_trend.direction == "upward":
        score += 20 if dif_trend.streak >= 3 else 15
    elif dif_trend.direction == "neutral":
        score += 10
    else:
        score += 5 if dif_trend.streak < 3 else 0

    # 2. 柱体趋势 (0-20)
    if bar_trend.direction == "upward":
        score += 20 if bar_trend.streak >= 3 else 15
    elif bar_trend.direction == "neutral":
        score += 10
    else:
        score += 5 if bar_trend.streak < 3 else 0

    # 3. 交叉信号 (0-20)
    if golden_cross and dif > 0:
        score += 20  # 零轴上金叉
    elif golden_cross:
        score += 15
    elif death_cross:
        score += 0
    else:
        score += 10

    # 4. 零轴位置 (0-20)
    if dif > 0 and dea > 0:
        score += 20
    elif dif < 0 and dea < 0:
        score += 0
    else:
        score += 10

    # 5. 背离 (0-20)
    if divergence.bullish_divergence:
        score += 20
    elif divergence.bearish_divergence:
        score += 0
    else:
        score += 10

    return score


def analyze_macd(df: pd.DataFrame) -> MACDAnalysisResult:
    """
    对股票进行完整的 MACD 分析。

    Args:
        df: 包含 MACD_DIF, MACD_DEA, MACD_BAR, close 列的 DataFrame

    Returns:
        MACDAnalysisResult 分析结果
    """
    result = MACDAnalysisResult()

    for col in ['MACD_DIF', 'MACD_DEA', 'MACD_BAR']:
        if col not in df.columns:
            result.annotations.append(f"MACD 数据缺失，无法完成分析（缺少 {col}）。")
            return result

    # 取最近数据
    recent = df.tail(7).copy()
    if len(recent) < 2:
        result.annotations.append("MACD 数据不足（少于2个交易日），无法进行趋势分析。")
        return result

    # 构建 7 日 MACD 记录
    difs: List[float] = []
    deas: List[float] = []
    bars: List[float] = []

    for i, (_, row) in enumerate(recent.iterrows()):
        bar_val = float(row['MACD_BAR'])
        dif_val = float(row['MACD_DIF'])
        dea_val = float(row['MACD_DEA'])
        close_val = float(row['close'])

        difs.append(dif_val)
        deas.append(dea_val)
        bars.append(bar_val)

        date_str = str(row['date'])
        if hasattr(row['date'], 'date'):
            date_str = str(row['date'].date())
        elif hasattr(row['date'], 'strftime'):
            date_str = row['date'].strftime('%Y-%m-%d')

        change_pct = None
        if 'pct_chg' in row and pd.notna(row['pct_chg']):
            change_pct = float(row['pct_chg'])

        result.days.append(MACDDayRecord(
            date=date_str,
            dif=dif_val,
            dea=dea_val,
            bar=bar_val,
            bar_direction="red" if bar_val >= 0 else "green",
            close=close_val,
            change_pct=change_pct,
        ))

    # 最新值
    result.latest_dif = difs[-1]
    result.latest_dea = deas[-1]
    result.latest_bar = bars[-1]

    # 变化幅度
    if len(difs) >= 2 and difs[-2] != 0:
        result.dif_change_pct = compute_change_pct(difs[-1], difs[-2])
    if len(bars) >= 2 and bars[-2] != 0:
        result.bar_change_pct = compute_change_pct(bars[-1], bars[-2])

    # 1. DIF 趋势
    result.dif_trend = detect_dif_trend(difs, bars)

    # 2. 柱体趋势
    result.bar_trend = detect_bar_trend(bars)

    # 3. 趋势加速/转折点
    result.turning_point = detect_turning_point(difs, result.dif_trend)

    # 4. 金叉/死叉
    result.golden_cross, result.death_cross, result.cross_day, result.cross_description = \
        detect_cross(difs, deas)

    # 5. 顶背离/底背离（使用更多历史数据）
    if len(df) >= 20:
        result.divergence = detect_divergence(df)
    else:
        result.divergence = MACDDivergence()

    # 6. 柱体强度
    result.bar_strength, result.is_noisy = compute_bar_strength(bars)

    # 7. MACD 复合评分
    result.composite_score = compute_composite_score(
        result.dif_trend, result.bar_trend,
        result.golden_cross, result.death_cross,
        result.latest_dif, result.latest_dea,
        result.divergence,
    )

    # ============================================================
    # 8. 生成综合标注
    # ============================================================
    annotations: List[str] = []

    # DIF 趋势标注
    if result.dif_trend.annotation:
        annotations.append(result.dif_trend.annotation)

    # 红绿柱趋势标注
    if result.bar_trend.annotation:
        annotations.append(result.bar_trend.annotation)

    # 转折点标注
    if result.turning_point.detected:
        annotations.append(result.turning_point.annotation)

    # 金叉/死叉
    if result.golden_cross:
        cross_ann = (
            f"🔀 {result.cross_description} "
            f"DIF({difs[result.cross_day]:.4f}) 上穿 DEA({deas[result.cross_day]:.4f})。"
            if result.cross_day >= 0
            else "🔀 金叉出现：DIF 上穿 DEA，买入信号。"
        )
        annotations.append(cross_ann)
    elif result.death_cross:
        cross_ann = (
            f"🔀 {result.cross_description} "
            f"DIF({difs[result.cross_day]:.4f}) 下穿 DEA({deas[result.cross_day]:.4f})。"
            if result.cross_day >= 0
            else "🔀 死叉出现：DIF 下穿 DEA，卖出信号。"
        )
        annotations.append(cross_ann)

    # 背离标注
    if result.divergence.annotation:
        annotations.append(result.divergence.annotation)

    # 噪音区提示
    if result.is_noisy:
        annotations.append(
            "🔇 MACD 柱体强度极低，DIF 与 DEA 高度粘合，"
            "当前信号可靠性较低，建议结合其他指标判断。"
        )

    # 零轴位置
    if result.latest_dif > 0 and deas[-1] > 0:
        annotations.append(
            f"📈 DIF({result.latest_dif:.4f}) 与 DEA({deas[-1]:.4f}) 均在零轴上方，"
            f"中长期趋势偏多。"
        )
    elif result.latest_dif < 0 and deas[-1] < 0:
        annotations.append(
            f"📉 DIF({result.latest_dif:.4f}) 与 DEA({deas[-1]:.4f}) 均在零轴下方，"
            f"中长期趋势偏空。"
        )

    result.annotations = annotations
    return result
