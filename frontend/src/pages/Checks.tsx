import { useRef, useState, type ChangeEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Card, CheckChip, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDateTime, fmtNum, pick } from "../i18n";
import type { Bi, Regression, Run } from "../types";

type Tab = "runs" | "regressions" | "mapping" | "collectors";

interface MappingRow {
  requirement: { id: string; label: string; title: Bi; area_id: string };
  checks: { check_id: string; provider: string; title: string; severity: string; status: "PASS" | "FAIL" | null; resources: number; failing: string[] }[];
}

interface Collectors {
  adapters: { adapter: string; available: boolean; detail: string }[];
  interval_hours: number;
  active_here?: boolean;
  next_run: string | null;
  last: { at: string | null; results: { adapter: string; status: string; detail: string; runs: number }[] };
  inbox: string;
}

function ImportPanel({ onDone }: { onDone: () => void }) {
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
    try {
      const r = await api.post<{ total: number; failed: number }>("/api/checks/import", fd);
      setMsg({ ok: true, text: t("checks.imported", { total: fmtNum(r.total), failed: fmtNum(r.failed) }) });
      onDone();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "error";
      setMsg({ ok: false, text: t(`checks.errors.${code}`, { defaultValue: t("common.error") }) });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <Card title={t("checks.import")}>
      <p className="mb-4 text-sm text-slate-600">{t("checks.importHint")}</p>
      <label className={`btn-primary cursor-pointer ${busy ? "pointer-events-none opacity-60" : ""}`}>
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M12 16V4m0 0L7 9m5-5 5 5M4 20h16" />
        </svg>
        {busy ? t("checks.importing") : t("checks.chooseFile")}
        <input ref={input} type="file" accept=".json,application/json" className="sr-only" onChange={onFile} disabled={busy} />
      </label>
      {msg && (
        <p role={msg.ok ? "status" : "alert"} className={`mt-3 text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>
          {msg.text}
        </p>
      )}
      <p className="mt-4 text-xs text-slate-500">{t("checks.credentialsNote")}</p>
    </Card>
  );
}

function RunsTable({ runs }: { runs: Run[] }) {
  const { t } = useTranslation();
  if (!runs.length) return <EmptyState title={t("checks.runsEmpty")} hint={t("dashboard.noRunsHint")} />;
  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <thead>
          <tr>
            <th>{t("checks.when")}</th>
            <th>{t("checks.target")}</th>
            <th>{t("checks.source")}</th>
            <th>{t("checks.results")}</th>
            <th>{t("checks.tabRegressions")}</th>
            <th>{t("checks.sha")}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="hover:bg-slate-50">
              <td className="whitespace-nowrap">
                <Link to={`/checks/runs/${r.id}`} className="font-medium text-brand-800 hover:underline">
                  {fmtDateTime(r.started_at)}
                </Link>
              </td>
              <td>
                <div dir="ltr" className="text-start">
                  {r.target}
                </div>
                <div className="text-xs text-slate-500">{t(`checks.providers.${r.provider}`, { defaultValue: r.provider })}</div>
              </td>
              <td className="text-slate-600">{t(`checks.sources.${r.source}`, { defaultValue: r.source })}</td>
              <td className="whitespace-nowrap">
                <span className="text-green-700">{fmtNum(r.passed)}</span> / <span className="text-red-700">{fmtNum(r.failed)}</span>
                {r.unmapped > 0 && <span className="ms-2 text-xs text-slate-500" title={t("checks.unmappedHint")}>+{fmtNum(r.unmapped)}</span>}
              </td>
              <td className="whitespace-nowrap">
                {r.regressions ? <span className="chip bg-red-600 text-white">{t("checks.comparedRegressions", { count: fmtNum(r.regressions) })}</span> : null}{" "}
                {r.fixed ? <span className="chip bg-green-100 text-green-800">{t("checks.comparedFixed", { count: fmtNum(r.fixed) })}</span> : null}
                {!r.regressions && !r.fixed && <span className="text-xs text-slate-500">—</span>}
              </td>
              <td className="font-mono text-[11px] text-slate-500" dir="ltr" title={r.file_sha256}>
                {r.file_sha256.slice(0, 12)}…
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RegressionList() {
  const { t } = useTranslation();
  const { data, error, loading } = useApi<Regression[]>("/api/checks/regressions");
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.length) return <EmptyState title={t("dashboard.regressionsEmpty")} />;
  return (
    <ul className="space-y-3">
      {data.map((r) => (
        <li key={`${r.run_id}-${r.check_id}-${r.resource}`} className="rounded-xl border border-red-200 bg-red-50/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-red-900">{r.title || r.check_id}</span>
            <CheckChip status="FAIL" />
          </div>
          <p className="mt-1 text-sm text-slate-700">{r.message}</p>
          <p className="mt-2 text-xs text-slate-500" dir="ltr">
            {r.check_id} · {r.resource}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            {t("dashboard.regressionHint", { target: r.target })}{" "}
            <Link to={`/checks/runs/${r.run_id}`} className="text-brand-700 hover:underline">
              {t("checks.runDetail", { id: r.run_id })}
            </Link>
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {r.requirements.map((id) => (
              <Link key={id} to={`/requirements/${id}`} className="chip bg-white text-slate-700 ring-1 ring-slate-300 hover:ring-brand-400">
                {id.toUpperCase().replace("-", ".")}
              </Link>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

function MappingTable() {
  const { t } = useTranslation();
  const { data, error, loading } = useApi<MappingRow[]>("/api/checks/mapping");
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{t("checks.mappingSubtitle")}</p>
      {data?.map((row) => (
        <details key={row.requirement.id} className="group rounded-xl border border-slate-200 bg-white">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
            <span className="text-sm font-medium">
              <span className="me-2 text-xs text-slate-500">{row.requirement.label}</span>
              {pick(row.requirement.title)}
            </span>
            <span className="flex gap-2 text-xs">
              <span className="text-green-700">{fmtNum(row.checks.filter((c) => c.status === "PASS").length)}</span>
              <span className="text-red-700">{fmtNum(row.checks.filter((c) => c.status === "FAIL").length)}</span>
              <span className="text-slate-500">/ {fmtNum(row.checks.length)}</span>
            </span>
          </summary>
          <ul className="divide-y divide-slate-100 border-t border-slate-100">
            {row.checks.map((c) => (
              <li key={c.check_id} className="flex items-start justify-between gap-3 px-4 py-2">
                <div className="min-w-0">
                  <div className="text-sm">{c.title}</div>
                  <code className="break-all text-[11px] text-slate-500" dir="ltr">
                    {c.check_id}
                  </code>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs text-slate-500">{t(`checks.providers.${c.provider}`, { defaultValue: c.provider })}</span>
                  {c.status ? <CheckChip status={c.status} /> : <span className="text-xs text-slate-500">{t("requirements.noResult")}</span>}
                </div>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

function CollectorsPanel() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<Collectors>("/api/checks/collectors");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title={t("checks.schedule")}>
        <p className="text-sm text-slate-700">{t("checks.scheduleEvery", { hours: fmtNum(data.interval_hours) })}</p>
        <p className="mt-1 text-sm text-slate-600">
          {t("checks.nextRun")}: {fmtDateTime(data.next_run)}
        </p>
        <p className="mt-1 text-sm text-slate-600">
          {t("checks.lastCollection")}: {fmtDateTime(data.last.at)}
        </p>
        <ul className="mt-4 space-y-3">
          {data.adapters.map((a) => (
            <li key={a.adapter} className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 p-3">
              <div>
                <div className="text-sm font-medium">{t(`checks.adapters.${a.adapter}`, { defaultValue: a.adapter })}</div>
                <div className="text-xs text-slate-500" dir={a.adapter === "inbox" ? "ltr" : undefined}>
                  {a.adapter === "inbox" ? a.detail : t(`checks.reasons.${a.detail}`, { defaultValue: a.detail })}
                </div>
              </div>
              <span className={`chip ${a.available ? "bg-green-50 text-green-800 ring-1 ring-green-600/20" : "bg-slate-100 text-slate-600"}`}>
                {a.available ? t("checks.adapterReady") : t("checks.adapterOff")}
              </span>
            </li>
          ))}
        </ul>
        {data.active_here === false && (
          <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{t("orgs.collectorsElsewhere")}</p>
        )}
        {can("checks.write") && data.active_here !== false && (
          <button
            className="btn-secondary mt-4"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setDone(false);
              try {
                await api.post("/api/checks/collect");
                setDone(true);
                reload();
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? t("checks.collecting") : t("checks.runNow")}
          </button>
        )}
        {done && (
          <p role="status" className="mt-2 text-sm text-green-700">
            {t("checks.collected")}
          </p>
        )}
      </Card>
      <Card title={t("checks.providers.linux")}>
        <p className="text-sm text-slate-700">{t("checks.linuxHow")}</p>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100" dir="ltr">
          sudo python3 pdpl_linux_collector.py -o $(hostname).ocsf.json
        </pre>
        <p className="mt-4 text-sm text-slate-600">{t("checks.inboxHint")}</p>
        <code className="mt-1 block break-all rounded bg-slate-100 px-2 py-1 text-xs" dir="ltr">
          {data.inbox}
        </code>
      </Card>
    </div>
  );
}

export default function Checks() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "runs";
  const runs = useApi<Run[]>("/api/checks/runs?limit=200");
  const tabs: Tab[] = ["runs", "regressions", "mapping", "collectors"];
  const label: Record<Tab, string> = { runs: t("checks.tabRuns"), regressions: t("checks.tabRegressions"), mapping: t("checks.tabMapping"), collectors: t("checks.tabCollectors") };

  return (
    <>
      <PageHeader title={t("checks.title")} subtitle={t("checks.subtitle")} />
      <div role="tablist" aria-label={t("checks.title")} className="mb-5 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-slate-200">
        {tabs.map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium whitespace-nowrap ${tab === k ? "border-brand-600 text-brand-800" : "border-transparent text-slate-600 hover:text-ink"}`}
            onClick={() => setParams({ tab: k }, { replace: true })}
          >
            {label[k]}
          </button>
        ))}
      </div>
      {tab === "runs" && (
        <div className="grid gap-5 xl:grid-cols-3">
          <Card title={t("checks.runs")} className="xl:col-span-2">
            <ErrorBox error={runs.error} onRetry={runs.reload} />
            {runs.loading && !runs.data ? <Spinner /> : <RunsTable runs={runs.data ?? []} />}
          </Card>
          {can("checks.write") ? <ImportPanel onDone={runs.reload} /> : <Card title={t("checks.import")}>{<p className="text-sm text-slate-600">{t("common.readOnly")}</p>}</Card>}
        </div>
      )}
      {tab === "regressions" && <RegressionList />}
      {tab === "mapping" && <MappingTable />}
      {tab === "collectors" && <CollectorsPanel />}
    </>
  );
}
