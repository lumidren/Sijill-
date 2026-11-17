import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth";
import { DaysChip, LEVEL_STYLE } from "../components/RecordForm";
import { BasisChip, Card, CheckChip, EmptyState, ErrorBox, Spinner, StaleChip, StatusChip, Unverified } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtDateTime, fmtNum, pick } from "../i18n";
import type { RequirementDetail as Detail } from "../types";

function Explanation({ d }: { d: Detail }) {
  const { t } = useTranslation();
  const r = d.result;
  const text =
    r.reason === "capped_by_failing_checks"
      ? t("requirements.capped", { count: fmtNum(r.failing_checks) })
      : r.reason === "na_overridden_by_failing_checks"
        ? t("requirements.naOverridden", { count: fmtNum(r.failing_checks) })
        : r.reason === "derived_from_checks"
          ? t("requirements.derived", { passed: fmtNum(r.passing_checks), failed: fmtNum(r.failing_checks) })
          : r.reason === "from_answer"
            ? t("requirements.fromAnswer")
            : t("requirements.notAssessedReason");
  const tone = r.status === "compliant" ? "border-green-200 bg-green-50" : r.status === "non_compliant" ? "border-red-200 bg-red-50" : r.status === "partial" ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50";
  return (
    <section className={`rounded-2xl border p-5 ${tone}`} aria-labelledby="why">
      <h2 id="why" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
        {t("requirements.why")}
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusChip status={r.status} />
        <BasisChip basis={r.basis} />
        {r.stale && <StaleChip />}
      </div>
      <p className="mt-3 text-sm text-slate-800">{text}</p>
      {(r.attested_status || r.automated_status) && (
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div className="rounded-xl bg-white/70 p-3">
            <dt className="text-xs text-slate-500">{t("requirements.attestedStatus")}</dt>
            <dd className="mt-1">{r.attested_status ? <StatusChip status={r.attested_status} /> : t("requirements.noAnswer")}</dd>
          </div>
          <div className="rounded-xl bg-white/70 p-3">
            <dt className="text-xs text-slate-500">{t("requirements.automatedStatus")}</dt>
            <dd className="mt-1">{r.automated_status ? <StatusChip status={r.automated_status} /> : d.checks.length ? t("requirements.noResult") : "—"}</dd>
          </div>
        </dl>
      )}
      {r.stale && r.evidence_at && <p className="mt-3 text-xs text-orange-800">{t("requirements.staleReason", { when: fmtDate(r.evidence_at), days: fmtNum(d.stale_days) })}</p>}
      <p className="mt-3 text-xs text-slate-600">
        {d.contribution
          ? t("requirements.contributionText", {
              points: fmtNum(d.contribution.points, 1),
              of: fmtNum(d.contribution.of),
              area: pick(d.area.title),
              total: fmtNum(d.contribution.area_weight),
            })
          : t("requirements.excluded")}
      </p>
    </section>
  );
}

export default function RequirementDetail() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<Detail>(`/api/posture/requirements/${id}`);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const req = data.requirement;

  return (
    <>
      <Link to={`/requirements?area=${req.area_id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
        <span aria-hidden className="inline-block rtl:rotate-180">
          ←
        </span>
        {t("requirements.back")}
      </Link>
      <div className="mb-6">
        <p className="text-sm text-slate-500">
          {req.label} • {data.area.label} {pick(data.area.title)}
        </p>
        <h1 className="page-title mt-1 flex flex-wrap items-center gap-3">
          {pick(req.title)} {!req.verified && <Unverified />}
        </h1>
        <p className="mt-1 text-xs text-slate-500">
          {req.technical ? t("requirements.technical") : t("requirements.organisational")} • {t("requirements.weightHint", { weight: fmtNum(req.weight) })}
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Explanation d={data} />

          <Card title={t("requirements.automatedChecks")}>
            {data.checks.length === 0 ? (
              <p className="text-sm text-slate-600">{t("requirements.noChecks")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th>{t("requirements.checkId")}</th>
                      <th>{t("common.status")}</th>
                      <th>{t("requirements.resources")}</th>
                      <th>{t("requirements.lastObserved")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.checks.map((c) => (
                      <tr key={c.check_id}>
                        <td>
                          <div className="text-sm">{c.title}</div>
                          <code className="break-all text-[11px] text-slate-500" dir="ltr">
                            {c.check_id}
                          </code>
                          {c.failing_resources.length > 0 && (
                            <ul className="mt-1 space-y-0.5">
                              {c.failing_resources.slice(0, 4).map((r) => (
                                <li key={r} className="truncate text-[11px] text-red-700" dir="ltr">
                                  ✕ {r}
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td>{c.status ? <CheckChip status={c.status} /> : <span className="text-xs text-slate-500">{t("requirements.noResult")}</span>}</td>
                        <td className="whitespace-nowrap text-xs text-slate-600">{c.status ? t("requirements.resourcesShort", { passing: fmtNum(c.passing), failing: fmtNum(c.failing) }) : "—"}</td>
                        <td className="whitespace-nowrap text-xs text-slate-600">{fmtDateTime(c.last_observed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title={t("requirements.statement")}>
            <p className="text-sm leading-relaxed text-slate-800">{pick(req.statement)}</p>
            <h3 className="mt-5 text-sm font-semibold text-slate-700">{t("requirements.question")}</h3>
            <p className="mt-1 text-sm text-slate-700">{pick(req.question)}</p>
            {pick(req.guidance) && (
              <>
                <h3 className="mt-5 text-sm font-semibold text-slate-700">{t("requirements.guidance")}</h3>
                <p className="mt-1 text-sm text-slate-700">{pick(req.guidance)}</p>
              </>
            )}
            <p className="mt-5 text-xs text-slate-500">
              {t("requirements.source")}: {req.source || t("requirements.sourceNeeded")}
            </p>
          </Card>
        </div>

        <div className="space-y-5">
          <Card title={t("requirements.answer")}>
            {data.answer ? (
              <>
                <StatusChip status={data.answer.status} />
                {data.answer.note && <p className="mt-3 text-sm text-slate-700">{data.answer.note}</p>}
                <p className="mt-3 text-xs text-slate-500">{t("requirements.answerFrom", { who: data.answer.updated_by ?? "—", when: fmtDateTime(data.answer.updated_at) })}</p>
              </>
            ) : (
              <p className="text-sm text-slate-600">{t("requirements.noAnswer")}</p>
            )}
            {can("assessment.write") && (
              <Link to={`/assessment?area=${req.area_id}#${req.id}`} className="btn-secondary mt-4 w-full">
                {t("requirements.answerInAssessment")}
              </Link>
            )}
          </Card>

          <Card title={t("gov.related")}>
            {!data.related || data.related.tasks.length + data.related.risks.length + data.related.policies.length === 0 ? (
              <p className="text-sm text-slate-600">{t("gov.noRelated")}</p>
            ) : (
              <div className="space-y-4 text-sm">
                {data.related.tasks.length > 0 && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold text-slate-500">{t("nav.tasks")}</h3>
                    <ul className="space-y-1.5">
                      {data.related.tasks.map((x) => (
                        <li key={x.id}>
                          <Link to="/tasks?done=1" className="hover:text-brand-800">
                            {x.title}
                          </Link>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                            <span>{t(`tasks.statuses.${x.status}`)}</span>
                            {x.owner && <span>• {x.owner}</span>}
                            <DaysChip days={x.days_left} done={x.status === "done"} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {data.related.risks.length > 0 && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold text-slate-500">{t("nav.risks")}</h3>
                    <ul className="space-y-1.5">
                      {data.related.risks.map((x) => (
                        <li key={x.id} className="flex items-start justify-between gap-2">
                          <Link to="/risks" className="hover:text-brand-800">
                            {x.title}
                          </Link>
                          <span className={`chip shrink-0 ${LEVEL_STYLE[x.level]}`}>{t(`risks.levels.${x.level}`)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {data.related.policies.length > 0 && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold text-slate-500">{t("nav.policies")}</h3>
                    <ul className="space-y-1.5">
                      {data.related.policies.map((x) => (
                        <li key={x.id}>
                          <Link to="/policies" className="hover:text-brand-800">
                            {x.title} <span dir="ltr">v{x.version}</span>
                          </Link>
                          <div className="text-xs text-slate-500">
                            {t(`policies.statuses.${x.status}`)}
                            {x.review_overdue && <span className="ms-1.5 font-medium text-red-700">• {t("policies.reviewOverdue")}</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {can("tasks.write") && !["compliant", "not_applicable"].includes(data.result.status) && (
              <Link to={`/tasks?new=${req.id}&title=${encodeURIComponent(pick(req.title))}`} className="btn-secondary mt-4 w-full">
                {t("tasks.createFromGap")}
              </Link>
            )}
            {can("evidence_requests.manage") && data.result.status !== "not_applicable" && (
              <Link to={`/evidence-requests?new=${req.id}`} className="btn-ghost mt-2 w-full">
                {t("er.askClient")}
              </Link>
            )}
          </Card>

          <Card title={t("requirements.evidence")}>
            {data.evidence.length === 0 ? (
              <EmptyState title={t("requirements.noEvidence")} />
            ) : (
              <ul className="space-y-3">
                {data.evidence.map((f) => (
                  <li key={f.id} className="rounded-xl border border-slate-200 p-3">
                    <a href={`/api/evidence/${f.id}/download`} className="text-sm font-medium text-brand-800 hover:underline">
                      {f.filename}
                    </a>
                    {f.description && <p className="text-xs text-slate-600">{f.description}</p>}
                    <p className="mt-1 text-[11px] text-slate-500">{fmtDateTime(f.uploaded_at)}</p>
                    <p className="truncate font-mono text-[10px] text-slate-500" dir="ltr" title={f.sha256}>
                      SHA-256 {f.sha256}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
