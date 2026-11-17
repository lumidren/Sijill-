import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { Card, ErrorBox, PageHeader, Spinner, Unverified } from "../components/ui";
import { useApi } from "../hooks";
import { fmtNum } from "../i18n";

interface Row {
  key: string;
  value: number;
  unit: string;
  env: string;
  verified?: boolean;
}

interface SettingsData {
  version: string;
  organization: { name: string; name_ar?: string; sector?: string; city?: string; dpo?: string } | null;
  legal_defaults: Row[];
  policy: Row[];
  timezone: string;
  catalog: { version: string; requirements: number; unverified: number };
  aws: { profile_configured: boolean; role_configured: boolean };
}

function Table({ rows }: { rows: Row[] }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <thead>
          <tr>
            <th>{t("settings.setting")}</th>
            <th>{t("settings.value")}</th>
            <th>{t("settings.variable")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>
                {t(`settings.keys.${r.key}`)} {r.verified === false && <Unverified />}
              </td>
              <td className="whitespace-nowrap font-medium">
                {fmtNum(r.value)} {t(`settings.units.${r.unit}`)}
              </td>
              <td>
                <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs" dir="ltr">
                  {r.env}
                </code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Settings() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<SettingsData>("/api/settings");
  const [org, setOrg] = useState({ name: "", name_ar: "", sector: "", city: "", dpo: "" });
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    if (data?.organization) setOrg({ name_ar: "", sector: "", city: "", dpo: "", ...data.organization });
  }, [data]);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const canEdit = can("settings.manage");

  async function save(e: FormEvent) {
    e.preventDefault();
    await api.put("/api/settings/organization", org);
    setMsg(t("settings.saved"));
    reload();
  }

  return (
    <>
      <PageHeader title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title={t("settings.organisation")}>
          <form onSubmit={save} className="space-y-3">
            {(
              [
                ["name", t("settings.orgName")],
                ["name_ar", t("settings.orgNameAr")],
                ["sector", t("settings.sector")],
                ["city", t("settings.city")],
                ["dpo", t("settings.dpo")],
              ] as const
            ).map(([k, label]) => (
              <div key={k}>
                <label className="label" htmlFor={`org-${k}`}>
                  {label}
                </label>
                <input id={`org-${k}`} className="input" value={org[k]} onChange={(e) => setOrg({ ...org, [k]: e.target.value })} disabled={!canEdit} required={k === "name"} dir={k === "name_ar" ? "rtl" : undefined} />
              </div>
            ))}
            {canEdit && (
              <button className="btn-primary" disabled={!org.name.trim()}>
                {t("common.save")}
              </button>
            )}
            {msg && (
              <p role="status" className="text-sm text-green-700">
                {msg}
              </p>
            )}
          </form>
        </Card>
        <div className="space-y-5">
          <Card title={t("settings.legal")}>
            <p className="mb-3 text-sm text-slate-600">{t("settings.legalHint")}</p>
            <Table rows={data.legal_defaults} />
          </Card>
          <Card title={t("settings.policy")}>
            <p className="mb-3 text-sm text-slate-600">{t("settings.policyHint")}</p>
            <Table rows={data.policy} />
          </Card>
          <Card title={t("settings.aws")}>
            <p className="text-sm text-slate-700">{data.aws.profile_configured || data.aws.role_configured ? t("settings.awsConfigured") : t("settings.awsNot")}</p>
            <p className="mt-3 text-xs text-slate-500">{t("checks.credentialsNote")}</p>
            <p className="mt-3 text-xs text-slate-500">
              {t("settings.catalogInfo", { version: data.catalog.version, unverified: fmtNum(data.catalog.unverified), total: fmtNum(data.catalog.requirements) })}{" "}
              {t("settings.timezone", { tz: data.timezone })} • v{data.version}
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
