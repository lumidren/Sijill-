import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate } from "../i18n";

export interface Activity {
  id: number;
  ref: string;
  role: "controller" | "processor";
  name: string;
  purpose: string;
  lawful_basis: string;
  data_subjects: string[];
  data_categories: string[];
  sensitive_categories: string[];
  source: string;
  recipients: string[];
  cross_border: boolean;
  transfer_countries: string[];
  transfer_safeguards: string;
  retention: string;
  security_measures: string;
  systems: string[];
  client_name: string;
  owner: string;
  status: "active" | "archived";
  updated_at: string;
  issues: string[];
}

type Draft = Omit<Activity, "id" | "ref" | "status" | "updated_at" | "issues">;
const LIST_FIELDS = ["data_subjects", "data_categories", "sensitive_categories", "recipients", "transfer_countries", "systems"] as const;
const EMPTY: Draft = {
  role: "controller", name: "", purpose: "", lawful_basis: "", data_subjects: [], data_categories: [], sensitive_categories: [],
  source: "", recipients: [], cross_border: false, transfer_countries: [], transfer_safeguards: "", retention: "",
  security_measures: "", systems: [], client_name: "", owner: "",
};

function ActivityForm({ initial, id, onClose, onSaved }: { initial: Draft; id: number | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [d, setD] = useState<Draft>(initial);
  const [lists, setLists] = useState<Record<string, string>>(Object.fromEntries(LIST_FIELDS.map((k) => [k, initial[k].join("\n")])));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD({ ...d, [k]: v });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const body = { ...d, ...Object.fromEntries(LIST_FIELDS.map((k) => [k, lists[k].split("\n").map((s) => s.trim()).filter(Boolean)])) };
    try {
      if (id) await api.put(`/api/register/${id}`, body);
      else await api.post("/api/register", body);
      onSaved();
      onClose();
    } catch (ex) {
      setErr(ex instanceof ApiError && ex.status === 422 ? t("errors.validation_error") : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  const text = (k: keyof Draft, label: string, area = false, hint?: string) => (
    <div>
      <label className="label" htmlFor={`f-${k}`}>
        {label}
      </label>
      {area ? (
        <textarea id={`f-${k}`} className="input min-h-[64px]" value={d[k] as string} onChange={(e) => set(k, e.target.value as never)} maxLength={4000} />
      ) : (
        <input
          id={`f-${k}`}
          className="input"
          value={d[k] as string}
          onChange={(e) => set(k, e.target.value as never)}
          maxLength={255}
          required={k === "name"}
          autoFocus={k === "name"}
          aria-describedby={hint ? `h-${k}` : undefined}
        />
      )}
      {hint && (
        <p id={`h-${k}`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
    </div>
  );
  const list = (k: (typeof LIST_FIELDS)[number], label: string) => (
    <div>
      <label className="label" htmlFor={`f-${k}`}>
        {label}
      </label>
      <textarea id={`f-${k}`} className="input min-h-[64px]" value={lists[k]} onChange={(e) => setLists({ ...lists, [k]: e.target.value })} />
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-900/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="form-title"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <form onSubmit={submit} className="flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 id="form-title" className="text-lg font-semibold">
            {id ? t("register.edit") : t("register.add")}
          </h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t("common.close")}
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          <fieldset>
            <legend className="label">{t("register.roleLabel")}</legend>
            <div className="flex flex-wrap gap-3">
              {(["controller", "processor"] as const).map((r) => (
                <label key={r} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${d.role === r ? "border-brand-500 bg-brand-50" : "border-slate-200"}`}>
                  <input type="radio" name="role" checked={d.role === r} onChange={() => set("role", r)} className="accent-brand-700" />
                  {t(`register.${r}`)}
                </label>
              ))}
            </div>
          </fieldset>
          {text("name", t("register.name"))}
          {d.role === "processor" && text("client_name", t("register.client"))}
          {text("purpose", t("register.purpose"), true)}
          {d.role === "controller" && text("lawful_basis", t("register.lawfulBasis"), false, t("register.lawfulBasisHint"))}
          <div className="grid gap-4 sm:grid-cols-2">
            {list("data_subjects", t("register.dataSubjects"))}
            {list("data_categories", t("register.dataCategories"))}
            {list("sensitive_categories", t("register.sensitive"))}
            {list("recipients", t("register.recipients"))}
          </div>
          {text("source", t("register.source"))}
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" checked={d.cross_border} onChange={(e) => set("cross_border", e.target.checked)} className="h-4 w-4 accent-brand-700" />
            {t("register.crossBorder")}
          </label>
          {d.cross_border && (
            <div className="grid gap-4 sm:grid-cols-2">
              {list("transfer_countries", t("register.countries"))}
              {text("transfer_safeguards", t("register.safeguards"), true)}
            </div>
          )}
          {text("retention", t("register.retention"))}
          {text("security_measures", t("register.security"), true)}
          <div className="grid gap-4 sm:grid-cols-2">
            {list("systems", t("register.systems"))}
            {text("owner", t("register.owner"))}
          </div>
          {err && (
            <p role="alert" className="text-sm text-red-700">
              {err}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <button type="button" className="btn-secondary" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button className="btn-primary" disabled={busy || !d.name.trim()}>
            {busy ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Register() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [archived, setArchived] = useState(false);
  const { data, error, loading, reload } = useApi<Activity[]>(`/api/register${archived ? "?include_archived=true" : ""}`);
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const canEdit = can("register.write");

  return (
    <>
      <PageHeader
        title={t("register.title")}
        subtitle={t("register.subtitle")}
        actions={
          canEdit && (
            <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>
              + {t("register.add")}
            </button>
          )
        }
      />
      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-slate-700">{t("register.exports")}:</span>
          <a className="btn-secondary text-xs" href="/api/register/export?role=controller&fmt=csv" download>
            {t("register.controllerCsv")}
          </a>
          <a className="btn-secondary text-xs" href="/api/register/export?role=controller&fmt=pdf&lang=en" download>
            {t("register.controllerPdf")} (EN)
          </a>
          <a className="btn-secondary text-xs" href="/api/register/export?role=controller&fmt=pdf&lang=ar" download>
            {t("register.controllerPdf")} (AR)
          </a>
          <a className="btn-secondary text-xs" href="/api/register/export?role=processor&fmt=csv" download>
            {t("register.processorCsv")}
          </a>
          <label className="ms-auto flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} className="accent-brand-700" />
            {t("register.showArchived")}
          </label>
        </div>
        <p className="mt-2 text-xs text-slate-500">{t("register.templateNote")}</p>
      </Card>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : !data?.length ? (
        <EmptyState title={t("register.empty")} hint={t("register.emptyHint")} />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>{t("register.ref")}</th>
                  <th>{t("register.name")}</th>
                  <th>{t("register.dataSubjects").split(" (")[0]}</th>
                  <th>{t("register.crossBorder")}</th>
                  <th>{t("register.retention")}</th>
                  <th>{t("register.issuesTitle")}</th>
                  <th>
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id} className={a.status === "archived" ? "opacity-60" : ""}>
                    <td className="whitespace-nowrap font-mono text-xs text-slate-500">{a.ref}</td>
                    <td>
                      <div className="font-medium">{a.name}</div>
                      <div className="text-xs text-slate-500">
                        {t(`register.${a.role}`)} · {fmtDate(a.updated_at)}
                      </div>
                      {a.sensitive_categories.length > 0 && <span className="chip mt-1 bg-violet-50 text-violet-800">{a.sensitive_categories.join(", ")}</span>}
                    </td>
                    <td className="text-sm text-slate-700">{a.data_subjects.join(", ")}</td>
                    <td className="text-sm">{a.cross_border ? `${t("register.yes")} · ${a.transfer_countries.join(", ")}` : t("register.no")}</td>
                    <td className="text-sm text-slate-700">{a.retention || "—"}</td>
                    <td>
                      {a.issues.length === 0 ? (
                        <span className="chip bg-green-50 text-green-800">{t("register.complete")}</span>
                      ) : (
                        <ul className="space-y-1">
                          {a.issues.map((i) => (
                            <li key={i} className="chip bg-amber-50 text-amber-900 ring-1 ring-amber-600/20">
                              {t(`register.issues.${i}`)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-end">
                      {canEdit && (
                        <>
                          <button className="btn-ghost text-xs" onClick={() => setEditing({ id: a.id, draft: { ...EMPTY, ...a } })}>
                            {t("common.edit")}
                          </button>
                          <button
                            className="btn-ghost text-xs"
                            onClick={async () => {
                              await api.post(`/api/register/${a.id}/archive`);
                              reload();
                            }}
                          >
                            {a.status === "archived" ? t("register.restore") : t("register.archive")}
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {editing && <ActivityForm initial={editing.draft} id={editing.id} onClose={() => setEditing(null)} onSaved={reload} />}
    </>
  );
}
