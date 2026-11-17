import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { Disclaimer, LangSwitch } from "../components/AppShell";
import { Spinner } from "../components/ui";
import { fmtDate, fmtNum, pick } from "../i18n";
import type { Bi } from "../types";

interface PFile { id: number; filename: string; size: number; uploaded_at: string }
interface PItem { id: number; requirement_id: string; label: string; title: Bi; question: Bi; ask: string; response: string; status: string; review_note: string; files: PFile[] }
interface PView {
  organization: { name: string; name_ar: string };
  title: string; recipient: string; message: string; status: string; expires_at: string;
  max_upload_mb: number; files_per_item: number; items: PItem[];
}

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.csv,.json";

function Item({ token, item, max, perItem, locked, onChange }: { token: string; item: PItem; max: number; perItem: number; locked: boolean; onChange: (i: PItem) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState(item.response);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [fileMsg, setFileMsg] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const base = `/api/public/r/${token}/items/${item.id}`;
  const done = locked || item.status === "accepted";

  async function save() {
    setState("saving");
    try {
      onChange(await api.put<PItem>(base, { response: text }));
      setState("saved");
    } catch {
      setState("error");
    }
  }

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      onChange(await api.post<PItem>(`${base}/files`, fd));
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "error";
      setFileMsg(t(`pr.fileErrors.${code}`, { defaultValue: t("common.error"), mb: fmtNum(max), n: fmtNum(perItem) }));
    } finally {
      if (input.current) input.current.value = "";
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby={`q-${item.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 id={`q-${item.id}`} className="font-semibold">
          <span className="font-mono text-xs text-slate-500" dir="ltr">{item.label}</span> {pick(item.title)}
        </h2>
        {item.status === "accepted" && <span className="chip bg-green-50 text-green-800">{t("pr.accepted")}</span>}
      </div>
      <p className="mt-2 text-sm text-slate-700">{pick(item.question)}</p>
      {item.ask && (
        <p className="mt-2 rounded-lg bg-brand-50 p-2 text-sm text-brand-900">
          {t("pr.consultantAsks")}: {item.ask}
        </p>
      )}
      {item.status === "returned" && item.review_note && (
        <p className="mt-2 rounded-lg bg-amber-50 p-2 text-sm text-amber-900" role="note">
          {t("pr.returned")}: {item.review_note}
        </p>
      )}
      <label className="label mt-4" htmlFor={`a-${item.id}`}>
        {t("pr.yourAnswer")}
      </label>
      <textarea
        id={`a-${item.id}`}
        className="input min-h-[90px]"
        maxLength={5000}
        value={text}
        disabled={done}
        onChange={(e) => {
          setText(e.target.value);
          setState("idle");
        }}
      />
      {!done && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button type="button" className="btn-secondary text-sm" disabled={state === "saving" || text === item.response} onClick={save}>
            {state === "saving" ? t("pr.saving") : t("pr.save")}
          </button>
          <label className={`btn-ghost cursor-pointer text-sm ${item.files.length >= perItem ? "pointer-events-none opacity-50" : ""}`}>
            {t("pr.attach")}
            <input ref={input} type="file" className="sr-only" accept={ACCEPT} onChange={onFile} aria-describedby={`f-hint-${item.id}`} />
          </label>
          <span role="status" className="text-xs">
            {state === "saved" && <span className="text-green-700">{t("pr.saved")}</span>}
            {state === "error" && <span className="text-red-700">{t("common.error")}</span>}
          </span>
        </div>
      )}
      <p id={`f-hint-${item.id}`} className="mt-1 text-xs text-slate-500">
        {t("pr.fileHint", { mb: fmtNum(max), n: fmtNum(perItem) })}
      </p>
      {fileMsg && (
        <p role="alert" className="mt-1 text-sm text-red-700">
          {fileMsg}
        </p>
      )}
      {item.files.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {item.files.map((f) => (
            <li key={f.id} className="flex items-center gap-2">
              <span>{f.filename}</span>
              <span className="text-xs text-slate-500">{fmtNum(Math.ceil(f.size / 1024))} KB</span>
              {!done && (
                <button
                  type="button"
                  className="text-xs text-red-700 hover:underline"
                  aria-label={`${t("pr.remove")}: ${f.filename}`}
                  onClick={async () => onChange(await api.del<PItem>(`${base}/files/${f.id}`))}
                >
                  {t("pr.remove")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The page client staff open from the link. No account, no navigation, nothing else of the install. */
export default function PublicRequest() {
  const { t, i18n } = useTranslation();
  const { token = "" } = useParams();
  const [view, setView] = useState<PView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<PView>(`/api/public/r/${token}`)
      .then((v) => {
        setView(v);
        setSubmitted(v.status === "submitted");
      })
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, [token]);

  const answered = view?.items.filter((i) => i.status === "answered" || i.status === "accepted").length ?? 0;
  const org = view ? (i18n.language === "ar" && view.organization.name_ar) || view.organization.name : "";

  return (
    <div className="flex min-h-full flex-col bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 sm:px-8">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="font-semibold">{t("app.name")}</span>
        </div>
        <LangSwitch />
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        {error ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6" role="alert">
            <h1 className="text-lg font-semibold">{t(`pr.errors.${error}`, { defaultValue: t("pr.errors.link_not_found") })}</h1>
            <p className="mt-2 text-sm text-slate-600">{t("pr.askForNew")}</p>
          </div>
        ) : !view ? (
          <Spinner />
        ) : (
          <>
            <p className="text-sm text-slate-500">{org}</p>
            <h1 className="mt-1 text-2xl font-semibold">{view.title}</h1>
            <p className="mt-2 text-sm text-slate-600">
              {t("pr.for", { name: view.recipient })} · {t("pr.until", { when: fmtDate(view.expires_at) })}
            </p>
            {view.message && <p className="mt-4 whitespace-pre-line rounded-xl bg-white p-4 text-sm shadow-sm">{view.message}</p>}
            <p className="mt-4 text-xs text-slate-500">{t("pr.privacy")}</p>
            {submitted && (
              <div className="mt-6 rounded-2xl bg-green-50 p-5 text-green-900" role="status">
                <h2 className="font-semibold">{t("pr.thanks")}</h2>
                <p className="mt-1 text-sm">{t("pr.thanksBody")}</p>
              </div>
            )}
            <div className="mt-6 space-y-4">
              {view.items.map((i) => (
                <Item
                  key={i.id}
                  token={token}
                  item={i}
                  max={view.max_upload_mb}
                  perItem={view.files_per_item}
                  locked={submitted}
                  onChange={(n) => setView({ ...view, items: view.items.map((x) => (x.id === n.id ? n : x)) })}
                />
              ))}
            </div>
            {!submitted && (
              <div className="sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-lg">
                <span className="text-sm text-slate-600">{t("pr.progress", { done: fmtNum(answered), total: fmtNum(view.items.length) })}</span>
                <button
                  className="btn-primary"
                  disabled={busy || answered === 0}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api.post(`/api/public/r/${token}/submit`);
                      setSubmitted(true);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {t("pr.submit")}
                </button>
              </div>
            )}
          </>
        )}
      </main>
      <Disclaimer />
    </div>
  );
}
