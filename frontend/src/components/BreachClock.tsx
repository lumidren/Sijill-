import { useTranslation } from "react-i18next";
import { fmtDateTime, fmtNum } from "../i18n";

export type ClockState = "running" | "warning" | "urgent" | "overdue" | "met" | "met_late" | "not_needed";

export interface Clock {
  due: string;
  done_at: string | null;
  state: ClockState;
  seconds_left: number | null;
}

/** "41 h 12 m", "2 d 5 h", "12 m 30 s" with localised digits and units. */
export function useDuration() {
  const { t } = useTranslation();
  return (totalSeconds: number) => {
    const s = Math.max(0, Math.floor(Math.abs(totalSeconds)));
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const u = (n: number, unit: string) => `${fmtNum(n)} ${t(`incidents.units.${unit}`)}`;
    if (d >= 2) return `${u(d, "d")} ${u(h, "h")}`;
    if (s >= 3600) return `${u(d * 24 + h, "h")} ${u(m, "m")}`;
    return `${u(m, "m")} ${u(sec, "s")}`;
  };
}

/** Recompute the live state on the client from the due time (the server value is only a snapshot). */
export function liveState(c: Clock, now: Date): { state: ClockState; secondsLeft: number | null } {
  if (c.done_at || c.state === "not_needed") return { state: c.state, secondsLeft: null };
  const left = (new Date(c.due).getTime() - now.getTime()) / 1000;
  const state: ClockState = left < 0 ? "overdue" : left <= 12 * 3600 ? "urgent" : left <= 24 * 3600 ? "warning" : "running";
  return { state, secondsLeft: left };
}

const TONE: Record<ClockState, string> = {
  running: "border-slate-200 bg-white",
  warning: "border-amber-300 bg-amber-50",
  urgent: "border-red-300 bg-red-50",
  overdue: "border-red-600 bg-red-600 text-white",
  met: "border-green-200 bg-green-50",
  met_late: "border-amber-300 bg-amber-50",
  not_needed: "border-slate-200 bg-slate-50",
};

export function BreachClock({ label, clock, now, hours, size = "lg" }: { label: string; clock: Clock; now: Date; hours?: number; size?: "lg" | "sm" }) {
  const { t } = useTranslation();
  const dur = useDuration();
  const { state, secondsLeft } = liveState(clock, now);
  const big =
    state === "met" || state === "met_late"
      ? t(`incidents.clocks.${state}`, { when: fmtDateTime(clock.done_at) })
      : state === "not_needed"
        ? t("incidents.clocks.not_needed")
        : state === "overdue"
          ? t("incidents.clocks.overdue", { time: dur(secondsLeft ?? 0) })
          : t("incidents.clocks.left", { time: dur(secondsLeft ?? 0) });
  return (
    <section className={`rounded-2xl border p-4 ${TONE[state]} ${state === "urgent" ? "motion-safe:animate-pulse" : ""}`} aria-live="polite" aria-label={`${label}: ${big}`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className={`text-sm font-semibold ${state === "overdue" ? "text-white" : "text-slate-700"}`}>{label}</h3>
        <span className={`chip ${state === "overdue" ? "bg-white/20 text-white" : state === "urgent" ? "bg-red-600 text-white" : state === "warning" ? "bg-amber-200 text-amber-900" : "bg-slate-100 text-slate-700"}`}>
          {t(`incidents.states.${state}`)}
        </span>
      </div>
      <p className={`mt-2 font-semibold tabular-nums ${size === "lg" ? "text-2xl" : "text-base"}`}>{big}</p>
      {state !== "not_needed" && (
        <p className={`mt-1 text-xs ${state === "overdue" ? "text-white/90" : "text-slate-600"}`}>{t("incidents.clocks.due", { when: fmtDateTime(clock.due) })}</p>
      )}
      {hours != null && size === "lg" && <p className={`mt-1 text-[11px] ${state === "overdue" ? "text-white/80" : "text-slate-500"}`}>{t("incidents.clocks.rule", { hours: fmtNum(hours) })}</p>}
    </section>
  );
}
