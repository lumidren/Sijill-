import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { DaysChip, LEVEL_STYLE, RecordForm, orNull, type Draft, type Field } from "../components/RecordForm";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtNum } from "../i18n";

export const DPIA_CRITERIA = ["sensitive_data", "large_scale", "systematic_monitoring", "new_technology", "vulnerable_people", "cross_border", "automated_decisions", "data_matching"] as const;

interface DpiaRow {
  id: number;
  ref: string;
  title: string;
  activity_id: number | null;
  activity_name: string | null;
  screening: Record<string, boolean | null>;
  screening_result: { criteria_met: string[]; count: number; likely_needed: boolean; complete: boolean };
  description: string;
  necessity: string;
  risks: string;
  measures: string;
  residual_risk: string;
  dpo_opinion: string;
  status: "draft" | "in_review" | "approved" | "rejected";
  owner: string;
  approved_at: string | null;
  review_due: string | null;
  days_to_review: number | null;
}

interface Activity {
  id: number;
  name: string;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  in_review: "bg-sky-50 text-sky-800",
  approved: "bg-green-50 text-green-800 ring-1 ring-green-600/20",
  rejected: "bg-red-50 text-red-800",
};

function fields(t: (k: string) => string, activities: Activity[]): Field[] {
  return [
    { key: "title", label: t("dpias.fields.title"), required: true },
    { key: "activity_id", label: t("dpias.fields.activity"), type: "select", options: [{ value: "", label: t("dpias.noActivity") }, ...activities.map((a) => ({ value: String(a.id), label: a.name }))] },
    ...DPIA_CRITERIA.map((c): Field => ({ key: `sc_${c}`, label: t(`dpias.criteria.${c}`), type: "checkbox", half: true })),
    { key: "description", label: t("dpias.fields.description"), type: "textarea" },
    { key: "necessity", label: t("dpias.fields.necessity"), type: "textarea" },
    { key: "risks", label: t("dpias.fields.risks"), type: "textarea" },
    { key: "measures", label: t("dpias.fields.measures"), type: "textarea" },
    { key: "residual_risk", label: t("dpias.fields.residual"), type: "select", options: [{ value: "", label: "—" }, ...["low", "medium", "high"].map((k) => ({ value: k, label: t(`dpias.residual.${k}`) }))], half: true },
    { key: "status", label: t("dpias.fields.status"), type: "select", options: ["draft", "in_review"].map((k) => ({ value: k, label: t(`dpias.statuses.${k}`) })), half: true },
    { key: "dpo_opinion", label: t("dpias.fields.opinion"), type: "textarea" },
    { key: "owner", label: t("dpias.fields.owner"), half: true },
    { key: "review_due", label: t("dpias.fields.reviewDue"), type: "date", half: true },
  ];
}

const EMPTY: Draft = { title: "", activity_id: "", description: "", necessity: "", risks: "", measures: "", residual_risk: "", status: "draft", dpo_opinion: "", owner: "", review_due: "", ...Object.fromEntries(DPIA_CRITERIA.map((c) => [`sc_${c}`, false])) };

const toDraft = (d: DpiaRow): Draft => ({
  ...EMPTY,
  title: d.title, activity_id: d.activity_id ? String(d.activity_id) : "", description: d.description, necessity: d.necessity, risks: d.risks, measures: d.measures,
  residual_risk: d.residual_risk, status: d.status === "approved" || d.status === "rejected" ? "in_review" : d.status, dpo_opinion: d.dpo_opinion, owner: d.owner, review_due: d.review_due ?? "",
  ...Object.fromEntries(DPIA_CRITERIA.map((c) => [`sc_${c}`, !!d.screening[c]])),
});

const body = (d: Draft) => ({
  title: d.title, activity_id: d.activity_id ? Number(d.activity_id) : null, description: d.description, necessity: d.necessity, risks: d.risks, measures: d.measures,
  residual_risk: d.residual_risk, status: d.status, dpo_opinion: d.dpo_opinion, owner: d.owner, review_due: orNull(d.review_due),
  screening: Object.fromEntries(DPIA_CRITERIA.map((c) => [c, !!d[`sc_${c}`]])),
});

export function ScreeningResult({ count }: { count: number }) {
  const { t } = useTranslation();
  return count >= 2 ? (
    <span className="chip bg-amber-100 text-amber-900">{t("dpias.likelyNeeded", { count: fmtNum(count) })}</span>
  ) : (
    <span className="chip bg-slate-100 text-slate-700">{t("dpias.likelyNotNeeded", { count: fmtNum(count) })}</span>
  );
}

export default function Dpias() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<DpiaRow[]>("/api/dpias");
  const activities = useApi<Activity[]>("/api/register");
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function approve(d: DpiaRow) {
    setActionError(null);
    try {
      await api.post(`/api/dpias/${d.id}/approve`, {});
      reload();
    } catch {
      setActionError(t("dpias.approveHint"));
    }
  }

  return (
    <>
      <PageHeader
        title={t("dpias.title")}
        subtitle={t("dpias.subtitle")}
        actions={can("governance.write") && <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>+ {t("gov.add")}</button>}
      />
      <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{t("dpias.screeningHint")}</p>
      <ErrorBox error={error} onRetry={reload} />
      {actionError && (
        <p role="alert" className="mb-4 text-sm text-red-700">
          {actionError}
        </p>
      )}
      {loading && !data ? (
        <Spinner />
      ) : !data?.length ? (
        <EmptyState title={t("gov.empty")} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.map((d) => (
            <Card key={d.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="text-xs text-slate-500" dir="ltr">
                    {d.ref}
                  </div>
                  <h2 className="font-semibold">{d.title}</h2>
                  <div className="text-sm text-slate-600">{d.activity_name ?? t("dpias.noActivity")}</div>
                </div>
                <span className={`chip ${STATUS_STYLE[d.status]}`}>{t(`dpias.statuses.${d.status}`)}</span>
              </div>
              <div className="mt-3 space-y-2">
                <ScreeningResult count={d.screening_result.count} />
                {d.screening_result.criteria_met.length > 0 && (
                  <ul className="flex flex-wrap gap-1">
                    {d.screening_result.criteria_met.map((c) => (
                      <li key={c} className="chip bg-slate-100 text-slate-700">
                        {t(`dpias.criteria.${c}`)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <div>
                  <dt className="text-xs text-slate-500">{t("dpias.fields.residual")}</dt>
                  <dd>{d.residual_risk ? <span className={`chip ${LEVEL_STYLE[d.residual_risk]}`}>{t(`dpias.residual.${d.residual_risk}`)}</span> : "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">{t("dpias.fields.reviewDue")}</dt>
                  <dd className="space-x-1">
                    <span>{fmtDate(d.review_due)}</span> <DaysChip days={d.days_to_review} done={d.status !== "approved"} />
                  </dd>
                </div>
                {d.approved_at && <div className="col-span-2 text-xs text-green-800">{t("gov.approvedOn", { when: fmtDate(d.approved_at) })}</div>}
              </dl>
              {d.dpo_opinion && <p className="mt-3 border-s-2 border-brand-200 ps-3 text-sm text-slate-700">{d.dpo_opinion}</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                {can("governance.write") && (
                  <button className="btn-secondary text-xs" onClick={() => setEditing({ id: d.id, draft: toDraft(d) })}>
                    {t("common.edit")}
                  </button>
                )}
                {can("approve") && d.status === "in_review" && (
                  <button className="btn-primary text-xs" onClick={() => approve(d)} title={t("dpias.approveHint")}>
                    {t("gov.approve")}
                  </button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && (
        <RecordForm
          title={editing.id ? t("gov.edit") : t("gov.add")}
          fields={fields(t, activities.data ?? [])}
          initial={editing.draft}
          onClose={() => setEditing(null)}
          footer={(d) => (
            <div className="mt-4 space-y-1">
              <ScreeningResult count={DPIA_CRITERIA.filter((c) => d[`sc_${c}`]).length} />
              <p className="text-xs text-slate-500">{t("dpias.approveHint")}</p>
            </div>
          )}
          onSubmit={async (d) => {
            if (editing.id) await api.put(`/api/dpias/${editing.id}`, body(d));
            else await api.post("/api/dpias", body(d));
            reload();
          }}
        />
      )}
    </>
  );
}
