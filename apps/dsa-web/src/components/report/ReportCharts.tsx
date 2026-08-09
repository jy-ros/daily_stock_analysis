import React, { useMemo } from 'react';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, RadarChart, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';
import type { UiLanguage } from '../../i18n/uiText';

interface ReportChartsProps {
  rawResult?: Record<string, unknown>;
  sentimentScore?: number | null;
  language: UiLanguage;
}

const LABELS = {
  zh: {
    macdTitle: 'MACD 趋势 (7日)',
    radarTitle: '多维因子评分',
    priceTitle: '近期价格走势',
    dif: 'DIF',
    dea: 'DEA',
    bar: 'MACD柱',
    price: '收盘价',
    trend: '趋势',
    momentum: '动量',
    volatility: '波动率',
    sentiment: '情绪',
    factor: '因子',
    risk: '风险',
  },
  en: {
    macdTitle: 'MACD Trend (7D)',
    radarTitle: 'Factor Radar',
    priceTitle: 'Recent Price',
    dif: 'DIF',
    dea: 'DEA',
    bar: 'MACD Bar',
    price: 'Close',
    trend: 'Trend',
    momentum: 'Momentum',
    volatility: 'Volatility',
    sentiment: 'Sentiment',
    factor: 'Factor',
    risk: 'Risk',
  },
} as const;

function toNum(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  return undefined;
}

function extractMacdData(raw: Record<string, unknown>): Array<Record<string, unknown>> {
  const days = raw['macd_7d_days'];
  if (!Array.isArray(days)) return [];
  return days.map((d: Record<string, unknown>) => ({
    date: typeof d['date'] === 'string' ? (d['date'] as string).slice(5) : '',
    dif: toNum(d['dif']),
    dea: toNum(d['dea']),
    bar: toNum(d['bar']),
    close: toNum(d['close']),
  }));
}

function extractRadarData(raw: Record<string, unknown>, sentimentScore: number | null | undefined, language: UiLanguage) {
  const labels = LABELS[language];
  const quant = raw['quant'] as Record<string, unknown> | undefined;
  const macdScore = toNum(raw['macd_composite_score']);
  const factorScore = toNum(raw['factor_score']);
  const vol20d = toNum(quant?.['vol_20d']);
  const riskLevel = quant?.['risk_level'];
  const riskScore = riskLevel === '低' ? 80 : riskLevel === '中' ? 50 : riskLevel === '高' ? 20 : null;

  // Trend: derive from macd_trend_direction
  const trendDir = raw['macd_trend_direction'];
  const trendScore = trendDir === 'upward' ? 75 : trendDir === 'downward' ? 25 : 50;

  // Volatility: inverse of vol_20d (lower vol = higher score)
  const volScore = vol20d != null ? Math.max(0, Math.min(100, 100 - vol20d * 2)) : null;

  return [
    { dimension: labels.trend, value: trendScore, fullMark: 100 },
    { dimension: labels.momentum, value: macdScore, fullMark: 100 },
    { dimension: labels.volatility, value: volScore, fullMark: 100 },
    { dimension: labels.sentiment, value: sentimentScore, fullMark: 100 },
    { dimension: labels.factor, value: factorScore, fullMark: 100 },
    { dimension: labels.risk, value: riskScore, fullMark: 100 },
  ].filter((d) => d.value != null) as Array<{ dimension: string; value: number; fullMark: number }>;
}

export const ReportCharts: React.FC<ReportChartsProps> = ({ rawResult, sentimentScore, language }) => {
  const labels = LABELS[language];

  const macdData = useMemo(
    () => (rawResult ? extractMacdData(rawResult) : []),
    [rawResult],
  );

  const radarData = useMemo(
    () => (rawResult ? extractRadarData(rawResult, sentimentScore) : []),
    [rawResult, sentimentScore],
  );

  const priceData = useMemo(() => macdData.filter((d) => d.close != null), [macdData]);

  if (!rawResult || (macdData.length === 0 && radarData.length === 0)) return null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* MACD Chart */}
      {macdData.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-card/60 p-4">
          <h3 className="label-uppercase mb-3">{labels.macdTitle}</h3>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={macdData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#888' }} />
                <YAxis tick={{ fontSize: 10, fill: '#888' }} />
                <Tooltip
                  contentStyle={{ background: 'rgba(15,15,25,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }}
                />
                <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
                <Bar dataKey="bar" fill="rgba(99,102,241,0.4)" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="dif" stroke="#f59e0b" strokeWidth={1.5} dot={false} name={labels.dif} />
                <Line type="monotone" dataKey="dea" stroke="#6366f1" strokeWidth={1.5} dot={false} name={labels.dea} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Factor Radar */}
      {radarData.length >= 3 && (
        <div className="rounded-xl border border-white/10 bg-card/60 p-4">
          <h3 className="label-uppercase mb-3">{labels.radarTitle}</h3>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                <PolarGrid stroke="rgba(255,255,255,0.1)" />
                <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 10, fill: '#aaa' }} />
                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9, fill: '#666' }} />
                <Radar
                  name="Score"
                  dataKey="value"
                  stroke="#6366f1"
                  fill="rgba(99,102,241,0.25)"
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Price Trend */}
      {priceData.length >= 2 && (
        <div className="rounded-xl border border-white/10 bg-card/60 p-4 lg:col-span-2">
          <h3 className="label-uppercase mb-3">{labels.priceTitle}</h3>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={priceData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#888' }} />
                <YAxis tick={{ fontSize: 10, fill: '#888' }} domain={['dataMin - 1', 'dataMax + 1']} />
                <Tooltip
                  contentStyle={{ background: 'rgba(15,15,25,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }}
                  formatter={(value) => [`${Number(value).toFixed(2)}`, labels.price]}
                />
                <Line type="monotone" dataKey="close" stroke="#22c55e" strokeWidth={2} dot={{ r: 3, fill: '#22c55e' }} name={labels.price} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};
