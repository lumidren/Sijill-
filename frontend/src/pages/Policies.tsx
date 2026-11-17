import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { DaysChip, RecordForm, lines, orNull, toDraft, type Draft, type Field } from "../components/RecordForm";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate } from "../i18n";

interface PolicyRow {
  id: number;
  title: string;
  version: string;
  status: "draft" | "approved" | "retired";
  owner: string;
  summary: string;
  requirement_ids: string[];
  evidence_file_id: number | null;
  approved_on: string | null;
  review_due: string | null;
  days_to_review: number | null;
  review_overdue: boolean;
  history: { version: string; status: string; at: string; by: string }[];
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  approved: "bg-green-50 text-green-800 ring-1 ring-green-600/20",
  retired: "bg-slate-50 text-slate-500",
};

function fields(t: (k: string) => string): Field[] {
  return [
    { key: "title", label: t("policies.fields.title"), required: true },
    { key: "version", label: t("policies.fields.version"), required: true, dir: "ltr", half: true, hint: t("policies.newVersionHint") },
    { key: "owner", label: t("policies.fields.owner"), half: true },
    { key: "summary", label: t("policies.fields.summary"), type: "textarea" },
    { key: "requirement_ids", label: t("gov.requirements"), type: "lines", dir: "ltr" },
    { key: "review_due", label: t("policies.fields.reviewDue"), type: "date", half: true },
    { key: "evidence_file_id", label: t("policies.fields.evidence"), type: "number", half: true },
    { key: "status", label: t("policies.fields.status"), type: "select", options: ["draft", "retired"].map((k) => ({ value: k, label: t(`policies.statuses.${k}`) })), half: true, show: (d) => !d._approved },
    // An approved policy stays approved when edited under the same version ("draft" is sent; the server keeps the approval).
    { key: "status", label: t("policies.fields.status"), type: "select", options: [{ value: "draft", label: t("policies.statuses.approved") }, { value: "retired", label: t("policies.statuses.retired") }], half: true, show: (d) => !!d._approved },
  ];
}

const EMPTY: Draft = { title: "", version: "1.0", owner: "", summary: "", requirement_ids: "", review_due: "", evidence_file_id: "", status: "draft" };
const body = (d: Draft) => ({
  title: d.title, version: String(d.version).trim(), owner: d.owner, summary: d.summary, requirement_ids: lines(d.requirement_ids),
  review_due: orNull(d.review_due), evidence_file_id: d.evidence_file_id ? Number(d.evidence_file_id) : null, status: d.status,
});

export default function Policies() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<PolicyRow[]>("/api/policies");
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  return (
    <>
      <PageHeader
        title={t("policies.title")}
        subtitle={t("policies.subtitle")}
        actions={can("governance.write") && <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>+ {t("gov.add")}</button>}
      />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : !data?.length ? (
        <EmptyState title={t("gov.empty")} />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>{t("policies.fields.title")}</th>
                  <th>{t("policies.fields.version")}</th>
                  <th>{t("policies.fields.status")}</th>
                  <th>{t("policies.fields.reviewDue")}</th>
                  <th>
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className={p.status === "retired" ? "opacity-60" : ""}>
                    <td>
                      <div className="font-medium">{p.title}</div>
                      {p.summary && <div className="mt-0.5 max-w-md text-xs text-slate-600">{p.summary}</div>}
                      <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-500">
                        {p.owner && <span>{p.owner}</span>}
                        {p.requirement_ids.map((id) => (
                          <Link key={id} to={`/requirements/${id}`} className="text-brand-700 hover:underline" dir="ltr">
                            {id.toUpperCase().replace("-", ".")}
                          </Link>
                        ))}
                      </div>
                      {p.history.length > 0 && (
                        <button className="mt-1 text-xs text-brand-700 hover:underline" aria-expanded={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>
                          {t("policies.history")} ({p.history.length})
                        </button>
                      )}
                      {open === p.id && (
                        <ol className="mt-1 space-y-0.5 text-xs text-slate-600">
                          {[...p.history].reverse().map((h, i) => (
                            <li key={i}>
                              <span dir="ltr">v{h.version}</span> · {t(`policies.statuses.${h.status}`)} · {fmtDate(h.at)} · {h.by}
                            </li>
                          ))}
                        </ol>
                      )}
                    </td>
                    <td className="text-sm" dir="ltr">
                      v{p.version}
                    </td>
                    <td className="space-y-1">
                      <span className={`chip ${STATUS_STYLE[p.status]}`}>{t(`policies.statuses.${p.status}`)}</span>
                      {p.approved_on && <div className="text-xs text-slate-500">{t("gov.approvedOn", { when: fmtDate(p.approved_on) })}</div>}
                    </td>
                    <td className="space-y-1 text-sm">
                      <div>{fmtDate(p.review_due)}</div>
                      {p.review_overdue ? <span className="chip bg-red-600 text-white">{t("policies.reviewOverdue")}</span> : <DaysChip days={p.days_to_review} done={p.status !== "approved"} />}
                    </td>
                    <td className="whitespace-nowrap text-end">
                      {can("governance.write") && (
                        <button
                          className="btn-ghost text-xs"
                          onClick={() =>
                            setEditing({
                              id: p.id,
                              draft: { ...EMPTY, ...toDraft(p), status: p.status === "approved" ? "draft" : p.status, _approved: p.status === "approved", requirement_ids: p.requirement_ids.join("\n"), review_due: p.review_due ?? "", evidence_file_id: p.evidence_file_id ? String(p.evidence_file_id) : "" },
                            })
                          }
                        >
                          {t("common.edit")}
                        </button>
                      )}
                      {can("approve") && p.status === "draft" && (
                        <button
                          className="btn-ghost text-xs"
                          onClick={async () => {
                            await api.post(`/api/policies/${p.id}/approve`, {});
                            reload();
                          }}
                        >
                          {t("gov.approve")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {editing && (
        <RecordForm
          title={editing.id ? t("gov.edit") : t("gov.add")}
          fields={fields(t)}
          initial={editing.draft}
          onClose={() => setEditing(null)}
          onSubmit={async (d) => {
            if (editing.id) await api.put(`/api/policies/${editing.id}`, body(d));
            else await api.post("/api/policies", body(d));
            reload();
          }}
        />
      )}
    </>
  );
}
