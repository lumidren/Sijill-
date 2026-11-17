import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fmtNum } from "../i18n";
import { HeatMap } from "../pages/Risks";
import type { GovernanceSummary } from "../types";
import { Card } from "./ui";

function Stat({ to, label, value, alert, extra }: { to: string; label: string; value: number; alert?: boolean; extra?: string }) {
  return (
    <Link to={to} className="block rounded-xl border border-slate-200 px-3 py-2.5 hover:border-brand-300 hover:bg-brand-50/40">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span className={`text-xl font-semibold ${alert ? "text-red-700" : "text-ink"}`}>{fmtNum(value)}</span>
        {extra && <span className={`text-xs ${alert ? "font-medium text-red-700" : "text-slate-500"}`}>{extra}</span>}
      </div>
    </Link>
  );
}

/** Grid counts [impact-1][likelihood-1] -> rows the HeatMap can count. */
const gridRows = (grid: number[][]) =>
  grid.flatMap((row, i) => row.flatMap((n, l) => Array.from({ length: n }, () => ({ likelihood: l + 1, impact: i + 1, status: "open" }))));

export function GovernanceCard({ g }: { g: GovernanceSummary }) {
  const { t } = useTranslation();
  return (
    <Card title={t("gov.glance")} className="lg:col-span-3">
      <div className="grid gap-5 md:grid-cols-[auto_1fr]">
        <Link to="/risks" className="block" aria-label={t("risks.title")}>
          <HeatMap rows={gridRows(g.risks.heat_map)} compact />
        </Link>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
          <Stat to="/tasks" label={t("gov.openTasks")} value={g.tasks.open} alert={g.tasks.overdue > 0} extra={g.tasks.overdue ? `${fmtNum(g.tasks.overdue)} ${t("gov.overdueTasks")}` : undefined} />
          <Stat
            to="/risks"
            label={t("gov.openRisks")}
            value={g.risks.open}
            alert={!!g.risks.by_level.critical}
            extra={g.risks.by_level.critical ? `${fmtNum(g.risks.by_level.critical)} ${t("risks.levels.critical")}` : undefined}
          />
          <Stat to="/requests" label={t("gov.requestsOpen")} value={g.requests.open} alert={g.requests.overdue > 0} extra={g.requests.overdue ? `${fmtNum(g.requests.overdue)} ${t("gov.requestsOverdue")}` : undefined} />
          <Stat to="/vendors" label={t("gov.vendorsNoDpa")} value={g.vendors.without_dpa} alert={g.vendors.without_dpa > 0} />
          <Stat to="/policies" label={t("gov.policiesReview")} value={g.policies.review_overdue} alert={g.policies.review_overdue > 0} />
          <Stat to="/dpias" label={t("gov.dpiasPending")} value={g.dpias.pending} />
        </div>
      </div>
    </Card>
  );
}
