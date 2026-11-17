import { useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api";
import { fmtNum } from "../i18n";

export type Draft = Record<string, string | boolean>;

export interface Field {
  key: string;
  label: string;
  type?: "text" | "textarea" | "date" | "datetime-local" | "select" | "number" | "lines" | "checkbox";
  options?: { value: string; label: string }[];
  required?: boolean;
  hint?: string;
  dir?: "ltr" | "rtl";
  show?: (d: Draft) => boolean;
  half?: boolean;
}

/** Side-panel form driven by a field list. "lines" fields are edited one item per line. */
export function RecordForm({ title, fields, initial, onSubmit, onClose, footer }: {
  title: string;
  fields: Field[];
  initial: Draft;
  onSubmit: (d: Draft) => Promise<unknown>;
  onClose: () => void;
  footer?: ReactNode | ((d: Draft) => ReactNode);
}) {
  const { t } = useTranslation();
  const [d, setD] = useState<Draft>(initial);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const first = fields.find((f) => f.type !== "checkbox" && f.type !== "select")?.key;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await onSubmit(d);
      onClose();
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 422) setErr(ex.code === "validation_error" ? t("errors.validation_error") : `${t("errors.validation_error")} (${ex.code})`);
      else if (ex instanceof ApiError && ex.status === 403) setErr(t("common.forbidden"));
      else setErr(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  const visible = fields.filter((f) => !f.show || f.show(d));
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" aria-labelledby="record-form-title" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form onSubmit={submit} className="flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 id="record-form-title" className="text-lg font-semibold">
            {title}
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t("common.close")}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {visible.map((f) => {
              const id = `rf-${f.key}`;
              const v = d[f.key];
              const span = f.half ? "" : "sm:col-span-2";
              if (f.type === "checkbox")
                return (
                  <label key={f.key} className={`flex items-center gap-2 text-sm font-medium ${span}`}>
                    <input id={id} type="checkbox" className="h-4 w-4 accent-brand-700" checked={!!v} onChange={(e) => setD({ ...d, [f.key]: e.target.checked })} />
                    {f.label}
                  </label>
                );
              return (
                <div key={f.key} className={span}>
                  <label className="label" htmlFor={id}>
                    {f.label}
                  </label>
                  {f.type === "select" ? (
                    <select id={id} className="input" value={String(v ?? "")} onChange={(e) => setD({ ...d, [f.key]: e.target.value })} required={f.required}>
                      {f.options?.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  ) : f.type === "textarea" || f.type === "lines" ? (
                    <textarea id={id} className="input min-h-[72px]" value={String(v ?? "")} onChange={(e) => setD({ ...d, [f.key]: e.target.value })} dir={f.dir} aria-describedby={f.hint ? `${id}-h` : undefined} />
                  ) : (
                    <input
                      id={id}
                      type={f.type ?? "text"}
                      className="input"
                      value={String(v ?? "")}
                      onChange={(e) => setD({ ...d, [f.key]: e.target.value })}
                      required={f.required}
                      autoFocus={f.key === first}
                      dir={f.dir}
                      aria-describedby={f.hint ? `${id}-h` : undefined}
                    />
                  )}
                  {f.hint && (
                    <p id={`${id}-h`} className="mt-1 text-xs text-slate-500">
                      {f.hint}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
          {err && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {err}
            </p>
          )}
          {typeof footer === "function" ? footer(d) : footer}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <button type="button" className="btn-secondary" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button className="btn-primary" disabled={busy}>
            {busy ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export const lines = (v: string | boolean | undefined) =>
  String(v ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

export const orNull = (v: string | boolean | undefined) => (v === "" || v === undefined ? null : v);

export function DaysChip({ days, done }: { days: number | null | undefined; done?: boolean }) {
  const { t } = useTranslation();
  if (days == null || done) return null;
  const cls = days < 0 ? "bg-red-600 text-white" : days <= 7 ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-700";
  const text = days < 0 ? t("gov.overdueBy", { days: fmtNum(-days) }) : days === 0 ? t("gov.dueToday") : t("gov.dueIn", { days: fmtNum(days) });
  return <span className={`chip ${cls}`}>{text}</span>;
}

export const LEVEL_STYLE: Record<string, string> = {
  low: "bg-green-50 text-green-800 ring-1 ring-green-600/20",
  medium: "bg-amber-50 text-amber-800 ring-1 ring-amber-600/25",
  high: "bg-orange-100 text-orange-900 ring-1 ring-orange-600/30",
  critical: "bg-red-600 text-white",
};

/** Turn an API row into form values: numbers to strings, lists to one item per line, nulls to "". */
export function toDraft(row: object): Draft {
  const out: Draft = {};
  for (const [k, v] of Object.entries(row)) {
    if (typeof v === "string" || typeof v === "boolean") out[k] = v;
    else if (typeof v === "number") out[k] = String(v);
    else if (Array.isArray(v) && v.every((x) => typeof x === "string")) out[k] = v.join("\n");
    else if (v == null) out[k] = "";
  }
  return out;
}
