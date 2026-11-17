import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { RecordForm, type Draft } from "../components/RecordForm";
import { Card, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtNum, fmtPct } from "../i18n";
import { useOrg, type Org } from "../org";

export interface ClientRow extends Org {
  overall: number | null;
  counts: { total: number; by_basis: Record<string, number>; by_status: Record<string, number> };
  gaps: number;
  risks_high: number;
  tasks_overdue: number;
  requests_overdue: number;
  vendors_without_dpa: number;
  open_breaches: number;
  last_run: string | null;
}

const BASIS = [
  { key: "automated", className: "bg-sky-500" },
  { key: "attested", className: "bg-violet-500" },
  { key: "not_assessed", className: "bg-slate-300" },
];

function EvidenceBar({ row }: { row: ClientRow }) {
  const { t } = useTranslation();
  const total = row.counts.total || 1;
  const label = BASIS.map((b) => `${t(`basis.${b.key}`)}: ${fmtNum(row.counts.by_basis[b.key] ?? 0)}`).join(", ");
  return (
    <div className="min-w-[9rem]" role="img" aria-label={label} title={label}>
      <div className="flex h-2 overflow-hidden rounded-full bg-slate-100">
        {BASIS.map((b) => (
          <div key={b.key} className={b.className} style={{ width: `${((row.counts.by_basis[b.key] ?? 0) / total) * 100}%` }} />
        ))}
      </div>
      <div className="mt-1 text-[11px] text-slate-500">
        {fmtNum(row.counts.by_basis.automated ?? 0)} · {fmtNum(row.counts.by_basis.attested ?? 0)} · {fmtNum(row.counts.by_basis.not_assessed ?? 0)}
      </div>
    </div>
  );
}

function Count({ n, warn }: { n: number; warn?: boolean }) {
  return <span className={n > 0 && warn ? "font-semibold text-red-700" : n > 0 ? "font-medium" : "text-slate-400"}>{fmtNum(n)}</span>;
}

export default function Clients() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { current, select, reload: reloadOrgs } = useOrg();
  const { data, error, loading, reload } = useApi<{ current: number; items: ClientRow[] }>("/api/orgs/overview");
  const archived = useApi<Org[]>(can("orgs.manage") ? "/api/orgs/all" : null);
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const refresh = () => {
    reload();
    archived.reload();
    reloadOrgs();
  };
  const patch = async (id: number, body: object) => {
    await api.patch(`/api/orgs/${id}`, body);
    refresh();
  };
  const hidden = (archived.data ?? []).filter((o) => o.archived);
  const here = data?.current ?? current; // the server decides which organisation is open

  return (
    <>
      <PageHeader
        title={t("orgs.title")}
        subtitle={t("orgs.subtitle")}
        actions={can("orgs.manage") && <button className="btn-primary" onClick={() => setEditing({ id: null, draft: { name: "", sector: "" } })}>+ {t("orgs.add")}</button>}
      />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>{t("orgs.organisation")}</th>
                  <th>{t("orgs.readiness")}</th>
                  <th>{t("orgs.evidence")}</th>
                  <th className="text-end">{t("orgs.gaps")}</th>
                  <th className="text-end">{t("orgs.highRisks")}</th>
                  <th className="text-end">{t("orgs.overdue")}</th>
                  <th className="text-end">{t("orgs.noContract")}</th>
                  <th className="text-end">{t("orgs.breaches")}</th>
                  <th>{t("orgs.lastCheck")}</th>
                  <th>
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((o) => (
                  <tr key={o.id} className={o.id === here ? "bg-brand-50/50" : ""}>
                    <td>
                      <div className="font-medium">{o.name}</div>
                      {o.id === here && <div className="text-xs text-brand-700">{t("orgs.openNow")}</div>}
                      {can("orgs.manage") && (
                        <div className="mt-0.5 flex gap-3 text-xs">
                          <button className="text-brand-700 hover:underline" onClick={() => setEditing({ id: o.id, draft: { name: o.name } })} aria-label={`${t("orgs.rename")}: ${o.name}`}>
                            {t("orgs.rename")}
                          </button>
                          {data!.items.length > 1 && (
                            <button className="text-slate-500 hover:underline" onClick={() => patch(o.id, { archived: true })} aria-label={`${t("orgs.archive")}: ${o.name}`}>
                              {t("orgs.archive")}
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="text-lg font-semibold">{o.overall == null ? <span className="text-sm text-slate-400">—</span> : fmtPct(o.overall)}</td>
                    <td>
                      <EvidenceBar row={o} />
                    </td>
                    <td className="text-end">
                      <Count n={o.gaps} />
                    </td>
                    <td className="text-end">
                      <Count n={o.risks_high} warn />
                    </td>
                    <td className="text-end">
                      <Count n={o.tasks_overdue + o.requests_overdue} warn />
                    </td>
                    <td className="text-end">
                      <Count n={o.vendors_without_dpa} warn />
                    </td>
                    <td className="text-end">
                      <Count n={o.open_breaches} warn />
                    </td>
                    <td className="whitespace-nowrap text-sm text-slate-600">{o.last_run ? fmtDate(o.last_run) : <span className="text-slate-400">{t("orgs.none")}</span>}</td>
                    <td className="whitespace-nowrap text-end">
                      <button className="btn-secondary text-xs" onClick={() => select(o.id, "/")} aria-label={`${t("orgs.open")}: ${o.name}`}>
                        {t("orgs.open")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-xs text-slate-500">{t("orgs.legend")}</p>
        </Card>
      )}
      {hidden.length > 0 && (
        <Card title={t("orgs.archived")} className="mt-6">
          <ul className="divide-y divide-slate-100">
            {hidden.map((o) => (
              <li key={o.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-slate-600">{o.name}</span>
                <button className="btn-ghost text-xs" onClick={() => patch(o.id, { archived: false })}>
                  {t("orgs.restore")}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {editing && (
        <RecordForm
          title={editing.id ? t("orgs.rename") : t("orgs.add")}
          fields={[
            { key: "name", label: t("orgs.name"), required: true },
            ...(editing.id ? [] : [{ key: "sector", label: t("orgs.sector"), hint: t("orgs.addHint") }]),
          ]}
          initial={editing.draft}
          onClose={() => setEditing(null)}
          onSubmit={async (d) => {
            if (editing.id) await api.patch(`/api/orgs/${editing.id}`, { name: d.name });
            else await api.post("/api/orgs", { name: d.name, sector: d.sector });
            refresh();
          }}
        />
      )}
    </>
  );
}
