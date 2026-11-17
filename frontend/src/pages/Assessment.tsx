import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { MiniBar } from "../components/charts";
import { BasisChip, Card, ErrorBox, PageHeader, Spinner, StaleChip, StatusChip, Unverified, type ReqStatus } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDateTime, fmtNum, pick } from "../i18n";
import type { Bi } from "../types";

const OPTIONS: ReqStatus[] = ["compliant", "partial", "non_compliant", "not_applicable", "not_assessed"];

interface Result {
  status: ReqStatus;
  basis: "automated" | "attested" | "not_assessed";
  capped: boolean;
  stale: boolean;
  reason: string;
  failing_checks: number;
  passing_checks: number;
  automated_status: ReqStatus | null;
}

interface Req {
  id: string;
  label: string;
  title: Bi;
  statement: Bi;
  question: Bi;
  guidance: Bi;
  technical: boolean;
  verified: boolean;
  weight: number;
  answer: { status: ReqStatus; note: string; updated_at: string; updated_by: string | null } | null;
  evidence_count: number;
  result: Result;
}

interface Area {
  id: string;
  label: string;
  title: Bi;
  overview: Bi;
  score: number | null;
  answered: number;
  requirement_count: number;
  requirements: Req[];
}

interface Overview {
  answered: number;
  total: number;
  areas: Area[];
}

function EvidenceUpload({ reqId, count, onDone }: { reqId: string; count: number; onDone: () => void }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("requirement_id", reqId);
    fd.append("description", "");
    try {
      await api.post("/api/evidence", fd);
      setMsg({ ok: true, text: t("assessment.attached", { name: file.name }) });
      onDone();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "error";
      setMsg({ ok: false, text: t(`assessment.errors.${code}`, { defaultValue: t("common.error") }) });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <label className={`btn-secondary cursor-pointer text-xs ${busy ? "pointer-events-none opacity-60" : ""}`}>
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="m21 12-8.5 8.5a5 5 0 0 1-7-7L14 5a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 8" />
          </svg>
          {busy ? t("assessment.attaching") : t("assessment.attach")}
          <input ref={input} type="file" className="sr-only" accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.csv,.json" onChange={onFile} aria-describedby={`ev-hint-${reqId}`} />
        </label>
        {count > 0 && (
          <Link to={`/requirements/${reqId}`} className="text-xs text-brand-700 hover:underline">
            {t("assessment.evidence")}: {fmtNum(count)}
          </Link>
        )}
      </div>
      <p id={`ev-hint-${reqId}`} className="mt-1 text-[11px] text-slate-500">
        {t("assessment.evidenceHint")}
      </p>
      {msg && (
        <p role={msg.ok ? "status" : "alert"} className={`mt-1 text-xs ${msg.ok ? "text-green-700" : "text-red-700"}`}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

function Question({ req, canAnswer, canUpload, onSaved }: { req: Req; canAnswer: boolean; canUpload: boolean; onSaved: () => void }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ReqStatus>(req.answer?.status ?? "not_assessed");
  const [note, setNote] = useState(req.answer?.note ?? "");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [result, setResult] = useState<Result>(req.result);
  const dirty = status !== (req.answer?.status ?? "not_assessed") || note !== (req.answer?.note ?? "");
  const group = `ans-${req.id}`;

  async function save() {
    setSaving(true);
    setMsg(null);
    try {
      const r = await api.put<{ result: Result }>(`/api/assessment/answers/${req.id}`, { status, note });
      setResult(r.result);
      setMsg({ ok: true, text: t("assessment.saved", { status: t(`status.${r.result.status}`) }) });
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError && err.status === 403 ? t("common.forbidden") : t("common.error") });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section id={req.id} className="card scroll-mt-20 p-5" aria-labelledby={`${req.id}-q`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-slate-500">
            {req.label} · {pick(req.title)} {!req.verified && <Unverified />}
          </p>
          <h3 id={`${req.id}-q`} className="mt-1 text-[15px] font-semibold text-ink">
            {pick(req.question)}
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" aria-label={t("assessment.currentStatus")}>
          {result.stale && <StaleChip />}
          <BasisChip basis={result.basis} />
          <StatusChip status={result.status} />
        </div>
      </div>

      <details className="mt-2 text-sm text-slate-600">
        <summary className="cursor-pointer text-xs font-medium text-brand-700">{t("assessment.statement")}</summary>
        <p className="mt-2">{pick(req.statement)}</p>
        {pick(req.guidance) && (
          <p className="mt-2 text-slate-500">
            <span className="font-medium">{t("assessment.showGuidance")}: </span>
            {pick(req.guidance)}
          </p>
        )}
      </details>

      {result.automated_status && (
        <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${result.failing_checks ? "bg-amber-50 text-amber-900" : "bg-sky-50 text-sky-900"}`}>
          {t("assessment.autoNote", { passing: fmtNum(result.passing_checks), failing: fmtNum(result.failing_checks) })}{" "}
          {result.failing_checks > 0 && t("assessment.capWarning", { count: fmtNum(result.failing_checks) })}{" "}
          <Link to={`/requirements/${req.id}`} className="font-medium underline">
            {t("common.details")}
          </Link>
        </div>
      )}

      <fieldset className="mt-4" disabled={!canAnswer}>
        <legend className="mb-2 text-sm font-medium text-slate-700">{t("assessment.choose")}</legend>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {OPTIONS.map((o) => (
            <label
              key={o}
              className={`flex cursor-pointer flex-col rounded-xl border p-3 text-sm transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-400 ${
                status === o ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-slate-300"
              } ${!canAnswer ? "cursor-not-allowed opacity-70" : ""}`}
            >
              <span className="flex items-center gap-2 font-medium">
                <input type="radio" name={group} value={o} checked={status === o} onChange={() => setStatus(o)} className="accent-brand-700" />
                {t(`assessment.options.${o}`)}
              </span>
              <span className="mt-1 text-xs text-slate-500">{t(`assessment.optionHints.${o}`)}</span>
            </label>
          ))}
        </div>
        <label className="label mt-4" htmlFor={`${req.id}-note`}>
          {t("assessment.note")}
        </label>
        <textarea
          id={`${req.id}-note`}
          className="input min-h-[72px]"
          maxLength={4000}
          placeholder={t("assessment.notePlaceholder")}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </fieldset>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        {canUpload ? <EvidenceUpload reqId={req.id} count={req.evidence_count} onDone={onSaved} /> : <span />}
        <div className="flex flex-col items-end gap-1">
          {canAnswer && (
            <button className="btn-primary" disabled={!dirty || saving} onClick={save}>
              {saving ? t("common.saving") : t("assessment.save")}
            </button>
          )}
          {req.answer?.updated_by && <span className="text-[11px] text-slate-500">{t("assessment.lastUpdated", { who: req.answer.updated_by, when: fmtDateTime(req.answer.updated_at) })}</span>}
        </div>
      </div>
      {msg && (
        <p role={msg.ok ? "status" : "alert"} className={`mt-2 text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>
          {msg.text}
        </p>
      )}
    </section>
  );
}

export default function Assessment() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<Overview>("/api/assessment");
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const areaId = params.get("area") || data?.areas[0]?.id || "a01";

  useEffect(() => {
    if (!data || !location.hash) return;
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [data, location.hash]);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const idx = Math.max(0, data.areas.findIndex((a) => a.id === areaId));
  const area = data.areas[idx];
  const canAnswer = can("assessment.write");
  const canUpload = can("evidence.upload");
  const go = (i: number) => {
    setParams({ area: data.areas[i].id });
    window.scrollTo({ top: 0 });
  };

  return (
    <>
      <PageHeader title={t("assessment.title")} subtitle={t("assessment.subtitle")} />
      <div className="mb-5 flex items-center gap-4">
        <div className="flex-1">
          <MiniBar value={data.answered / data.total} />
        </div>
        <span className="text-sm text-slate-600">{t("assessment.progress", { answered: fmtNum(data.answered), total: fmtNum(data.total) })}</span>
      </div>
      {!canAnswer && <p className="mb-4 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">{t("assessment.readOnlyNote")}</p>}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <nav aria-label={t("requirements.filterArea")} className="lg:sticky lg:top-20 lg:self-start">
          <ol className="space-y-1">
            {data.areas.map((a, i) => (
              <li key={a.id}>
                <button
                  onClick={() => go(i)}
                  aria-current={a.id === area.id ? "step" : undefined}
                  className={`w-full rounded-lg px-3 py-2 text-start text-sm transition ${a.id === area.id ? "bg-brand-700 text-white" : "hover:bg-white"}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      <span className={`me-1.5 text-xs ${a.id === area.id ? "text-brand-100" : "text-slate-500"}`}>{a.label}</span>
                      {pick(a.title)}
                    </span>
                    <span className={`shrink-0 text-xs tabular-nums ${a.id === area.id ? "text-brand-100" : "text-slate-500"}`}>
                      {fmtNum(a.answered)}/{fmtNum(a.requirement_count)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <div className="min-w-0 space-y-4">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-medium text-slate-500">{area.label}</p>
                <h2 className="text-lg font-semibold">{pick(area.title)}</h2>
                <p className="text-sm text-slate-600">{pick(area.overview)}</p>
              </div>
              <div className="w-44 text-sm">
                <div className="mb-1 flex justify-between text-xs text-slate-500">
                  <span>{t("assessment.areaProgress", { answered: fmtNum(area.answered), total: fmtNum(area.requirement_count) })}</span>
                  <span className="font-semibold text-ink">{area.score == null ? "—" : fmtNum(Math.round(area.score * 100))}</span>
                </div>
                <MiniBar value={area.score} />
              </div>
            </div>
          </Card>
          {area.requirements.map((r) => (
            <Question key={r.id} req={r} canAnswer={canAnswer} canUpload={canUpload} onSaved={reload} />
          ))}
          <div className="flex justify-between">
            <button className="btn-secondary" disabled={idx === 0} onClick={() => go(idx - 1)}>
              <span aria-hidden className="inline-block rtl:rotate-180">←</span> {t("assessment.prev")}
            </button>
            <button className="btn-primary" disabled={idx === data.areas.length - 1} onClick={() => go(idx + 1)}>
              {t("assessment.next")} <span aria-hidden className="inline-block rtl:rotate-180">→</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
