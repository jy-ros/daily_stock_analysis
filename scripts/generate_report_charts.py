#!/usr/bin/env python3
"""从分析报告 JSON 生成可视化图表 PNG。

用法:
    python scripts/generate_report_charts.py reports/report_YYYYMMDD.json
    python scripts/generate_report_charts.py reports/report_YYYYMMDD.json --outdir reports/charts

输出:
    reports/charts/dashboard_overview.png   — 全局评分总览
    reports/charts/<code>_macd.png          — MACD 7 日走势
    reports/charts/<code>_radar.png         — 六维因子雷达
    reports/charts/<code>_attribution.png   — 信号归因权重
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

plt.rcParams.update({
    "font.sans-serif": [
        "Noto Sans CJK SC", "WenQuanYi Micro Hei", "SimHei",
        "Microsoft YaHei", "PingFang SC", "DejaVu Sans",
    ],
    "axes.unicode_minus": False,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
})

COLORS = {
    "blue": "#3B82F6",
    "red": "#EF4444",
    "green": "#22C55E",
    "orange": "#F97316",
    "purple": "#A855F7",
    "cyan": "#06B6D4",
    "gray": "#9CA3AF",
    "bg": "#FAFBFC",
}


def load_report(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _safe_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _short_name(name: str, max_len: int = 10) -> str:
    return name[:max_len] + "…" if len(name) > max_len else name


# ---------------------------------------------------------------------------
# 1. Dashboard overview — 水平柱状图：评分 + MACD 复合分 + 因子分
# ---------------------------------------------------------------------------
def generate_dashboard_overview(stocks: list[dict], outdir: Path) -> Path | None:
    valid = [
        s for s in stocks
        if s.get("current_price") is not None and s.get("factor_score") is not None
    ]
    if not valid:
        return None
    valid.sort(key=lambda s: _safe_float(s.get("factor_score")), reverse=True)

    labels = [_short_name(f'{s.get("name", "")}({s.get("code", "")})') for s in valid]
    sentiment = [_safe_float(s.get("sentiment_score")) for s in valid]
    factor = [_safe_float(s.get("factor_score")) for s in valid]
    macd_score = [_safe_float(s.get("macd_composite_score")) for s in valid]

    y = np.arange(len(labels))
    height = max(3, len(labels) * 0.45)
    fig, ax = plt.subplots(figsize=(10, height))
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])

    bar_h = 0.25
    ax.barh(y - bar_h, sentiment, bar_h, label="Sentiment", color=COLORS["blue"], alpha=0.85)
    ax.barh(y, macd_score, bar_h, label="MACD", color=COLORS["orange"], alpha=0.85)
    ax.barh(y + bar_h, factor, bar_h, label="Factor", color=COLORS["green"], alpha=0.85)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Score (0–100)")
    ax.set_title("Stock Score Overview", fontsize=13, fontweight="bold", pad=12)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, 105)
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    out = outdir / "dashboard_overview.png"
    fig.savefig(out)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 2. MACD 7-day chart — 柱状图(MACD bar) + 折线(DIF, DEA) + 价格副轴
# ---------------------------------------------------------------------------
def generate_macd_chart(stock: dict, outdir: Path) -> Path | None:
    days = stock.get("macd_7d_days") or []
    if not days:
        return None
    dates = [d.get("date", "") for d in days]
    dif = [_safe_float(d.get("dif")) for d in days]
    dea = [_safe_float(d.get("dea")) for d in days]
    bar = [_safe_float(d.get("bar")) for d in days]
    close = [_safe_float(d.get("close")) for d in days]

    x = np.arange(len(dates))
    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_facecolor(COLORS["bg"])
    ax1.set_facecolor(COLORS["bg"])

    bar_colors = [COLORS["red"] if v >= 0 else COLORS["green"] for v in bar]
    ax1.bar(x, bar, 0.5, color=bar_colors, alpha=0.55, label="MACD Bar")
    ax1.plot(x, dif, "o-", color=COLORS["blue"], linewidth=2, markersize=5, label="DIF")
    ax1.plot(x, dea, "s--", color=COLORS["orange"], linewidth=1.5, markersize=4, label="DEA")
    ax1.axhline(0, color="gray", linewidth=0.5, linestyle="-")
    ax1.set_ylabel("MACD Value")
    ax1.set_xticks(x)
    ax1.set_xticklabels([d[-5:] for d in dates], fontsize=8, rotation=30)
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(axis="y", alpha=0.2)

    if any(c > 0 for c in close):
        ax2 = ax1.twinx()
        ax2.plot(x, close, "D-", color=COLORS["purple"], linewidth=1.5, markersize=4, alpha=0.7, label="Close")
        ax2.set_ylabel("Close Price", color=COLORS["purple"])
        ax2.legend(loc="upper right", fontsize=8)

    name = stock.get("name", stock.get("code", ""))
    code = stock.get("code", "")
    ax1.set_title(f"MACD 7-Day — {name} ({code})", fontsize=12, fontweight="bold", pad=10)

    out = outdir / f"{code}_macd.png"
    fig.savefig(out)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 3. Factor radar chart — 六维雷达图
# ---------------------------------------------------------------------------
def _derive_radar_values(stock: dict) -> dict[str, float]:
    macd_dir = stock.get("macd_trend_direction", "neutral")
    trend = {"upward": 75, "downward": 25}.get(macd_dir, 50)

    macd_cs = _safe_float(stock.get("macd_composite_score"), 50)
    momentum = min(100, max(0, macd_cs))

    vol = _safe_float((stock.get("quant") or {}).get("vol_20d"), 30)
    volatility = max(0, 100 - vol)

    sentiment = _safe_float(stock.get("sentiment_score"), 50)

    factor = _safe_float(stock.get("factor_score"), 50)

    risk = (stock.get("quant") or {}).get("risk_level", "中")
    risk_val = {"低": 80, "中": 50, "高": 20}.get(risk, 50)

    return {
        "Trend": trend,
        "Momentum": momentum,
        "Volatility": volatility,
        "Sentiment": sentiment,
        "Factor": factor,
        "Risk": risk_val,
    }


def generate_radar_chart(stock: dict, outdir: Path) -> Path | None:
    dims = _derive_radar_values(stock)
    labels = list(dims.keys())
    values = list(dims.values())
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values_closed = values + [values[0]]
    angles_closed = angles + [angles[0]]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(COLORS["bg"])

    ax.fill(angles_closed, values_closed, color=COLORS["blue"], alpha=0.15)
    ax.plot(angles_closed, values_closed, "o-", color=COLORS["blue"], linewidth=2, markersize=6)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80])
    ax.set_yticklabels(["20", "40", "60", "80"], fontsize=7, color="gray")
    ax.grid(color="gray", linewidth=0.3, alpha=0.5)

    for angle, label, val in zip(angles, labels, values):
        ax.annotate(f"{val:.0f}", xy=(angle, val), fontsize=8,
                    ha="center", va="bottom", fontweight="bold", color=COLORS["blue"])

    name = stock.get("name", stock.get("code", ""))
    code = stock.get("code", "")
    ax.set_title(f"Factor Radar — {name} ({code})", fontsize=12, fontweight="bold", pad=20)

    out = outdir / f"{code}_radar.png"
    fig.savefig(out)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 4. Signal attribution — 环形图(技术/新闻/基本面/市场)
# ---------------------------------------------------------------------------
def generate_attribution_chart(stock: dict, outdir: Path) -> Path | None:
    dashboard = stock.get("dashboard") or {}
    attr = dashboard.get("signal_attribution") or {}
    weights_raw = attr.get("weights") or {}
    if not weights_raw:
        weights_raw = {
            "technical_indicators": _safe_float(attr.get("technical_indicators"), 70),
            "news_sentiment": _safe_float(attr.get("news_sentiment"), 10),
            "fundamentals": _safe_float(attr.get("fundamentals"), 10),
            "market_conditions": _safe_float(attr.get("market_conditions"), 10),
        }

    label_map = {
        "technical_indicators": "Technical",
        "news_sentiment": "News",
        "fundamentals": "Fundamental",
        "market_conditions": "Market",
    }
    colors = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["purple"]]

    keys = list(label_map.keys())
    vals = [_safe_float(weights_raw.get(k)) for k in keys]
    total = sum(vals) or 1
    vals = [v / total * 100 for v in vals]
    labels = [label_map[k] for k in keys]

    fig, ax = plt.subplots(figsize=(5, 5))
    fig.patch.set_facecolor(COLORS["bg"])

    wedges, texts, autotexts = ax.pie(
        vals, labels=labels, colors=colors, autopct="%1.0f%%",
        startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.4, edgecolor="white", linewidth=2),
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_fontweight("bold")

    bull = (attr.get("strongest_bull_signal") or "")[:40]
    bear = (attr.get("strongest_bear_signal") or "")[:40]
    info = f"Bull: {bull}\nBear: {bear}" if bull or bear else ""
    if info:
        ax.text(0, -0.1, info, ha="center", va="top", fontsize=7.5, style="italic", color="gray",
                transform=ax.transAxes)

    name = stock.get("name", stock.get("code", ""))
    code = stock.get("code", "")
    ax.set_title(f"Signal Attribution — {name} ({code})", fontsize=12, fontweight="bold", pad=12)

    out = outdir / f"{code}_attribution.png"
    fig.savefig(out)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate visual charts from report JSON")
    parser.add_argument("json_path", help="Path to report JSON file")
    parser.add_argument("--outdir", default=None, help="Output directory for chart images")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"Error: {json_path} not found")
        sys.exit(1)

    outdir = Path(args.outdir) if args.outdir else json_path.parent / "charts"
    outdir.mkdir(parents=True, exist_ok=True)

    stocks = load_report(json_path)
    print(f"Loaded {len(stocks)} stocks from {json_path}")

    generated = []

    overview = generate_dashboard_overview(stocks, outdir)
    if overview:
        generated.append(overview)
        print(f"  [overview] {overview.name}")

    for stock in stocks:
        code = stock.get("code", "unknown")
        for fn, suffix in [
            (generate_macd_chart, "_macd.png"),
            (generate_radar_chart, "_radar.png"),
            (generate_attribution_chart, "_attribution.png"),
        ]:
            try:
                result = fn(stock, outdir)
                if result:
                    generated.append(result)
                    print(f"  [{code}] {result.name}")
            except Exception as e:
                print(f"  [{code}] {suffix} failed: {e}")

    print(f"\nGenerated {len(generated)} chart(s) in {outdir}")


if __name__ == "__main__":
    main()
