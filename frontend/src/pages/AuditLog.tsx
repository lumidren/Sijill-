import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDateTime, fmtNum } from "../i18n";

interface Entry {
  id: number;
  at: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  detail: Record<string, unknown>;
}

const PAGE = 50;

export default function AuditLog() {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi<{ total: number; items: Entry[] }>(`/api/audit?limit=${PAGE}&offset=${offset}`);
  const [verify, setVerify] = useState<{ ok: boolean; first_bad_id: number | null } | null>(null);

  return (
    <>
      <PageHeader
        title={t("audit.title")}
        subtitle={t("audit.subtitle")}
        actions={
          <button className="btn-secondary" onClick={async () => setVerify(await api.get("/api/audit/verify"))}>
            {t("audit.verify")}
          </button>
        }
      />
      {verify && (
        <div role="status" className={`mb-4 rounded-xl border px-4 py-3 text-sm ${verify.ok ? "border-green-200 bg-green-50 text-green-800" : "border-red-200 bg-red-50 text-red-800"}`}>
          {verify.ok ? t("audit.verified") : t("audit.broken", { id: verify.first_bad_id })}
        </div>
      )}
      <Card>
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? (
          <Spinner />
        ) : !data?.items.length ? (
          <EmptyState title={t("audit.empty")} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{t("audit.when")}</th>
                    <th>{t("audit.who")}</th>
                    <th>{t("audit.action")}</th>
                    <th>{t("audit.entity")}</th>
                    <th>{t("common.details")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((e) => (
                    <tr key={e.id}>
                      <td className="text-slate-500">{fmtNum(e.id)}</td>
                      <td className="whitespace-nowrap">{fmtDateTime(e.at)}</td>
                      <td dir="ltr" className="text-start">{e.actor}</td>
                      <td>
                        <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs" dir="ltr">
                          {e.action}
                        </code>
                      </td>
                      <td className="text-slate-600" dir="ltr">
                        {e.entity_type}
                        {e.entity_id ? ` · ${e.entity_id}` : ""}
                      </td>
                      <td className="max-w-xs truncate text-xs text-slate-500" dir="ltr" title={JSON.stringify(e.detail)}>
                        {Object.keys(e.detail || {}).length ? JSON.stringify(e.detail) : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
              <span>
                {fmtNum(offset + 1)}–{fmtNum(Math.min(offset + PAGE, data.total))} {t("common.of")} {fmtNum(data.total)}
              </span>
              <div className="flex gap-2">
                <button className="btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  ‹
                </button>
                <button className="btn-secondary" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                  ›
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
