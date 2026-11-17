import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtNum } from "../i18n";

type Kind = "licence" | "permit" | "dpo_registration" | "consent_mechanism" | "cross_border_flow" | "other";
type Status = "planned" | "applied" | "active" | "expired" | "not_needed";
const KINDS: Kind[] = ["licence", "permit", "dpo_registration", "consent_mechanism", "cross_border_flow", "other"];
const STATUSES: Status[] = ["planned", "applied", "active", "expired", "not_needed"];

interface Item {
  id: number;
  kind: Kind;
  title: string;
  reference: string;
  status: Status;
  effective_status: Status;
  issued_on: string | null;
  expires_on: string | null;
  review_due: string | null;
  expiry_from_default: boolean;
  days_to_expiry: number | null;
  days_to_review: number | null;
  owner: string;
  notes: string;
}

interface ReminderRow {
  id: number;
  kind: "expiry" | "review";
  due: string;
  days_left: number;
  obligation: { id: number; title: string; kind: Kind };
}

type Answers = Record<string, boolean | null | undefined>;
interface Questionnaires {
  licensing: { questions: string[]; answers: Answers; results: { key: string; kind: Kind; question: string; likely_required: boolean | null }[]; notes: string[] };
  applicability: { questions: string[]; answers: Answers; result: string; reason: string | null };
  licence_validity_years: number;
}

function DaysChip({ days }: { days: number | null }) {
  const { t } = useTranslation();
  if (days == null) return null;
  const cls = days < 0 ? "bg-red-600 text-white" : days <= 14 ? "bg-amber-100 text-amber-900" : days <= 90 ? "bg-sky-50 text-sky-800" : "bg-slate-100 text-slate-600";
  const text = days < 0 ? t("obligations.overdue", { days: fmtNum(-days) }) : days === 0 ? t("obligations.today") : t("obligations.inDays", { days: fmtNum(days) });
  return <span className={`chip ${cls}`}>{text}</span>;
}

const EMPTY = { kind: "permit" as Kind, title: "", reference: "", status: "planned" as Status, issued_on: "", expires_on: "", review_due: "", owner: "", notes: "" };

function ItemForm({ initial, id, years, onClose, onSaved }: { initial: typeof EMPTY; id: number | null; years: number; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [d, setD] = useState(initial);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const body = { ...d, issued_on: d.issued_on || null, expires_on: d.expires_on || null, review_due: d.review_due || null };
    try {
      if (id) await api.put(`/api/obligations/${id}`, body);
      else await api.post("/api/obligations", body);
      onSaved();
      onClose();
    } catch (ex) {
      setErr(ex instanceof ApiError && ex.status === 422 ? t("errors.validation_error") : t("common.error"));
    } finally {
      setBusy(false);
    }
  }
  const field = (k: keyof typeof EMPTY, label: string, type = "text") => (
    <div>
      <label className="label" htmlFor={`o-${k}`}>
        {label}
      </label>
      <input id={`o-${k}`} type={type} className="input" value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} required={k === "title"} autoFocus={k === "title"} />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" aria-labelledby="o-dialog-title" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form onSubmit={submit} className="flex h-full w-full max-w-lg flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 id="o-dialog-title" className="text-lg font-semibold">
            {id ? t("obligations.edit") : t("obligations.add")}
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t("common.close")}
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="o-kind">
                {t("obligations.kind")}
              </label>
              <select id="o-kind" className="input" value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value as Kind })}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`obligations.kinds.${k}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="o-status">
                {t("obligations.status")}
              </label>
              <select id="o-status" className="input" value={d.status} onChange={(e) => setD({ ...d, status: e.target.value as Status })}>
                {STATUSES.filter((s) => s !== "expired").map((s) => (
                  <option key={s} value={s}>
                    {t(`obligations.statuses.${s}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {field("title", t("obligations.itemTitle"))}
          {field("reference", t("obligations.reference"))}
          <div className="grid gap-4 sm:grid-cols-3">
            {field("issued_on", t("obligations.issuedOn"), "date")}
            {field("expires_on", t("obligations.expiresOn"), "date")}
            {field("review_due", t("obligations.reviewDue"), "date")}
          </div>
          {d.kind === "licence" && <p className="text-xs text-slate-500">{t("obligations.defaultExpiryHint", { years: fmtNum(years) })}</p>}
          {field("owner", t("obligations.owner"))}
          <div>
            <label className="label" htmlFor="o-notes">
              {t("obligations.notesLabel")}
            </label>
            <textarea id="o-notes" className="input min-h-[72px]" value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} maxLength={4000} />
          </div>
          {err && (
            <p role="alert" className="text-sm text-red-700">
              {err}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <button type="button" className="btn-secondary" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button className="btn-primary" disabled={busy || !d.title.trim()}>
            {busy ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </form>
    </div>
  );
}

function YesNo({ name, value, onChange, disabled }: { name: string; value: boolean | null | undefined; onChange: (v: boolean | null) => void; disabled: boolean }) {
  // the question text carries id `${name}-q`; the group is named by it
  const { t } = useTranslation();
  const opts: [boolean | null, string][] = [
    [true, t("obligations.yes")],
    [false, t("obligations.no")],
    [null, t("obligations.unsure")],
  ];
  return (
    <div role="radiogroup" aria-labelledby={`${name}-q`} className="flex gap-1.5">
      {opts.map(([v, label]) => (
        <label key={String(v)} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-400 ${(value ?? null) === v ? "border-brand-500 bg-brand-50 font-medium" : "border-slate-200"} ${disabled ? "cursor-not-allowed opacity-70" : ""}`}>
          <input type="radio" className="sr-only" name={name} checked={(value ?? null) === v} onChange={() => onChange(v)} disabled={disabled} />
          {label}
        </label>
      ))}
    </div>
  );
}

function Licensing({ q, reload, onTrack, canEdit, trackedTitles }: { q: Questionnaires; reload: () => void; onTrack: (key: string, kind: Kind) => void; canEdit: boolean; trackedTitles: string[] }) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<Answers>(q.licensing.answers);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setAnswers(q.licensing.answers), [q]);
  return (
    <div className="grid gap-5 xl:grid-cols-5">
      <Card className="xl:col-span-3">
        <ol className="space-y-4">
          {q.licensing.questions.map((k, i) => (
            <li key={k} className="flex flex-col gap-2 border-b border-slate-100 pb-4 last:border-0 sm:flex-row sm:items-center sm:justify-between">
              <span id={`lic-${k}-q`} className="text-sm text-slate-800">
                <span className="me-2 text-slate-500">{fmtNum(i + 1)}.</span>
                {t(`obligations.questions.${k}`)}
              </span>
              <YesNo name={`lic-${k}`} value={answers[k]} onChange={(v) => setAnswers({ ...answers, [k]: v })} disabled={!canEdit} />
            </li>
          ))}
        </ol>
        {canEdit && (
          <div className="mt-4 flex items-center gap-3">
            <button
              className="btn-primary"
              onClick={async () => {
                await api.put("/api/obligations/questionnaires/licensing", { answers });
                setMsg(t("obligations.saved"));
                reload();
              }}
            >
              {t("obligations.save")}
            </button>
            {msg && (
              <span role="status" className="text-sm text-green-700">
                {msg}
              </span>
            )}
          </div>
        )}
      </Card>
      <Card className="xl:col-span-2" title={t("obligations.likely")}>
        <ul className="space-y-3">
          {q.licensing.results.map((r) => (
            <li key={r.key} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3">
              <div>
                <div className="text-sm font-medium">{t(`obligations.results.${r.key}`)}</div>
                <div className={`text-xs ${r.likely_required ? "text-amber-800" : "text-slate-500"}`}>
                  {r.likely_required === true ? t("obligations.likely") : r.likely_required === false ? t("obligations.likelyNot") : t("obligations.unknown")}
                </div>
              </div>
              {r.likely_required &&
                (trackedTitles.some((tt) => tt.startsWith(t(`obligations.results.${r.key}`).toLowerCase())) ? (
                  <span className="chip bg-green-50 text-green-800">{t("obligations.alreadyTracked")}</span>
                ) : (
                  canEdit && (
                    <button className="btn-secondary text-xs" onClick={() => onTrack(r.key, r.kind)}>
                      {t("obligations.track")}
                    </button>
                  )
                ))}
            </li>
          ))}
        </ul>
        {q.licensing.notes.map((n) => (
          <p key={n} className="mt-3 rounded-lg bg-violet-50 px-3 py-2 text-xs text-violet-900">
            {t(`obligations.notes.${n}`)}
          </p>
        ))}
        <p className="mt-4 text-xs text-slate-500">{t("obligations.estimateNote")}</p>
      </Card>
    </div>
  );
}

function Applicability({ q, reload, canEdit }: { q: Questionnaires; reload: () => void; canEdit: boolean }) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<Answers>(q.applicability.answers);
  useEffect(() => setAnswers(q.applicability.answers), [q]);
  const result = q.applicability.result;
  const tone = result === "likely_in_scope" ? "border-brand-300 bg-brand-50" : result === "likely_out_of_scope" ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50";
  const visible = q.applicability.questions.filter((k) => k !== "money_transfer_or_exchange" || answers.cbe_supervised === true);
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card>
        <ol className="space-y-4">
          {visible.map((k, i) => (
            <li key={k} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span id={`app-${k}-q`} className="text-sm text-slate-800">
                <span className="me-2 text-slate-500">{fmtNum(i + 1)}.</span>
                {t(`obligations.questions.${k}`)}
              </span>
              <YesNo name={`app-${k}`} value={answers[k]} onChange={(v) => setAnswers({ ...answers, [k]: v })} disabled={!canEdit} />
            </li>
          ))}
        </ol>
        {canEdit && (
          <button
            className="btn-primary mt-4"
            onClick={async () => {
              await api.put("/api/obligations/questionnaires/applicability", { answers });
              reload();
            }}
          >
            {t("obligations.save")}
          </button>
        )}
      </Card>
      <section className={`rounded-2xl border p-5 ${tone}`} aria-live="polite">
        <h2 className="text-base font-semibold">{t(`obligations.applicability.${result}`)}</h2>
        {q.applicability.reason && <p className="mt-2 text-sm text-slate-700">{t(`obligations.reasons.${q.applicability.reason}`)}</p>}
        <p className="mt-4 text-xs text-slate-500">{t("obligations.estimateNote")}</p>
      </section>
    </div>
  );
}

export default function Obligations() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const canEdit = can("obligations.write");
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "tracker";
  const items = useApi<Item[]>("/api/obligations");
  const reminders = useApi<ReminderRow[]>("/api/obligations/reminders");
  const q = useApi<Questionnaires>("/api/obligations/questionnaires");
  const [editing, setEditing] = useState<{ id: number | null; draft: typeof EMPTY } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const years = q.data?.licence_validity_years ?? 3;
  const reloadAll = () => {
    items.reload();
    reminders.reload();
    q.reload();
  };

  const tabs = [
    ["tracker", t("obligations.tabTracker")],
    ["licensing", t("obligations.tabLicensing")],
    ["applicability", t("obligations.tabApplicability")],
  ];

  return (
    <>
      <PageHeader
        title={t("obligations.title")}
        subtitle={t("obligations.subtitle")}
        actions={
          canEdit && tab === "tracker" && (
            <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>
              + {t("obligations.add")}
            </button>
          )
        }
      />
      <div role="tablist" aria-label={t("obligations.title")} className="mb-5 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-slate-200">
        {tabs.map(([k, label]) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium whitespace-nowrap ${tab === k ? "border-brand-600 text-brand-800" : "border-transparent text-slate-600 hover:text-ink"}`}
            onClick={() => setParams({ tab: k }, { replace: true })}
          >
            {label}
          </button>
        ))}
      </div>
      {flash && (
        <p role="status" className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
          {flash}
        </p>
      )}

      {tab === "tracker" && (
        <div className="grid gap-5 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <ErrorBox error={items.error} onRetry={items.reload} />
            {items.loading && !items.data ? (
              <Spinner />
            ) : !items.data?.length ? (
              <EmptyState title={t("obligations.empty")} hint={t("obligations.emptyHint")} />
            ) : (
              <div className="overflow-x-auto">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th>{t("obligations.itemTitle")}</th>
                      <th>{t("obligations.status")}</th>
                      <th>{t("obligations.dates")}</th>
                      <th>{t("obligations.owner")}</th>
                      <th>
                        <span className="sr-only">{t("common.actions")}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.data.map((o) => (
                      <tr key={o.id} className={o.status === "not_needed" ? "opacity-60" : ""}>
                        <td>
                          <div className="font-medium">{o.title}</div>
                          <div className="text-xs text-slate-500">
                            {t(`obligations.kinds.${o.kind}`)}
                            {o.reference && (
                              <span dir="ltr" className="ms-1">
                                • {o.reference}
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          <span className={`chip ${o.effective_status === "expired" ? "bg-red-600 text-white" : o.effective_status === "active" ? "bg-green-50 text-green-800" : "bg-slate-100 text-slate-700"}`}>
                            {t(`obligations.statuses.${o.effective_status}`)}
                          </span>
                        </td>
                        <td className="space-y-1 text-xs">
                          {o.expires_on && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-slate-500">{t("obligations.expiry")}</span> {fmtDate(o.expires_on)}
                              {o.status !== "not_needed" && <DaysChip days={o.days_to_expiry} />}
                              {o.expiry_from_default && <span className="text-[11px] italic text-slate-500">({t("obligations.fromDefault")})</span>}
                            </div>
                          )}
                          {o.review_due && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-slate-500">{t("obligations.review")}</span> {fmtDate(o.review_due)}
                              {o.status !== "not_needed" && <DaysChip days={o.days_to_review} />}
                            </div>
                          )}
                        </td>
                        <td className="text-sm text-slate-700">{o.owner}</td>
                        <td className="text-end">
                          {canEdit && (
                            <button
                              className="btn-ghost text-xs"
                              onClick={() =>
                                setEditing({
                                  id: o.id,
                                  draft: { kind: o.kind, title: o.title, reference: o.reference, status: o.status, issued_on: o.issued_on ?? "", expires_on: o.expiry_from_default ? "" : (o.expires_on ?? ""), review_due: o.review_due ?? "", owner: o.owner, notes: o.notes },
                                })
                              }
                            >
                              {t("common.edit")}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title={t("obligations.reminders")}>
            {!reminders.data?.length ? (
              <EmptyState title={t("obligations.remindersEmpty")} />
            ) : (
              <ul className="space-y-3">
                {reminders.data.map((r) => (
                  <li key={r.id} className={`rounded-xl border p-3 ${r.days_left < 0 ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50/60"}`}>
                    <div className="text-sm font-medium">{r.obligation.title}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-700">
                      {r.kind === "expiry" ? t("obligations.expiry") : t("obligations.review")} {fmtDate(r.due)} <DaysChip days={r.days_left} />
                    </div>
                    {canEdit && (
                      <button
                        className="mt-2 text-xs font-medium text-brand-700 hover:underline"
                        onClick={async () => {
                          await api.post(`/api/obligations/reminders/${r.id}/dismiss`);
                          reminders.reload();
                        }}
                      >
                        {t("obligations.dismiss")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === "licensing" && (q.data ? <Licensing q={q.data} reload={q.reload} canEdit={canEdit} trackedTitles={(items.data ?? []).filter((o) => o.status !== "not_needed").map((o) => o.title.toLowerCase())} onTrack={(key, kind) => {
        setEditing({ id: null, draft: { ...EMPTY, kind, title: t(`obligations.results.${key}`) } });
        setFlash(null);
      }} /> : <Spinner />)}
      {tab === "applicability" && (q.data ? <Applicability q={q.data} reload={q.reload} canEdit={canEdit} /> : <Spinner />)}

      {editing && (
        <ItemForm
          initial={editing.draft}
          id={editing.id}
          years={years}
          onClose={() => setEditing(null)}
          onSaved={() => {
            reloadAll();
            if (!editing.id) setFlash(t("obligations.tracked"));
          }}
        />
      )}
    </>
  );
}
