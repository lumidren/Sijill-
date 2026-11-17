import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner, StatusChip } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtDateTime, fmtNum, pick } from "../i18n";
import type { Bi, Posture } from "../types";

type ReqState = "open" | "submitted" | "closed" | "revoked" | "expired";
type ItemState = "open" | "answered" | "accepted" | "returned";

interface RFile { id: number; filename: string; size: number; uploaded_at: string; sha256?: string; evidence_file_id?: number | null }
interface RItem {
  id: number; requirement_id: string; label: string; title: Bi; question: Bi; ask: string; response: string;
  status: ItemState; responded_at: string | null; review_note: string; files: RFile[];
}
export interface EvidenceRequestRow {
  id: number; title: string; recipient: string; recipient_contact: string; message: string; status: ReqState;
  expires_at: string; created_at: string; first_opened_at: string | null; submitted_at: string | null;
  total: number; counts: Record<ItemState, number>; files: number; items?: RItem[]; token?: string;
}

const STATE_STYLE: Record<string, string> = {
  open: "bg-sky-50 text-sky-800 ring-1 ring-sky-600/20",
  submitted: "bg-violet-50 text-violet-800 ring-1 ring-violet-600/20",
  closed: "bg-slate-100 text-slate-600",
  revoked: "bg-slate-100 text-slate-600",
  expired: "bg-amber-50 text-amber-900",
  answered: "bg-violet-50 text-violet-800 ring-1 ring-violet-600/20",
  accepted: "bg-green-50 text-green-800 ring-1 ring-green-600/20",
  returned: "bg-amber-50 text-amber-900",
};

export const linkFor = (token: string) => `${window.location.origin}/r/${token}`;

/** Shows a freshly made link once, with a copy button. */
function LinkOnce({ token, onDone }: { token: string; onDone: () => void }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const url = linkFor(token);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true" aria-labelledby="link-title">
      <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-xl">
        <h2 id="link-title" className="text-lg font-semibold">
          {t("er.linkTitle")}
        </h2>
        <p className="mt-2 text-sm text-slate-600">{t("er.linkOnce")}</p>
        <label htmlFor="er-link" className="label mt-4">
          {t("er.link")}
        </label>
        <input id="er-link" className="input font-mono text-xs" dir="ltr" readOnly value={url} onFocus={(e) => e.target.select()} />
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            className="btn-primary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(url);
                setCopied(true);
              } catch {
                setCopied(false);
              }
            }}
          >
            {copied ? t("er.copied") : t("er.copy")}
          </button>
          <button className="btn-secondary" onClick={onDone}>
            {t("common.close")}
          </button>
        </div>
        <p className="mt-4 text-xs text-slate-500">{t("er.sendYourself")}</p>
      </div>
    </div>
  );
}

function NewRequest({ preselect, onCreated, onClose }: { preselect: string[]; onCreated: (r: EvidenceRequestRow) => void; onClose: () => void }) {
  const { t } = useTranslation();
  const posture = useApi<Posture>("/api/posture");
  const [f, setF] = useState({ title: "", recipient: "", recipient_contact: "", message: "", expires_days: "14" });
  const [picked, setPicked] = useState<Set<string>>(new Set(preselect));
  const [asks, setAsks] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const byArea = useMemo(() => {
    const out = new Map<string, Posture["requirements"]>();
    for (const r of posture.data?.requirements ?? []) out.set(r.area_id, [...(out.get(r.area_id) ?? []), r]);
    return out;
  }, [posture.data]);
  const toggle = (id: string) => {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  };
  const pickGaps = () => setPicked(new Set((posture.data?.requirements ?? []).filter((r) => ["partial", "non_compliant", "not_assessed"].includes(r.status)).map((r) => r.id)));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const ids = [...picked];
      const r = await api.post<EvidenceRequestRow>("/api/evidence-requests", {
        ...f, expires_days: Number(f.expires_days) || 14, requirement_ids: ids,
        asks: Object.fromEntries(Object.entries(asks).filter(([k, v]) => picked.has(k) && v.trim())),
      });
      onCreated(r);
    } catch (ex) {
      setErr(ex instanceof ApiError && ex.status === 422 ? t("errors.validation_error") : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" aria-labelledby="er-new-title" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form onSubmit={submit} className="flex h-full w-full max-w-3xl flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 id="er-new-title" className="text-lg font-semibold">
            {t("er.new")}
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t("common.close")}
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {err && (
            <p role="alert" className="text-sm text-red-700">
              {err}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label" htmlFor="er-title">{t("er.title_")}</label>
              <input id="er-title" className="input" required maxLength={200} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="er-recipient">{t("er.recipient")}</label>
              <input id="er-recipient" className="input" required maxLength={128} value={f.recipient} onChange={(e) => setF({ ...f, recipient: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="er-contact">{t("er.contact")}</label>
              <input id="er-contact" className="input" maxLength={255} value={f.recipient_contact} onChange={(e) => setF({ ...f, recipient_contact: e.target.value })} aria-describedby="er-contact-hint" />
              <p id="er-contact-hint" className="mt-1 text-xs text-slate-500">{t("er.contactHint")}</p>
            </div>
            <div className="sm:col-span-2">
              <label className="label" htmlFor="er-message">{t("er.message")}</label>
              <textarea id="er-message" className="input min-h-[70px]" maxLength={4000} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="er-days">{t("er.expiresDays")}</label>
              <input id="er-days" type="number" min={1} max={60} className="input" value={f.expires_days} onChange={(e) => setF({ ...f, expires_days: e.target.value })} />
            </div>
          </div>
          <fieldset>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <legend className="text-sm font-medium">
                {t("er.pick")} ({fmtNum(picked.size)})
              </legend>
              <button type="button" className="btn-ghost text-xs" onClick={pickGaps}>
                {t("er.pickGaps")}
              </button>
            </div>
            {posture.loading && !posture.data ? (
              <Spinner />
            ) : (
              <div className="mt-2 space-y-3">
                {(posture.data?.areas ?? []).map((a) => (
                  <div key={a.id} className="rounded-xl border border-slate-200 p-3">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{pick(a.title)}</div>
                    <ul className="space-y-2">
                      {(byArea.get(a.id) ?? []).map((r) => (
                        <li key={r.id}>
                          <label className="flex items-start gap-2 text-sm">
                            <input type="checkbox" className="mt-1" checked={picked.has(r.id)} onChange={() => toggle(r.id)} />
                            <span className="flex-1">
                              <span className="font-mono text-xs text-slate-500" dir="ltr">{r.label}</span> {pick(r.title)}
                            </span>
                            <StatusChip status={r.status} />
                          </label>
                          {picked.has(r.id) && (
                            <input
                              className="input mt-1 text-xs"
                              placeholder={t("er.askPlaceholder")}
                              aria-label={`${t("er.ask")}: ${r.label}`}
                              maxLength={2000}
                              value={asks[r.id] ?? ""}
                              onChange={(e) => setAsks({ ...asks, [r.id]: e.target.value })}
                            />
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </fieldset>
        </div>
        <div className="flex gap-2 border-t border-slate-200 px-6 py-4">
          <button className="btn-primary" disabled={busy || picked.size === 0}>
            {t("er.create")}
          </button>
          <button type="button" className="btn-secondary" onClick={onClose}>
            {t("common.cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function StateChip({ state }: { state: string }) {
  const { t } = useTranslation();
  return <span className={`chip ${STATE_STYLE[state] ?? "bg-slate-100"}`}>{t(`er.states.${state}`)}</span>;
}

export default function EvidenceRequests() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const { data, error, loading, reload } = useApi<EvidenceRequestRow[]>("/api/evidence-requests");
  const preselect = params.get("new");
  const [creating, setCreating] = useState(preselect !== null);
  const [token, setToken] = useState<string | null>(null);

  return (
    <>
      <PageHeader
        title={t("er.title")}
        subtitle={t("er.subtitle")}
        actions={can("evidence_requests.manage") && <button className="btn-primary" onClick={() => setCreating(true)}>+ {t("er.new")}</button>}
      />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : !data?.length ? (
        <EmptyState title={t("er.empty")} hint={t("er.emptyHint")} />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>{t("er.title_")}</th>
                  <th>{t("er.recipient")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("er.progress")}</th>
                  <th>{t("er.expires")}</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/evidence-requests/${r.id}`} className="font-medium text-brand-700 hover:underline">
                        {r.title}
                      </Link>
                      {r.counts.answered > 0 && <div className="text-xs font-medium text-violet-700">{t("er.toReview", { count: r.counts.answered })}</div>}
                    </td>
                    <td className="text-sm">{r.recipient}</td>
                    <td>
                      <StateChip state={r.status} />
                    </td>
                    <td className="text-sm text-slate-600">
                      {t("er.progressOf", { done: fmtNum(r.counts.answered + r.counts.accepted), total: fmtNum(r.total) })} • {t("er.accepted", { count: r.counts.accepted })}
                    </td>
                    <td className="text-sm text-slate-600">{fmtDate(r.expires_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {creating && (
        <NewRequest
          preselect={preselect ? [preselect] : []}
          onClose={() => {
            setCreating(false);
            if (preselect) setParams({}, { replace: true });
          }}
          onCreated={(r) => {
            setCreating(false);
            setToken(r.token ?? null);
            reload();
          }}
        />
      )}
      {token && <LinkOnce token={token} onDone={() => setToken(null)} />}
    </>
  );
}

export function EvidenceRequestDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<EvidenceRequestRow>(`/api/evidence-requests/${id}`);
  const [token, setToken] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const manage = can("evidence_requests.manage");
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const act = async (path: string, body: object = {}) => {
    const r = await api.post<EvidenceRequestRow>(`/api/evidence-requests/${data.id}/${path}`, body);
    if (r.token) setToken(r.token);
    reload();
  };
  const live = ["open", "submitted", "expired"].includes(data.status);

  return (
    <>
      <PageHeader
        title={data.title}
        subtitle={`${t("er.recipient")}: ${data.recipient}${data.recipient_contact ? ` • ${data.recipient_contact}` : ""}`}
        actions={
          manage && (
            <div className="flex flex-wrap gap-2">
              {data.status !== "closed" && (
                <button className="btn-secondary" onClick={() => act("link", {})}>
                  {t("er.newLink")}
                </button>
              )}
              {live && data.status !== "expired" && (
                <button className="btn-ghost" onClick={() => act("revoke")}>
                  {t("er.revoke")}
                </button>
              )}
              {data.status !== "closed" && (
                <button className="btn-ghost" onClick={() => act("close")}>
                  {t("er.close")}
                </button>
              )}
            </div>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
        <StateChip state={data.status} />
        <span>{t("er.expiresOn", { when: fmtDate(data.expires_at) })}</span>
        <span>{data.first_opened_at ? t("er.openedOn", { when: fmtDateTime(data.first_opened_at) }) : t("er.notOpened")}</span>
        {data.submitted_at && <span>{t("er.submittedOn", { when: fmtDateTime(data.submitted_at) })}</span>}
        <Link to="/evidence-requests" className="text-brand-700 hover:underline">
          {t("er.back")}
        </Link>
      </div>
      <p className="mb-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{t("er.reviewHint")}</p>
      <div className="space-y-4">
        {data.items?.map((i) => (
          <Card key={i.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <Link to={`/requirements/${i.requirement_id}`} className="font-medium text-brand-700 hover:underline">
                  <span dir="ltr">{i.label}</span> {pick(i.title)}
                </Link>
                {i.ask && <p className="mt-1 text-xs text-slate-500">{t("er.ask")}: {i.ask}</p>}
              </div>
              <StateChip state={i.status} />
            </div>
            {i.response ? <p className="mt-3 whitespace-pre-line rounded-lg border border-slate-200 p-3 text-sm">{i.response}</p> : <p className="mt-3 text-sm text-slate-400">{t("er.noAnswer")}</p>}
            {i.files.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {i.files.map((f) => (
                  <li key={f.id} className="flex flex-wrap items-center gap-2">
                    <a className="text-brand-700 hover:underline" href={`/api/evidence-requests/${data.id}/files/${f.id}/download`}>
                      {f.filename}
                    </a>
                    <span className="text-xs text-slate-500">{fmtNum(Math.ceil(f.size / 1024))} KB</span>
                    <code className="text-[11px] text-slate-400" dir="ltr" title="SHA-256">{f.sha256?.slice(0, 12)}…</code>
                    {f.evidence_file_id && <span className="chip bg-green-50 text-green-800">{t("er.inEvidence")}</span>}
                  </li>
                ))}
              </ul>
            )}
            {i.review_note && <p className="mt-2 text-xs text-amber-900">{t("er.yourNote")}: {i.review_note}</p>}
            {manage && i.status !== "accepted" && (i.status !== "open" || i.response || i.files.length > 0) && (
              <div className="mt-3 flex flex-wrap items-end gap-2">
                <div className="min-w-[16rem] flex-1">
                  <label className="label" htmlFor={`note-${i.id}`}>{t("er.noteToRecipient")}</label>
                  <input id={`note-${i.id}`} className="input" maxLength={2000} value={notes[i.id] ?? ""} onChange={(e) => setNotes({ ...notes, [i.id]: e.target.value })} />
                </div>
                {i.status === "answered" && (
                  <button className="btn-primary" onClick={() => act(`items/${i.id}/review`, { decision: "accept", note: notes[i.id] ?? "" })}>
                    {t("er.accept")}
                  </button>
                )}
                <button className="btn-secondary" onClick={() => act(`items/${i.id}/review`, { decision: "return", note: notes[i.id] ?? "" })}>
                  {t("er.return")}
                </button>
              </div>
            )}
          </Card>
        ))}
      </div>
      {token && <LinkOnce token={token} onDone={() => setToken(null)} />}
    </>
  );
}
