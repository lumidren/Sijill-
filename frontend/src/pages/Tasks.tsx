import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { DaysChip, RecordForm, orNull, toDraft, type Draft, type Field } from "../components/RecordForm";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate } from "../i18n";

export interface TaskRow {
  id: number;
  title: string;
  description: string;
  requirement_id: string | null;
  requirement_label: string | null;
  source: string;
  source_id: string;
  owner: string;
  priority: "low" | "medium" | "high";
  status: "todo" | "in_progress" | "blocked" | "done";
  due_on: string | null;
  days_left: number | null;
  overdue: boolean;
  notes: string;
}

const PRIORITY_STYLE = { low: "bg-slate-100 text-slate-700", medium: "bg-sky-50 text-sky-800", high: "bg-red-50 text-red-800 ring-1 ring-red-600/20" };

export function taskFields(t: (k: string) => string): Field[] {
  const opts = (prefix: string, keys: string[]) => keys.map((k) => ({ value: k, label: t(`${prefix}.${k}`) }));
  return [
    { key: "title", label: t("tasks.fields.title"), required: true },
    { key: "description", label: t("tasks.fields.description"), type: "textarea" },
    { key: "requirement_id", label: t("tasks.fields.requirement"), dir: "ltr", half: true },
    { key: "owner", label: t("tasks.fields.owner"), half: true },
    { key: "priority", label: t("tasks.fields.priority"), type: "select", options: opts("tasks.priorities", ["low", "medium", "high"]), half: true },
    { key: "status", label: t("tasks.fields.status"), type: "select", options: opts("tasks.statuses", ["todo", "in_progress", "blocked", "done"]), half: true },
    { key: "due_on", label: t("tasks.fields.due"), type: "date", half: true },
    { key: "notes", label: t("tasks.fields.notes"), type: "textarea" },
  ];
}

export const taskBody = (d: Draft) => ({
  title: d.title, description: d.description, requirement_id: orNull(String(d.requirement_id ?? "").trim()), owner: d.owner,
  priority: d.priority, status: d.status, due_on: orNull(d.due_on), notes: d.notes, source: d.source || "manual", source_id: d.source_id || "",
});

export const EMPTY_TASK: Draft = { title: "", description: "", requirement_id: "", owner: "", priority: "medium", status: "todo", due_on: "", notes: "", source: "manual", source_id: "" };

export default function Tasks() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<TaskRow[]>("/api/tasks");
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const showDone = params.get("done") === "1";
  const overdueOnly = params.get("overdue") === "1";

  // /tasks?new=a06-05 opens the form prefilled for that requirement (from a gap or drill-down)
  useEffect(() => {
    const req = params.get("new");
    if (req && can("tasks.write")) {
      setEditing({ id: null, draft: { ...EMPTY_TASK, requirement_id: req, source: "gap", title: params.get("title") ?? "" } });
      const next = new URLSearchParams(params);
      next.delete("new");
      next.delete("title");
      setParams(next, { replace: true });
    }
  }, [params, setParams, can]);

  const rows = (data ?? []).filter((r) => (showDone || r.status !== "done") && (!overdueOnly || r.overdue));
  const toggle = (k: string, on: boolean) => {
    const next = new URLSearchParams(params);
    if (on) next.set(k, "1");
    else next.delete(k);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader
        title={t("tasks.title")}
        subtitle={t("tasks.subtitle")}
        actions={can("tasks.write") && <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY_TASK })}>+ {t("gov.add")}</button>}
      />
      <div className="mb-4 flex flex-wrap gap-4 text-sm text-slate-700">
        <label className="flex items-center gap-2">
          <input type="checkbox" className="accent-brand-700" checked={overdueOnly} onChange={(e) => toggle("overdue", e.target.checked)} />
          {t("tasks.filterOverdue")}
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" className="accent-brand-700" checked={showDone} onChange={(e) => toggle("done", e.target.checked)} />
          {t("tasks.showDone")}
        </label>
      </div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : !rows.length ? (
        <EmptyState title={t("gov.empty")} />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>{t("tasks.fields.title")}</th>
                  <th>{t("tasks.fields.priority")}</th>
                  <th>{t("tasks.fields.status")}</th>
                  <th>{t("tasks.fields.due")}</th>
                  <th>{t("tasks.fields.owner")}</th>
                  <th>
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={r.status === "done" ? "opacity-60" : ""}>
                    <td>
                      <div className="font-medium">{r.title}</div>
                      <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-500">
                        <span>{t(`tasks.sources.${r.source}`)}</span>
                        {r.requirement_id && (
                          <Link to={`/requirements/${r.requirement_id}`} className="text-brand-700 hover:underline" dir="ltr">
                            {r.requirement_label}
                          </Link>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`chip ${PRIORITY_STYLE[r.priority]}`}>{t(`tasks.priorities.${r.priority}`)}</span>
                    </td>
                    <td className="text-sm">{t(`tasks.statuses.${r.status}`)}</td>
                    <td className="space-y-1 text-sm">
                      <div>{fmtDate(r.due_on)}</div>
                      <DaysChip days={r.days_left} done={r.status === "done"} />
                    </td>
                    <td className="text-sm text-slate-700">{r.owner || "—"}</td>
                    <td className="text-end">
                      {can("tasks.write") && (
                        <button className="btn-ghost text-xs" onClick={() => setEditing({ id: r.id, draft: { ...EMPTY_TASK, ...toDraft(r), requirement_id: r.requirement_id ?? "", due_on: r.due_on ?? "" } })}>
                          {t("common.edit")}
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
          fields={taskFields(t)}
          initial={editing.draft}
          onClose={() => setEditing(null)}
          onSubmit={async (d) => {
            if (editing.id) await api.put(`/api/tasks/${editing.id}`, taskBody(d));
            else await api.post("/api/tasks", taskBody(d));
            reload();
          }}
        />
      )}
    </>
  );
}
