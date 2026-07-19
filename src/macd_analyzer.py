"""
MACD 深度分析模块

提供：
1. 7日 MACD 趋势分析（连续上涨/下跌趋势检测）
2. 趋势加速/转折点检测（当日变化幅度扩大 >20%）
3. 金叉/死叉检测与标注
4. 结构化的标注和说明文本
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd


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
    streak: int = 0  # 连续天数
    description: str = ""  # 趋势描述
    annotation: str = ""  # 标注文本


@dataclass
class MACDTurningPoint:
    """转折点检测"""
    detected: bool = False
    day_index: int = -1
    acceleration_pct: float = 0.0
    description: str = ""
    annotation: str = ""


@dataclass
class MACDAnalysisResult:
    """MACD 完整分析结果"""
    # 7日 MACD 列表（最近7个交易日）
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

    # 最新值
    latest_dif: float = 0.0
    latest_dea: float = 0.0
    latest_bar: float = 0.0
    dif_change_pct: Optional[float] = None  # 当日 DIF 变化幅度
    bar_change_pct: Optional[float] = None  # 当日 BAR 变化幅度

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
            "latest": {
                "dif": round(self.latest_dif, 4),
                "dea": round(self.latest_dea, 4),
                "bar": round(self.latest_bar, 4),
                "dif_change_pct": round(self.dif_change_pct, 2) if self.dif_change_pct is not None else None,
                "bar_change_pct": round(self.bar_change_pct, 2) if self.bar_change_pct is not None else None,
            },
            "annotations": self.annotations,
        }


def extract_close_prices(df: pd.DataFrame) -> List[float]:
    """从 DataFrame 提取最近 N 行收盘价序列。"""
    return [float(v) for v in df['close'].tail(7).values]


def extract_change_pcts(df: pd.DataFrame) -> List[Optional[float]]:
    """从 DataFrame 提取最近 N 行涨跌幅序列。"""
    pcts: List[Optional[float]] = []
    for _, row in df.tail(7).iterrows():
        if 'pct_chg' in row and pd.notna(row['pct_chg']):
            pcts.append(float(row['pct_chg']))
        else:
            pcts.append(None)
    return pcts


def compute_change_pct(d1: float, d2: float) -> float:
    """计算 d1 相对 d2 的变化百分比。"""
    if d2 == 0:
        return 0.0
    return (d1 - d2) / abs(d2) * 100


def detect_dif_trend(dif_values: List[float], bar_values: List[float]) -> MACDTrendSignal:
    """
    检测 DIF 连续趋势。

    规则：
    - 连续 >=3 天 DIF 递增 → "upward"
    - 连续 >=3 天 DIF 递减 → "downward"
    - 其他 → "neutral"
    """
    signal = MACDTrendSignal(direction="neutral", streak=0)

    if len(dif_values) < 3:
        return signal

    # 从最新数据向前检查连续递增/递减
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

        # 记录最大连续天数
        if streak_up >= 3:
            signal.direction = "upward"
            signal.streak = streak_up
        elif streak_down >= 3:
            signal.direction = "downward"
            signal.streak = streak_down

    # 为连续趋势生成描述
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
    """
    检测 MACD 柱体（带符号值）的连续趋势方向。

    核心逻辑：
    无论当前是红柱还是绿柱，看 BAR 的**带符号数值**是否在连续递增或递减：
    - 连续 >=3 天 BAR 递增（红柱放大 OR 绿柱缩小）→ 偏多方向
    - 连续 >=3 天 BAR 递减（红柱缩小 OR 绿柱放大）→ 偏空方向

    这比只看绝对值更准确：红柱缩小意味着多头衰减，绿柱缩小意味着空头衰减。
    """
    signal = MACDTrendSignal(direction="neutral", streak=0)

    if len(bar_values) < 3:
        return signal

    # 从最新数据向前检查连续递增/递减
    streak_up = 0   # BAR 值连续增大
    streak_down = 0  # BAR 值连续减小

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
                f"📊 MACD 红柱连续 {streak_up} 天放大，"
                f"多头力量持续增强。"
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
                f"📊 MACD 绿柱连续 {streak_down} 天放大，"
                f"空头力量持续增强。"
            )
        signal.description = f"MACD 柱体连续 {streak_down} 天下降"

    return signal


def detect_turning_point(dif_values: List[float], dif_trend: MACDTrendSignal) -> MACDTurningPoint:
    """
    检测 MACD 趋势加速/转折点。

    规则：
    如果已经处于连续趋势中，且当日 DIF 变化幅度相对前日扩大超过 20%，
    则标记为趋势加速/转折信号。
    """
    result = MACDTurningPoint(detected=False)

    if len(dif_values) < 3 or dif_trend.streak < 2:
        return result

    # 当日 DIF 变化量
    today_diff = dif_values[-1] - dif_values[-2]
    # 前日 DIF 变化量
    prev_diff = dif_values[-2] - dif_values[-3]

    if prev_diff == 0:
        return result

    # 变化幅度的比例
    acceleration = abs(today_diff / prev_diff)

    # 检查方向是否一致（same direction = acceleration, opposite = deceleration/ reversal）
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
    """
    检测金叉/死叉。

    金叉：DIF 上穿 DEA（前日 DIF <= DEA，当日 DIF > DEA）
    死叉：DIF 下穿 DEA（前日 DIF >= DEA，当日 DIF < DEA）
    """
    golden_cross = False
    death_cross = False
    cross_day = -1
    description = ""

    if len(dif_values) < 2:
        return golden_cross, death_cross, cross_day, description

    # 检查最近交易日是否出现交叉
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


def analyze_macd(df: pd.DataFrame) -> MACDAnalysisResult:
    """
    对股票进行完整的 MACD 分析。

    Args:
        df: 包含 MACD_DIF, MACD_DEA, MACD_BAR 列的 DataFrame

    Returns:
        MACDAnalysisResult 分析结果
    """
    result = MACDAnalysisResult()

    # 检查必要的列
    for col in ['MACD_DIF', 'MACD_DEA', 'MACD_BAR']:
        if col not in df.columns:
            result.annotations.append(f"MACD 数据缺失，无法完成分析（缺少 {col}）。")
            return result

    # 取最近 7 个交易日
    recent = df.tail(7).copy()
    if len(recent) < 2:
        result.annotations.append("MACD 数据不足（少于2个交易日），无法进行趋势分析。")
        return result

    # 提取涨跌幅
    change_pcts = extract_change_pcts(df)

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

        day_record = MACDDayRecord(
            date=date_str,
            dif=dif_val,
            dea=dea_val,
            bar=bar_val,
            bar_direction="red" if bar_val >= 0 else "green",
            close=close_val,
            change_pct=change_pcts[i] if i < len(change_pcts) else None,
        )
        result.days.append(day_record)

    # 最新值
    result.latest_dif = difs[-1]
    result.latest_dea = deas[-1]
    result.latest_bar = bars[-1]

    # 计算当日变化幅度
    if len(difs) >= 2:
        prev_dif = difs[-2]
        if prev_dif != 0:
            result.dif_change_pct = compute_change_pct(difs[-1], prev_dif)

    if len(bars) >= 2:
        prev_bar = bars[-2]
        if prev_bar != 0:
            result.bar_change_pct = compute_change_pct(bars[-1], prev_bar)

    # 1. 检测 DIF 趋势
    result.dif_trend = detect_dif_trend(difs, bars)

    # 2. 检测红绿柱趋势
    result.bar_trend = detect_bar_trend(bars)

    # 3. 检测趋势加速/转折点
    result.turning_point = detect_turning_point(difs, result.dif_trend)

    # 4. 检测金叉/死叉
    result.golden_cross, result.death_cross, result.cross_day, result.cross_description = \
        detect_cross(difs, deas)

    # 5. 生成综合标注
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

    # 金叉/死叉标注
    if result.golden_cross:
        cross_annotation = (
            f"🔀 {result.cross_description} "
            f"DIF({difs[result.cross_day]:.4f}) 上穿 DEA({deas[result.cross_day]:.4f})。"
            if result.cross_day >= 0
            else "🔀 金叉出现：DIF 上穿 DEA，买入信号。"
        )
        annotations.append(cross_annotation)
    elif result.death_cross:
        cross_annotation = (
            f"🔀 {result.cross_description} "
            f"DIF({difs[result.cross_day]:.4f}) 下穿 DEA({deas[result.cross_day]:.4f})。"
            if result.cross_day >= 0
            else "🔀 死叉出现：DIF 下穿 DEA，卖出信号。"
        )
        annotations.append(cross_annotation)

    # DIF 与零轴的关系
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
