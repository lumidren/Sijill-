import { Area, AreaChart, CartesianGrid, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";
import { fmtDate, fmtDateTime, fmtNum } from "../i18n";

export function ScoreRing({ value, size = 168, label }: { value: number | null; size?: number; label: string }) {
  const r = (size - 18) / 2;
  const c = 2 * Math.PI * r;
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <div className="relative" style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-slate-100)" strokeWidth="14" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-brand-600)"
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden>
        <span className="text-4xl font-semibold tracking-tight text-ink">{value == null ? "—" : fmtNum(Math.round(pct * 100))}</span>
        <span className="text-xs text-slate-500">/ {fmtNum(100)}</span>
      </div>
    </div>
  );
}

export interface Segment {
  key: string;
  label: string;
  value: number;
  className: string;
}

export function StackedBar({ segments, total, title }: { segments: Segment[]; total: number; title: string }) {
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${title}: ${segments.map((s) => `${s.label} ${s.value}`).join(", ")}`}>
        {segments.map((s) =>
          s.value > 0 ? <div key={s.key} className={`${s.className} h-full first:rounded-s-full last:rounded-e-full`} style={{ width: `${(s.value / Math.max(total, 1)) * 100}%` }} /> : null,
        )}
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-3">
        {segments.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-sm ${s.className}`} />
            <span className="text-slate-600">{s.label}</span>
            <span className="ms-auto font-semibold tabular-nums text-ink sm:ms-1">{fmtNum(s.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface TrendPoint {
  at: string;
  overall: number;
  reason: string;
}

/** Score over time. Points where the score fell after a check run are marked. */
export function TrendChart({ data, height = 240 }: { data: TrendPoint[]; height?: number }) {
  const { t, i18n } = useTranslation();
  const rtl = i18n.language === "ar";
  const points = data.map((d) => ({ ...d, ts: new Date(d.at).getTime(), pct: Math.round(d.overall * 1000) / 10 }));
  const dips = points.filter((p, i) => i > 0 && p.reason === "check_run" && p.pct < points[i - 1].pct - 0.05);
  return (
    <div style={{ height }} dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="scoreFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#149a8d" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#149a8d" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            reversed={rtl}
            tickFormatter={(v) => fmtDate(new Date(v).toISOString())}
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
            minTickGap={28}
          />
          <YAxis
            domain={[0, 100]}
            orientation={rtl ? "right" : "left"}
            tickFormatter={(v) => fmtNum(v)}
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
            width={34}
          />
          <Tooltip
            formatter={(v) => [fmtNum(Number(v), 1), t("dashboard.scoreTitle")]}
            labelFormatter={(v) => fmtDateTime(new Date(Number(v)).toISOString())}
            contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12, direction: rtl ? "rtl" : "ltr" }}
          />
          <Area type="monotone" dataKey="pct" stroke="#0d7b72" strokeWidth={2.5} fill="url(#scoreFill)" dot={{ r: 2.5, fill: "#0d7b72" }} isAnimationActive={false} />
          {dips.map((d) => (
            <ReferenceDot key={d.ts} x={d.ts} y={d.pct} r={6} fill="#dc2626" stroke="#fff" strokeWidth={2} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MiniBar({ value, className = "bg-brand-600" }: { value: number | null; className?: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div className={`h-full rounded-full ${className}`} style={{ width: `${Math.round((value ?? 0) * 100)}%` }} />
    </div>
  );
}
