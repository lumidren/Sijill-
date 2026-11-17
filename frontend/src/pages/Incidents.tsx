import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { BreachClock, type Clock } from "../components/BreachClock";
import { EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi, useNow } from "../hooks";
import { fmtDateTime } from "../i18n";

export interface IncidentRow {
  id: number;
  ref: string;
  title: string;
  description: string;
  status: "open" | "contained" | "notified" | "closed";
  severity: "low" | "medium" | "high";
  discovered_at: string;
  occurred_at: string | null;
  data_categories: string[];
  affected_count: number | null;
  systems: string[];
  likely_consequences: string;
  measures_taken: string;
  contact: string;
  individuals_notice_needed: boolean | null;
  regulator_notified_at: string | null;
  individuals_notified_at: string | null;
  source: { run_id?: number | null; check_id?: string };
  clocks: { regulator: Clock; individuals: Clock; regulator_hours: number; individuals_hours: number };
}

/** Value for <input type="datetime-local"> showing an ISO instant in Cairo time. */
export function toCairoInput(iso: string | null): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso));
  const g = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${g("year")}-${g("month")}-${g("day")}T${g("hour")}:${g("minute")}`;
}

export const EMPTY_INCIDENT = {
  title: "", description: "", severity: "medium", discovered_at: "", occurred_at: "", data_categories: "", affected_count: "",
  systems: "", likely_consequences: "", measures_taken: "", contact: "", individuals_notice_needed: "undecided",
};
export type IncidentDraft = typeof EMPTY_INCIDENT;

export function draftFrom(i: IncidentRow): IncidentDraft {
  return {
    title: i.title, description: i.description, severity: i.severity, discovered_at: toCairoInput(i.discovered_at),
    occurred_at: toCairoInput(i.occurred_at), data_categories: i.data_categories.join("\n"),
    affected_count: i.affected_count == null ? "" : String(i.affected_count), systems: i.systems.join("\n"),
    likely_consequences: i.likely_consequences, measures_taken: i.measures_taken, contact: i.contact,
    individuals_notice_needed: i.individuals_notice_needed == null ? "undecided" : i.individuals_notice_needed ? "yes" : "no",
  };
}

export function bodyFrom(d: IncidentDraft) {
  const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
  return {
    title: d.title, description: d.description, severity: d.severity,
    // datetime-local values carry no offset; the server reads them as Cairo time
    discovered_at: d.discovered_at, occurred_at: d.occurred_at || null,
    data_categories: lines(d.data_categories), affected_count: d.affected_count === "" ? null : Number(d.affected_count),
    systems: lines(d.systems), likely_consequences: d.likely_consequences, measures_taken: d.measures_taken, contact: d.contact,
    individuals_notice_needed: d.individuals_notice_needed === "undecided" ? null : d.individuals_notice_needed === "yes",
  };
}

export function IncidentFields({ d, set }: { d: IncidentDraft; set: (d: IncidentDraft) => void }) {
  const { t } = useTranslation();
  const f = (k: keyof IncidentDraft, label: string, type: "text" | "area" | "datetime-local" | "number" = "text") => (
    <div>
      <label className="label" htmlFor={`i-${k}`}>
        {label}
      </label>
      {type === "area" ? (
        <textarea id={`i-${k}`} className="input min-h-[72px]" value={d[k]} onChange={(e) => set({ ...d, [k]: e.target.value })} />
      ) : (
        <input id={`i-${k}`} type={type} min={type === "number" ? 0 : undefined} className="input" value={d[k]} onChange={(e) => set({ ...d, [k]: e.target.value })} required={k === "title" || k === "discovered_at"} autoFocus={k === "title"} />
      )}
    </div>
  );
  return (
    <div className="space-y-4">
      {f("title", t("incidents.fields.title"))}
      <div className="grid gap-4 sm:grid-cols-2">
        {f("discovered_at", t("incidents.fields.discovered"), "datetime-local")}
        {f("occurred_at", t("incidents.fields.occurred"), "datetime-local")}
      </div>
      {f("description", t("incidents.fields.description"), "area")}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="i-severity">
            {t("incidents.fields.severity")}
          </label>
          <select id="i-severity" className="input" value={d.severity} onChange={(e) => set({ ...d, severity: e.target.value })}>
            {(["low", "medium", "high"] as const).map((s) => (
              <option key={s} value={s}>
                {t(`incidents.severities.${s}`)}
              </option>
            ))}
          </select>
        </div>
        {f("affected_count", t("incidents.fields.affected"), "number")}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {f("data_categories", t("incidents.fields.dataCategories"), "area")}
        {f("systems", t("incidents.fields.systems"), "area")}
      </div>
      {f("likely_consequences", t("incidents.fields.consequences"), "area")}
      {f("measures_taken", t("incidents.fields.measures"), "area")}
      {f("contact", t("incidents.fields.contact"))}
      <div>
        <label className="label" htmlFor="i-needed">
          {t("incidents.fields.individualsNeeded")}
        </label>
        <select id="i-needed" className="input" value={d.individuals_notice_needed} onChange={(e) => set({ ...d, individuals_notice_needed: e.target.value })}>
          {(["undecided", "yes", "no"] as const).map((v) => (
            <option key={v} value={v}>
              {t(`incidents.needed.${v}`)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export function errorText(t: TFunction, err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 422 && err.code !== "validation_error") return t(`incidents.errors.${err.code}`, { defaultValue: t("errors.validation_error") });
    if (err.status === 422) return t("errors.validation_error");
    if (err.status === 403) return t("common.forbidden");
  }
  return t("common.error");
}

function NewIncident({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [d, setD] = useState<IncidentDraft>({ ...EMPTY_INCIDENT, discovered_at: toCairoInput(new Date().toISOString()) });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<IncidentRow>("/api/incidents", bodyFrom(d));
      navigate(`/incidents/${r.id}`);
    } catch (ex) {
      setErr(errorText(t, ex));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" aria-labelledby="new-incident-title" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form onSubmit={submit} className="flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 id="new-incident-title" className="text-lg font-semibold">
            {t("incidents.new")}
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t("common.close")}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <IncidentFields d={d} set={setD} />
          {err && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {err}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <button type="button" className="btn-secondary" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button className="btn-primary" disabled={busy || !d.title.trim() || !d.discovered_at}>
            {busy ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Incidents() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<IncidentRow[]>("/api/incidents");
  const now = useNow(1000);
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader
        title={t("incidents.title")}
        subtitle={t("incidents.subtitle")}
        actions={
          can("incidents.write") && (
            <button className="btn-danger" onClick={() => setCreating(true)}>
              + {t("incidents.new")}
            </button>
          )
        }
      />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : !data?.length ? (
        <EmptyState title={t("incidents.empty")} hint={t("incidents.emptyHint")} />
      ) : (
        <ul className="space-y-4">
          {data.map((i) => (
            <li key={i.id} className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs text-slate-500">
                    <span dir="ltr">{i.ref}</span> • {t(`incidents.severities.${i.severity}`)} • {fmtDateTime(i.discovered_at)}
                  </p>
                  <Link to={`/incidents/${i.id}`} className="text-base font-semibold text-ink hover:text-brand-800 hover:underline">
                    {i.title}
                  </Link>
                </div>
                <span className="chip bg-slate-100 text-slate-700">{t(`incidents.statuses.${i.status}`)}</span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <BreachClock label={t("incidents.clocks.regulator")} clock={i.clocks.regulator} now={now} size="sm" />
                <BreachClock label={t("incidents.clocks.individuals")} clock={i.clocks.individuals} now={now} size="sm" />
              </div>
            </li>
          ))}
        </ul>
      )}
      {creating && <NewIncident onClose={() => setCreating(false)} />}
    </>
  );
}
