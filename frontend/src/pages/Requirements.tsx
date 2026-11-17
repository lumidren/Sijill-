import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MiniBar } from "../components/charts";
import { BasisChip, Card, EmptyState, ErrorBox, PageHeader, Spinner, StaleChip, StatusChip, Unverified, type Basis, type ReqStatus } from "../components/ui";
import { useApi } from "../hooks";
import { fmtNum, pick } from "../i18n";
import type { Posture } from "../types";

const STATUSES: ReqStatus[] = ["compliant", "partial", "non_compliant", "not_assessed", "not_applicable"];
const BASES: Basis[] = ["automated", "attested", "not_assessed"];

export default function Requirements() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi<Posture>("/api/posture");
  const [params, setParams] = useSearchParams();
  const area = params.get("area") || "";
  const status = params.get("status") || "";
  const basis = params.get("basis") || "";
  const q = (params.get("q") || "").trim().toLowerCase();

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.requirements.filter((r) => {
      if (area && r.area_id !== area) return false;
      if (status === "gaps" && !["partial", "non_compliant", "not_assessed"].includes(r.status)) return false;
      if (status && status !== "gaps" && r.status !== status) return false;
      if (basis && r.basis !== basis) return false;
      if (q && !`${r.label} ${r.title.en} ${r.title.ar}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data, area, status, basis, q]);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  const areas = data.areas.filter((a) => filtered.some((r) => r.area_id === a.id));

  return (
    <>
      <PageHeader title={t("requirements.title")} subtitle={t("requirements.subtitle")} />
      <Card className="mb-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label" htmlFor="f-q">
              {t("common.search")}
            </label>
            <input id="f-q" className="input" type="search" placeholder={t("requirements.search")} value={params.get("q") || ""} onChange={(e) => set("q", e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="f-area">
              {t("requirements.filterArea")}
            </label>
            <select id="f-area" className="input" value={area} onChange={(e) => set("area", e.target.value)}>
              <option value="">{t("requirements.allAreas")}</option>
              {data.areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label} · {pick(a.title)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="f-status">
              {t("requirements.filterStatus")}
            </label>
            <select id="f-status" className="input" value={status} onChange={(e) => set("status", e.target.value)}>
              <option value="">{t("common.all")}</option>
              <option value="gaps">{t("dashboard.gaps")}</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`status.${s}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="f-basis">
              {t("requirements.filterBasis")}
            </label>
            <select id="f-basis" className="input" value={basis} onChange={(e) => set("basis", e.target.value)}>
              <option value="">{t("common.all")}</option>
              {BASES.map((b) => (
                <option key={b} value={b}>
                  {t(`basis.${b}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {filtered.length === 0 ? (
        <EmptyState title={t("requirements.empty")} />
      ) : (
        <div className="space-y-5">
          {areas.map((a) => (
            <Card key={a.id}>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">
                    <span className="me-2 text-sm text-slate-500">{a.label}</span>
                    {pick(a.title)}
                  </h2>
                  <p className="text-sm text-slate-500">{pick(a.overview)}</p>
                </div>
                <div className="w-40">
                  <div className="mb-1 flex justify-between text-xs text-slate-500">
                    <span>{t("requirements.areaScore")}</span>
                    <span className="font-semibold text-ink">{a.score == null ? "—" : fmtNum(Math.round(a.score * 100))}</span>
                  </div>
                  <MiniBar value={a.score} />
                </div>
              </div>
              <ul className="divide-y divide-slate-100">
                {filtered
                  .filter((r) => r.area_id === a.id)
                  .map((r) => (
                    <li key={r.id}>
                      <Link to={`/requirements/${r.id}`} className="-mx-2 flex flex-col gap-2 rounded-lg px-2 py-3 hover:bg-slate-50 sm:flex-row sm:items-center">
                        <span className="w-14 shrink-0 text-xs font-medium text-slate-500">{r.label}</span>
                        <span className="min-w-0 flex-1 text-sm text-ink">
                          {pick(r.title)} {!r.verified && <Unverified />}
                        </span>
                        <span className="flex flex-wrap items-center gap-1.5">
                          {r.capped && <span className="chip bg-amber-50 text-amber-800 ring-1 ring-amber-600/20">{t("dashboard.capped")}</span>}
                          {r.stale && <StaleChip />}
                          <BasisChip basis={r.basis} />
                          <StatusChip status={r.status} />
                        </span>
                      </Link>
                    </li>
                  ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
