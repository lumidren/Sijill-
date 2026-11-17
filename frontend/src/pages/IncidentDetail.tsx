import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { BreachClock } from "../components/BreachClock";
import { Card, ErrorBox, Spinner } from "../components/ui";
import { useApi, useNow } from "../hooks";
import { fmtDateTime, fmtNum } from "../i18n";
import { bodyFrom, draftFrom, errorText, IncidentFields, type IncidentDraft, type IncidentRow } from "./Incidents";

interface Detail extends IncidentRow {
  events: { id: number; at: string; kind: string; text: string; actor: string }[];
}

interface Notice {
  subject: string;
  body: string;
  note: string;
  missing_fields: number;
}

function NoticePanel({ id, target }: { id: number; target: "regulator" | "individuals" }) {
  const { t, i18n } = useTranslation();
  const [lang, setLang] = useState<"en" | "ar">(i18n.language === "ar" ? "ar" : "en");
  const { data } = useApi<Notice>(`/api/incidents/${id}/notice?target=${target}&lang=${lang}`);
  const [copied, setCopied] = useState(false);
  return (
    <Card
      title={target === "regulator" ? t("incidents.regulatorNotice") : t("incidents.individualsNotice")}
      actions={
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-xs" role="group">
          {(["en", "ar"] as const).map((l) => (
            <button key={l} className={`rounded-md px-2.5 py-1 ${lang === l ? "bg-white shadow-sm" : ""}`} aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
              {l === "en" ? "English" : "العربية"}
            </button>
          ))}
        </div>
      }
    >
      {!data ? (
        <Spinner />
      ) : (
        <>
          {data.missing_fields > 0 && <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{t("incidents.missing", { count: fmtNum(data.missing_fields) })}</p>}
          <div dir={lang === "ar" ? "rtl" : "ltr"} lang={lang} className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
            <p className="mb-2 font-semibold">{data.subject}</p>
            <pre className="font-sans whitespace-pre-wrap text-slate-800">{data.body}</pre>
          </div>
          <p className="mt-2 text-xs text-slate-500">{data.note}</p>
          <div className="mt-3 flex gap-2">
            <button
              className="btn-secondary text-xs"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(`${data.subject}\n\n${data.body}`);
                  setCopied(true);
                } catch {
                  setCopied(false);
                }
              }}
            >
              {copied ? t("incidents.copied") : t("incidents.copy")}
            </button>
            <a className="btn-secondary text-xs" href={`/api/incidents/${id}/notice?target=${target}&lang=${lang}&fmt=pdf`} download>
              {t("incidents.pdf")}
            </a>
          </div>
        </>
      )}
    </Card>
  );
}

export default function IncidentDetail() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { can } = useAuth();
  const canWrite = can("incidents.write");
  const { data, error, loading, reload } = useApi<Detail>(`/api/incidents/${id}`);
  const now = useNow(1000);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("");
  const [notifiedAt, setNotifiedAt] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<IncidentDraft | null>(null);
  useEffect(() => {
    if (data) setStatus(data.status);
  }, [data]);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  const act = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      reload();
    } catch (ex) {
      setErr(errorText(t, ex));
    }
  };

  return (
    <>
      <Link to="/incidents" className="mb-4 inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
        <span aria-hidden className="inline-block rtl:rotate-180">
          ←
        </span>
        {t("incidents.back")}
      </Link>
      <p className="text-sm text-slate-500">
        <span dir="ltr">{data.ref}</span> • {t(`incidents.severities.${data.severity}`)} • {t(`incidents.statuses.${data.status}`)}
      </p>
      <h1 className="page-title mt-1">{data.title}</h1>
      {data.source?.check_id && (
        <p className="mt-1 text-sm text-slate-600">
          {t("incidents.source", { check: data.source.check_id })}{" "}
          {data.source.run_id && (
            <Link to={`/checks/runs/${data.source.run_id}`} className="text-brand-700 hover:underline">
              {t("incidents.viewRun")}
            </Link>
          )}
        </p>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <BreachClock label={t("incidents.clocks.regulator")} clock={data.clocks.regulator} now={now} hours={data.clocks.regulator_hours} />
        <BreachClock label={t("incidents.clocks.individuals")} clock={data.clocks.individuals} now={now} hours={data.clocks.individuals_hours} />
      </div>

      {err && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
          {err}
        </p>
      )}

      {canWrite && (
        <Card className="mt-5">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="label" htmlFor="notified-at">
                {t("incidents.notifiedAt")}
              </label>
              <input id="notified-at" type="datetime-local" className="input" value={notifiedAt} onChange={(e) => setNotifiedAt(e.target.value)} />
            </div>
            {!data.regulator_notified_at && (
              <button className="btn-primary" onClick={() => act(() => api.post(`/api/incidents/${data.id}/notified`, { target: "regulator", at: notifiedAt || null }))}>
                {t("incidents.markRegulator")}
              </button>
            )}
            {!data.individuals_notified_at && data.individuals_notice_needed !== false && (
              <button className="btn-secondary" onClick={() => act(() => api.post(`/api/incidents/${data.id}/notified`, { target: "individuals", at: notifiedAt || null }))}>
                {t("incidents.markIndividuals")}
              </button>
            )}
          </div>
        </Card>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-5">
        <div className="space-y-5 xl:col-span-3">
          <NoticePanel id={data.id} target="regulator" />
          <NoticePanel id={data.id} target="individuals" />
        </div>
        <div className="space-y-5 xl:col-span-2">
          <Card title={t("incidents.timeline")}>
            <ol className="relative space-y-4 border-s border-slate-200 ps-4">
              {data.events.map((e) => (
                <li key={e.id}>
                  <span className="absolute -start-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-brand-600" aria-hidden />
                  <p className="text-xs text-slate-500">
                    {fmtDateTime(e.at)} • {e.actor}
                  </p>
                  <p className="text-sm font-medium">{t(`incidents.kinds.${e.kind}`, { defaultValue: e.kind })}</p>
                  {e.text && !e.kind.startsWith("notified") && <p className="text-sm text-slate-700">{e.text}</p>}
                </li>
              ))}
            </ol>
            {canWrite && (
              <div className="mt-5 space-y-3 border-t border-slate-100 pt-4">
                <label className="label" htmlFor="tl-note">
                  {t("incidents.addNote")}
                </label>
                <textarea id="tl-note" className="input min-h-[64px]" placeholder={t("incidents.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
                <div className="flex flex-wrap gap-2">
                  <button className="btn-secondary" disabled={!note.trim()} onClick={() => act(async () => { await api.post(`/api/incidents/${data.id}/events`, { kind: "note", text: note }); setNote(""); })}>
                    {t("incidents.addNote")}
                  </button>
                  <select aria-label={t("incidents.changeStatus")} className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
                    {(["open", "contained", "notified", "closed"] as const).map((s) => (
                      <option key={s} value={s}>
                        {t(`incidents.statuses.${s}`)}
                      </option>
                    ))}
                  </select>
                  <button className="btn-secondary" disabled={status === data.status} onClick={() => act(() => api.post(`/api/incidents/${data.id}/events`, { kind: "status", status }))}>
                    {t("incidents.changeStatus")}
                  </button>
                </div>
              </div>
            )}
          </Card>
          <Card
            title={t("incidents.details")}
            actions={
              canWrite && !draft && (
                <button className="btn-ghost text-xs" onClick={() => setDraft(draftFrom(data))}>
                  {t("common.edit")}
                </button>
              )
            }
          >
            {draft ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    await api.put(`/api/incidents/${data.id}`, bodyFrom(draft));
                    setDraft(null);
                  });
                }}
              >
                <IncidentFields d={draft} set={setDraft} />
                <div className="mt-4 flex justify-end gap-2">
                  <button type="button" className="btn-secondary" onClick={() => setDraft(null)}>
                    {t("common.cancel")}
                  </button>
                  <button className="btn-primary">{t("common.save")}</button>
                </div>
              </form>
            ) : (
              <dl className="space-y-3 text-sm">
                {[
                  [t("incidents.fields.discovered"), fmtDateTime(data.discovered_at)],
                  [t("incidents.fields.occurred"), fmtDateTime(data.occurred_at)],
                  [t("incidents.fields.description"), data.description],
                  [t("incidents.fields.dataCategories").split(" (")[0], data.data_categories.join(", ")],
                  [t("incidents.fields.affected"), data.affected_count == null ? "—" : fmtNum(data.affected_count)],
                  [t("incidents.fields.systems").split(" (")[0], data.systems.join(", ")],
                  [t("incidents.fields.consequences"), data.likely_consequences],
                  [t("incidents.fields.measures"), data.measures_taken],
                  [t("incidents.fields.contact"), data.contact],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="text-slate-800">{v || "—"}</dd>
                  </div>
                ))}
              </dl>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
