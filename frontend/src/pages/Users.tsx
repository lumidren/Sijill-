import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth, type Role, type User } from "../auth";
import { Card, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDateTime } from "../i18n";

type Row = User & { is_active: boolean; last_login_at: string | null };
const ROLES: Role[] = ["admin", "dpo", "it", "auditor"];

export default function Users() {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const { data, error, loading, reload } = useApi<Row[]>("/api/users");
  const [form, setForm] = useState({ username: "", display_name: "", password: "", role: "dpo" as Role });
  const [msg, setMsg] = useState<string | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setFormErr(null);
    try {
      await api.post("/api/users", form);
      setForm({ username: "", display_name: "", password: "", role: "dpo" });
      setMsg(t("users.created"));
      reload();
    } catch (err) {
      setFormErr(err instanceof ApiError ? t(`errors.${err.code}`, { defaultValue: t("common.error") }) : t("common.error"));
    }
  }

  async function resetMfa(u: Row) {
    await api.post(`/api/users/${u.id}/mfa/reset`, {});
    reload();
  }

  async function toggle(u: Row) {
    await api.patch(`/api/users/${u.id}`, { is_active: !u.is_active });
    reload();
  }

  return (
    <>
      <PageHeader title={t("users.title")} subtitle={t("users.subtitle")} />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <ErrorBox error={error} onRetry={reload} />
          {loading && !data ? (
            <Spinner />
          ) : (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>{t("users.name")}</th>
                    <th>{t("users.role")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("mfa.column")}</th>
                    <th>{t("users.lastLogin")}</th>
                    <th>
                      <span className="sr-only">{t("common.actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data?.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <div className="font-medium">{u.display_name}</div>
                        <div className="text-xs text-slate-500" dir="ltr">
                          {u.username}
                        </div>
                      </td>
                      <td>{t(`roles.${u.role}`)}</td>
                      <td>{u.is_active ? t("users.active") : <span className="text-slate-500">{t("users.inactive")}</span>}</td>
                      <td>{u.mfa_enabled ? <span className="chip bg-green-50 text-green-800">{t("mfa.on")}</span> : <span className="text-slate-500">{t("mfa.off")}</span>}</td>
                      <td className="text-slate-600">{fmtDateTime(u.last_login_at)}</td>
                      <td className="whitespace-nowrap text-end">
                        {u.mfa_enabled && u.id !== me?.id && (
                          <button className="btn-ghost text-xs" onClick={() => resetMfa(u)}>
                            {t("mfa.reset")}
                          </button>
                        )}
                        {u.id !== me?.id && (
                          <button className="btn-ghost text-xs" onClick={() => toggle(u)}>
                            {u.is_active ? t("users.deactivate") : t("users.activate")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title={t("users.add")}>
          <form onSubmit={create} className="space-y-3">
            {formErr && (
              <p role="alert" className="text-sm text-red-700">
                {formErr}
              </p>
            )}
            {msg && (
              <p role="status" className="text-sm text-green-700">
                {msg}
              </p>
            )}
            <div>
              <label className="label" htmlFor="nu-name">
                {t("users.name")}
              </label>
              <input id="nu-name" className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required />
            </div>
            <div>
              <label className="label" htmlFor="nu-user">
                {t("users.username")}
              </label>
              <input id="nu-user" className="input" dir="ltr" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
            </div>
            <div>
              <label className="label" htmlFor="nu-role">
                {t("users.role")}
              </label>
              <select id="nu-role" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`roles.${r}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="nu-pw">
                {t("users.password")}
              </label>
              <input id="nu-pw" type="password" className="input" dir="ltr" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={10} aria-describedby="nu-pw-hint" />
              <p id="nu-pw-hint" className="mt-1 text-xs text-slate-500">
                {t("login.passwordHint")}
              </p>
            </div>
            <button className="btn-primary w-full" type="submit">
              {t("common.create")}
            </button>
          </form>
        </Card>
      </div>
    </>
  );
}
