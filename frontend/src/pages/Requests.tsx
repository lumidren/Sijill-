import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { DaysChip, RecordForm, toDraft, type Draft, type Field } from "../components/RecordForm";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtDateTime, fmtNum } from "../i18n";
import { toCairoInput } from "./Incidents";

interface RequestRow {
  id: number;
  ref: string;
  request_type: string;
  requester: string;
  channel: string;
  received_at: string;
  identity_verified: boolean;
  status: string;
  details: string;
  outcome: string;
  owner: string;
  due_at: string;
  days_left: number | null;
  state: "on_track" | "due_soon" | "overdue" | "done" | "late";
  response_days: number;
}

const STATE_STYLE: Record<string, string> = {
  on_track: "bg-slate-100 text-slate-700",
  due_soon: "bg-amber-100 text-amber-900",
  overdue: "bg-red-600 text-white",
  done: "bg-green-50 text-green-800",
  late: "bg-amber-50 text-amber-800 ring-1 ring-amber-600/25",
};
const TYPES = ["access", "correction", "deletion", "objection", "withdraw_consent", "portability", "other"];

function fields(t: (k: string) => string): Field[] {
  return [
    { key: "request_type", label: t("requests.fields.type"), type: "select", options: TYPES.map((k) => ({ value: k, label: t(`requests.types.${k}`) })), half: true },
    { key: "received_at", label: t("requests.fields.received"), type: "datetime-local", required: true, half: true },
    { key: "requester", label: t("requests.fields.requester"), required: true },
    { key: "channel", label: t("requests.fields.channel"), half: true },
    { key: "owner", label: t("requests.fields.owner"), half: true },
    { key: "identity_verified", label: t("requests.fields.identity"), type: "checkbox" },
    { key: "details", label: t("requests.fields.details"), type: "textarea" },
    { key: "status", label: t("requests.fields.status"), type: "select", options: ["received", "in_progress", "completed", "refused"].map((k) => ({ value: k, label: t(`requests.statuses.${k}`) })), half: true },
    { key: "outcome", label: t("requests.fields.outcome"), type: "textarea" },
  ];
}

const EMPTY = (): Draft => ({ request_type: "access", received_at: toCairoInput(new Date().toISOString()), requester: "", channel: "", owner: "", identity_verified: false, details: "", status: "received", outcome: "" });

export default function Requests() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<RequestRow[]>("/api/requests");
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const days = data?.[0]?.response_days ?? 30;

  return (
    <>
      <PageHeader
        title={t("requests.title")}
        subtitle={t("requests.subtitle")}
        actions={can("governance.write") && <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY() })}>+ {t("gov.add")}</button>}
      />
      <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{t("requests.rule", { days: fmtNum(days) })}</p>
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
                  <th>{t("requests.fields.type")}</th>
                  <th>{t("requests.fields.requester").split(" (")[0]}</th>
                  <th>{t("requests.fields.received").split(" (")[0]}</th>
                  <th>{t("gov.status")}</th>
                  <th>
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div className="font-medium">{t(`requests.types.${r.request_type}`)}</div>
                      <div className="text-xs text-slate-500" dir="ltr">
                        {r.ref}
                      </div>
                    </td>
                    <td className="text-sm">
                      <div>{r.requester}</div>
                      {!r.identity_verified && r.days_left !== null && <div className="text-xs text-amber-800">{t("requests.identityPending")}</div>}
                    </td>
                    <td className="text-sm">
                      <div>{fmtDateTime(r.received_at)}</div>
                      <div className="text-xs text-slate-500">{t("requests.due", { when: fmtDate(r.due_at) })}</div>
                    </td>
                    <td className="space-y-1 text-sm">
                      <div>{t(`requests.statuses.${r.status}`)}</div>
                      <span className={`chip ${STATE_STYLE[r.state]}`}>{t(`requests.states.${r.state}`)}</span> <DaysChip days={r.days_left} />
                    </td>
                    <td className="text-end">
                      {can("governance.write") && (
                        <button className="btn-ghost text-xs" onClick={() => setEditing({ id: r.id, draft: { ...EMPTY(), ...toDraft(r), received_at: toCairoInput(r.received_at) } })}>
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
          fields={fields(t)}
          initial={editing.draft}
          onClose={() => setEditing(null)}
          onSubmit={async (d) => {
            const body = { request_type: d.request_type, received_at: d.received_at, requester: d.requester, channel: d.channel, owner: d.owner, identity_verified: !!d.identity_verified, details: d.details, status: d.status, outcome: d.outcome };
            if (editing.id) await api.put(`/api/requests/${editing.id}`, body);
            else await api.post("/api/requests", body);
            reload();
          }}
        />
      )}
    </>
  );
}
