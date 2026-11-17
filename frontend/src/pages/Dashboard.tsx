import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MiniBar, ScoreRing, StackedBar, TrendChart } from "../components/charts";
import { BasisChip, Card, EmptyState, ErrorBox, PageHeader, Spinner, StaleChip, StatusChip } from "../components/ui";
import { useApi, useNow } from "../hooks";
import { fmtDateTime, fmtNum, pick } from "../i18n";
import type { Dashboard as DashboardData } from "../types";

function shortResource(r: string) {
  const tail = r.split(/[:/]/).filter(Boolean).pop();
  return tail || r;
}

export default function Dashboard() {
  const { t, i18n } = useTranslation();
  const { data, error, loading, reload } = useApi<DashboardData>("/api/posture/dashboard");
  const now = useNow(60_000);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  const c = data.counts;
  const org = data.organization;
  const coverage = [
    { key: "automated", label: t("basis.automated"), value: c.by_basis.automated ?? 0, className: "bg-sky-500" },
    { key: "attested", label: t("basis.attested"), value: c.by_basis.attested ?? 0, className: "bg-violet-500" },
    { key: "not_assessed", label: t("basis.not_assessed"), value: c.by_basis.not_assessed ?? 0, className: "bg-slate-300" },
  ];
  const statuses = [
    { key: "compliant", label: t("status.compliant"), value: c.by_status.compliant ?? 0, className: "bg-green-600" },
    { key: "partial", label: t("status.partial"), value: c.by_status.partial ?? 0, className: "bg-amber-400" },
    { key: "non_compliant", label: t("status.non_compliant"), value: c.by_status.non_compliant ?? 0, className: "bg-red-600" },
  ];
  // Most recent movement: latest score vs the last different score before it.
  const latest = data.trend.at(-1)?.overall;
  const prior = [...data.trend].reverse().find((p) => Math.abs(p.overall - (latest ?? 0)) > 0.0005)?.overall;
  const delta = latest != null && prior != null ? Math.round((latest - prior) * 1000) / 10 : 0;
  const areaById = Object.fromEntries(data.areas.map((a) => [a.id, a]));

  return (
    <>
      <PageHeader
        title={org ? (i18n.language === "ar" && org.name_ar ? org.name_ar : org.name) : t("dashboard.title")}
        subtitle={org?.demo ? t("dashboard.demoOrg") : undefined}
        actions={
          <Link to="/requirements" className="btn-secondary">
            {t("dashboard.explain")}
          </Link>
        }
      />

      <div className="grid items-start gap-5 lg:grid-cols-3">
        {/* Score */}
        <Card className="flex flex-col">
          <h2 className="text-base font-semibold">{t("dashboard.scoreTitle")}</h2>
          <div className="mt-4 flex flex-col items-center gap-3">
            <ScoreRing value={data.overall} label={`${t("dashboard.scoreTitle")}: ${data.overall == null ? t("dashboard.notScored") : fmtNum(Math.round(data.overall * 100))} ${t("dashboard.scoreOutOf")}`} />
            <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
              {delta < 0 && (
                <span className="chip bg-red-50 text-red-800 ring-1 ring-red-600/20">
                  <span aria-hidden>▼</span> {t("dashboard.dip", { points: fmtNum(Math.abs(delta), 1) })}
                </span>
              )}
              {c.stale > 0 && (
                <span className="flex items-center gap-1">
                  <StaleChip /> <span className="text-xs text-slate-600">{fmtNum(c.stale)}</span>
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500">{t("dashboard.ofRequirements", { count: fmtNum(c.total - (c.by_status.not_applicable ?? 0)), total: fmtNum(c.total) })}</p>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-slate-500">{t("dashboard.scoreCaption")}</p>
        </Card>

        {/* Coverage split */}
        <Card title={t("dashboard.coverageTitle")} className="lg:col-span-2">
          <StackedBar segments={coverage} total={c.total} title={t("dashboard.coverageTitle")} />
          <p className="mt-4 text-sm text-slate-600">
            {t("dashboard.technicalCoverage", { automated: fmtNum(c.technical_automated), technical: fmtNum(c.technical_total) })}{" "}
            {t("dashboard.coverageCaption")}
          </p>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <h3 className="mb-3 text-sm font-semibold text-slate-700">{t("dashboard.statusTitle")}</h3>
            <StackedBar segments={statuses} total={c.total} title={t("dashboard.statusTitle")} />
          </div>
        </Card>

        {/* Trend */}
        <Card title={t("dashboard.trend")} className="lg:col-span-2">
          {data.trend.length < 2 ? <EmptyState title={t("dashboard.trendEmpty")} /> : <TrendChart data={data.trend} />}
        </Card>

        {/* Regressions */}
        <Card
          title={
            <span className="flex items-center gap-2">
              {t("dashboard.regressions")}
              {data.regressions.length > 0 && <span className="chip bg-red-600 text-white">{fmtNum(data.regressions.length)}</span>}
            </span>
          }
        >
          <p className="-mt-2 mb-3 text-xs text-slate-500">{t("dashboard.regressionsCaption")}</p>
          {data.regressions.length === 0 ? (
            <EmptyState title={t("dashboard.regressionsEmpty")} />
          ) : (
            <ul className="space-y-3">
              {data.regressions.slice(0, 3).map((r) => (
                <li key={`${r.run_id}-${r.check_id}-${r.resource}`} className="rounded-xl border border-red-200 bg-red-50/60 p-3">
                  <Link to={`/checks/runs/${r.run_id}`} className="text-sm font-medium text-red-900 hover:underline">
                    {r.title || r.check_id}
                  </Link>
                  <div className="mt-1 text-xs text-red-800/80" dir="ltr">
                    {shortResource(r.resource)} · {r.target}
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    {t("dashboard.detectedOn", { when: fmtDateTime(r.detected_at) })} ·{" "}
                    {t("dashboard.affects", { reqs: r.requirements.map((id) => id.toUpperCase().replace("-", ".")).join(", ") })}
                  </div>
                </li>
              ))}
              {data.regressions.length > 3 && (
                <li>
                  <Link to="/checks?tab=regressions" className="text-sm font-medium text-brand-700 hover:underline">
                    {t("dashboard.viewAll")} ({fmtNum(data.regressions.length)})
                  </Link>
                </li>
              )}
            </ul>
          )}
        </Card>

        {/* Areas */}
        <Card title={t("dashboard.areas")} className="lg:col-span-2">
          <ul className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {data.areas.map((a) => (
              <li key={a.id}>
                <Link to={`/requirements?area=${a.id}`} className="group block rounded-lg p-1.5 hover:bg-slate-50">
                  <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate font-medium text-slate-800 group-hover:text-brand-800">
                      <span className="me-1.5 text-xs text-slate-400">{a.label}</span>
                      {pick(a.title)}
                    </span>
                    <span className="shrink-0 tabular-nums text-slate-600">{a.score == null ? "—" : fmtNum(Math.round(a.score * 100))}</span>
                  </div>
                  <MiniBar value={a.score} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        {/* Gaps */}
        <Card
          title={t("dashboard.gaps")}
          actions={
            <Link to="/requirements?status=gaps" className="text-sm font-medium text-brand-700 hover:underline">
              {t("dashboard.viewAll")}
            </Link>
          }
        >
          {data.gaps.length === 0 ? (
            <EmptyState title={data.counts.by_basis.not_assessed === data.counts.total ? t("dashboard.noGapsYet") : t("dashboard.gapsEmpty")} />
          ) : (
            <>
              <p className="-mt-2 mb-3 text-xs text-slate-500">{t("dashboard.gapCount", { count: fmtNum(data.gap_total) })}</p>
              <ul className="divide-y divide-slate-100">
                {data.gaps.map((g) => (
                  <li key={g.id} className="py-2.5">
                    <Link to={`/requirements/${g.id}`} className="block hover:text-brand-800">
                      <div className="flex items-start justify-between gap-3">
                        <span className="text-sm">
                          <span className="me-1.5 text-xs text-slate-400">{g.label}</span>
                          {pick(g.title)}
                        </span>
                        <StatusChip status={g.status} />
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-slate-500">
                        <span>{pick(areaById[g.area_id]?.title)}</span>
                        {g.capped && <span className="chip bg-amber-50 text-amber-800">{t("dashboard.capped")}</span>}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        {/* Monitored systems */}
        <Card title={t("dashboard.targetsTitle")} className={data.features?.obligations || data.features?.incidents ? "" : "lg:col-span-3"}>
          {data.targets.length === 0 ? (
            <EmptyState
              title={t("dashboard.noRuns")}
              hint={t("dashboard.noRunsHint")}
              action={
                <Link to="/checks" className="btn-primary">
                  {t("checks.import")}
                </Link>
              }
            />
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.targets.map((tg) => (
                <li key={tg.run_id}>
                  <Link to={`/checks/runs/${tg.run_id}`} className="block rounded-xl border border-slate-200 p-3 hover:border-brand-300 hover:bg-brand-50/40">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium" dir="ltr">
                        {tg.target}
                      </span>
                      <BasisChip basis="automated" />
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {t(`checks.providers.${tg.provider}`, { defaultValue: tg.provider })} · {fmtDateTime(tg.started_at)}
                    </div>
                    <div className="mt-2 flex gap-3 text-xs">
                      <span className="text-green-700">
                        {t("checks.passed")} {fmtNum(tg.passed)}
                      </span>
                      <span className="text-red-700">
                        {t("checks.failed")} {fmtNum(tg.failed)}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {data.features?.obligations && (
          <Card
            title={t("dashboard.deadlines")}
            actions={
              <Link to="/obligations" className="text-sm font-medium text-brand-700 hover:underline">
                {t("dashboard.viewAll")}
              </Link>
            }
          >
            {data.deadlines.length === 0 ? (
              <EmptyState title={t("dashboard.deadlinesEmpty")} />
            ) : (
              <ul className="divide-y divide-slate-100">
                {data.deadlines.map((d) => (
                  <li key={`${d.kind}-${d.id}`} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <span>{d.title}</span>
                    <span className={`chip ${d.days_left < 0 ? "bg-red-600 text-white" : d.days_left <= 30 ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-700"}`}>
                      {d.days_left < 0 ? t("dashboard.overdue") : t("dashboard.dueIn", { days: fmtNum(d.days_left) })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}

        {data.features?.incidents && (
          <Card
            title={t("dashboard.breaches")}
            actions={
              <Link to="/incidents" className="text-sm font-medium text-brand-700 hover:underline">
                {t("dashboard.viewAll")}
              </Link>
            }
          >
            {data.breaches.length === 0 ? (
              <EmptyState title={t("dashboard.breachesEmpty")} />
            ) : (
              <ul className="space-y-3">
                {data.breaches.map((b) => {
                  const hours = Math.floor((new Date(b.regulator_due).getTime() - now.getTime()) / 3_600_000);
                  return (
                    <li key={b.id}>
                      <Link to={`/incidents/${b.id}`} className={`block rounded-xl border p-3 ${hours < 0 ? "border-red-300 bg-red-50" : hours < 12 ? "border-amber-300 bg-amber-50" : "border-slate-200"}`}>
                        <div className="text-sm font-medium">{b.title}</div>
                        <div className={`mt-1 text-xs font-semibold ${hours < 0 ? "text-red-700" : "text-amber-800"}`}>
                          {hours < 0 ? t("dashboard.overdue") : t("dashboard.hoursLeft", { hours: fmtNum(hours) })}
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
