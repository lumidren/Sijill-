import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CheckChip, ErrorBox, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDateTime, fmtNum } from "../i18n";
import type { DiffItem, RunDetail as Detail } from "../types";

function DiffList({ title, items, tone }: { title: string; items: DiffItem[]; tone: "red" | "green" | "amber" }) {
  if (!items.length) return null;
  const cls = { red: "border-red-200 bg-red-50/60", green: "border-green-200 bg-green-50/60", amber: "border-amber-200 bg-amber-50/60" }[tone];
  return (
    <div className={`rounded-xl border p-4 ${cls}`}>
      <h3 className="mb-2 text-sm font-semibold">
        {title} ({fmtNum(items.length)})
      </h3>
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={`${i.check_id}-${i.resource}`} className="text-sm">
            <div>{i.title || i.check_id}</div>
            <div className="text-xs text-slate-600" dir="ltr">
              {i.resource}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {i.requirements.map((id) => (
                <Link key={id} to={`/requirements/${id}`} className="chip bg-white text-slate-700 ring-1 ring-slate-300">
                  {id.toUpperCase().replace("-", ".")}
                </Link>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function RunDetail() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi<Detail>(`/api/checks/runs/${id}`);
  const [failedOnly, setFailedOnly] = useState(true);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const d = data.diff;
  const results = failedOnly ? data.results.filter((r) => r.status === "FAIL") : data.results;
  const noChange = d.previous_run_id && !d.regressions.length && !d.fixed.length && !d.new_failures.length;

  return (
    <>
      <Link to="/checks" className="mb-4 inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
        <span aria-hidden className="rtl:rotate-180">
          ←
        </span>
        {t("checks.runs")}
      </Link>
      <h1 className="page-title">{t("checks.runDetail", { id: data.id })}</h1>
      <p className="mt-1 text-sm text-slate-600">
        <span dir="ltr">{data.target}</span> · {t(`checks.providers.${data.provider}`, { defaultValue: data.provider })} · {t(`checks.sources.${data.source}`, { defaultValue: data.source })} · {fmtDateTime(data.started_at)}
      </p>
      <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          [t("checks.results"), data.total],
          [t("checks.passed"), data.passed],
          [t("checks.failed"), data.failed],
          [t("checks.unmapped"), data.unmapped],
        ].map(([k, v]) => (
          <div key={String(k)} className="card p-4">
            <dt className="text-xs text-slate-500">{k}</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{fmtNum(Number(v))}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 truncate font-mono text-[11px] text-slate-500" dir="ltr">
        {data.filename} · SHA-256 {data.file_sha256}
      </p>

      <section className="mt-6 space-y-3">
        <p className="text-sm text-slate-600">{d.previous_run_id ? t("checks.vsPrevious", { id: d.previous_run_id }) : t("checks.noPrevious")}</p>
        {noChange && <p className="text-sm text-slate-600">{t("checks.noChanges")}</p>}
        <div className="grid gap-4 lg:grid-cols-3">
          <DiffList title={t("checks.regressed")} items={d.regressions} tone="red" />
          <DiffList title={t("checks.newFailures")} items={d.new_failures} tone="amber" />
          <DiffList title={t("checks.fixed")} items={d.fixed} tone="green" />
        </div>
      </section>

      <Card
        className="mt-6"
        title={t("checks.results")}
        actions={
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-xs" role="group">
            <button className={`rounded-md px-2.5 py-1 ${failedOnly ? "bg-white shadow-sm" : ""}`} aria-pressed={failedOnly} onClick={() => setFailedOnly(true)}>
              {t("checks.failedOnly")}
            </button>
            <button className={`rounded-md px-2.5 py-1 ${!failedOnly ? "bg-white shadow-sm" : ""}`} aria-pressed={!failedOnly} onClick={() => setFailedOnly(false)}>
              {t("checks.allResults")}
            </button>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th>{t("common.status")}</th>
                <th>{t("requirements.checkId")}</th>
                <th>{t("checks.resource")}</th>
                <th>{t("checks.requirementsShort")}</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={`${r.check_id}-${r.resource}`}>
                  <td>
                    <CheckChip status={r.status} />
                  </td>
                  <td>
                    <div className="text-sm">{r.title || r.check_id}</div>
                    <div className="text-xs text-slate-600">{r.message}</div>
                    <code className="text-[11px] text-slate-400" dir="ltr">
                      {r.check_id}
                    </code>
                  </td>
                  <td className="max-w-xs truncate text-xs text-slate-600" dir="ltr" title={r.resource}>
                    {r.resource}
                  </td>
                  <td className="whitespace-nowrap text-xs">
                    {r.requirements.map((id) => (
                      <Link key={id} to={`/requirements/${id}`} className="me-1 text-brand-700 hover:underline">
                        {id.toUpperCase().replace("-", ".")}
                      </Link>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
