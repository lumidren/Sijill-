import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { DaysChip, LEVEL_STYLE, RecordForm, lines, orNull, toDraft, type Draft, type Field } from "../components/RecordForm";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate } from "../i18n";

interface VendorRow {
  id: number;
  name: string;
  service: string;
  role: string;
  data_categories: string[];
  countries: string[];
  dpa_signed: boolean;
  dpa_signed_on: string | null;
  due_diligence_on: string | null;
  next_review_on: string | null;
  days_to_review: number | null;
  risk_level: string;
  security_notes: string;
  status: string;
  owner: string;
  issues: string[];
}

function fields(t: (k: string) => string): Field[] {
  const opt = (prefix: string, keys: string[]) => keys.map((k) => ({ value: k, label: t(`${prefix}.${k}`) }));
  return [
    { key: "name", label: t("vendors.fields.name"), required: true },
    { key: "service", label: t("vendors.fields.service") },
    { key: "role", label: t("vendors.fields.role"), type: "select", options: opt("vendors.roles", ["processor", "sub_processor", "recipient"]), half: true },
    { key: "risk_level", label: t("vendors.fields.risk"), type: "select", options: opt("vendors.risk", ["low", "medium", "high"]), half: true },
    { key: "data_categories", label: t("vendors.fields.data"), type: "lines", half: true },
    { key: "countries", label: t("vendors.fields.countries"), type: "lines", half: true },
    { key: "dpa_signed", label: t("vendors.fields.dpa"), type: "checkbox" },
    { key: "dpa_signed_on", label: t("vendors.fields.dpaOn"), type: "date", half: true, show: (d) => !!d.dpa_signed },
    { key: "due_diligence_on", label: t("vendors.fields.dueDiligence"), type: "date", half: true },
    { key: "next_review_on", label: t("vendors.fields.nextReview"), type: "date", half: true },
    { key: "owner", label: t("vendors.fields.owner"), half: true },
    { key: "security_notes", label: t("vendors.fields.security"), type: "textarea" },
    { key: "status", label: t("vendors.fields.status"), type: "select", options: opt("vendors.statuses", ["active", "offboarded"]), half: true },
  ];
}

const EMPTY: Draft = { name: "", service: "", role: "processor", risk_level: "medium", data_categories: "", countries: "", dpa_signed: false, dpa_signed_on: "", due_diligence_on: "", next_review_on: "", owner: "", security_notes: "", status: "active" };
const body = (d: Draft) => ({
  name: d.name, service: d.service, role: d.role, risk_level: d.risk_level, data_categories: lines(d.data_categories), countries: lines(d.countries),
  dpa_signed: !!d.dpa_signed, dpa_signed_on: d.dpa_signed ? orNull(d.dpa_signed_on) : null, due_diligence_on: orNull(d.due_diligence_on),
  next_review_on: orNull(d.next_review_on), owner: d.owner, security_notes: d.security_notes, status: d.status,
});

export default function Vendors() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<VendorRow[]>("/api/vendors");
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);

  return (
    <>
      <PageHeader
        title={t("vendors.title")}
        subtitle={t("vendors.subtitle")}
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
                  <th>{t("vendors.fields.name")}</th>
                  <th>{t("vendors.fields.role")}</th>
                  <th>{t("vendors.fields.nextReview")}</th>
                  <th>{t("vendors.fields.risk")}</th>
                  <th>{t("register.issuesTitle")}</th>
                  <th>
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((v) => (
                  <tr key={v.id} className={v.status !== "active" ? "opacity-60" : ""}>
                    <td>
                      <div className="font-medium">{v.name}</div>
                      <div className="text-xs text-slate-500">{v.service}</div>
                      {v.countries.length > 0 && <div className="text-xs text-slate-500">{v.countries.join(", ")}</div>}
                    </td>
                    <td className="text-sm">{t(`vendors.roles.${v.role}`)}</td>
                    <td className="space-y-1 text-sm">
                      <div>{fmtDate(v.next_review_on)}</div>
                      <DaysChip days={v.days_to_review} done={v.status !== "active"} />
                    </td>
                    <td>
                      <span className={`chip ${LEVEL_STYLE[v.risk_level]}`}>{t(`vendors.risk.${v.risk_level}`)}</span>
                    </td>
                    <td>
                      {v.issues.length === 0 ? (
                        <span className="chip bg-green-50 text-green-800">{t("vendors.ok")}</span>
                      ) : (
                        <ul className="space-y-1">
                          {v.issues.map((i) => (
                            <li key={i} className={`chip ${i === "cross_border" ? "bg-sky-50 text-sky-800" : "bg-amber-50 text-amber-900 ring-1 ring-amber-600/20"}`}>
                              {t(`vendors.issues.${i}`)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className="text-end">
                      {can("governance.write") && (
                        <button
                          className="btn-ghost text-xs"
                          onClick={() =>
                            setEditing({
                              id: v.id,
                              draft: { ...EMPTY, ...toDraft(v), data_categories: v.data_categories.join("\n"), countries: v.countries.join("\n"), dpa_signed_on: v.dpa_signed_on ?? "", due_diligence_on: v.due_diligence_on ?? "", next_review_on: v.next_review_on ?? "" },
                            })
                          }
                        >
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
            if (editing.id) await api.put(`/api/vendors/${editing.id}`, body(d));
            else await api.post("/api/vendors", body(d));
            reload();
          }}
        />
      )}
    </>
  );
}
