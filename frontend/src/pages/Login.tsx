import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { Disclaimer, LangSwitch } from "../components/AppShell";

export default function Login() {
  const { t } = useTranslation();
  const { login, verifyMfa, setup, needsSetup } = useAuth();
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (needsSetup) await setup(username, displayName, password);
      else if (mfaToken) await verifyMfa(mfaToken, code.replace(/\s/g, ""));
      else {
        const token = await login(username, password);
        if (token) {
          setMfaToken(token);
          setCode("");
        }
      }
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const errCode = err instanceof ApiError ? err.code : "";
      if (mfaToken && errCode === "mfa_token_expired") {
        setMfaToken(null);
        setPassword("");
        setError(t("mfa.expired"));
      } else if (mfaToken && status === 401) setError(t("mfa.invalid"));
      else setError(status === 429 ? t("login.throttled") : status === 422 ? t("errors.validation_error") : status === 401 ? t("login.invalid") : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="grid flex-1 lg:grid-cols-2">
        <div className="relative hidden overflow-hidden bg-brand-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div className="flex items-center gap-3">
            <img src="/favicon.svg" alt="" className="h-10 w-10" />
            <span className="text-lg font-semibold">{t("app.name")}</span>
          </div>
          <div className="relative z-10 max-w-md">
            <h2 className="text-3xl font-semibold leading-tight">{t("app.tagline")}</h2>
            <p className="mt-4 text-brand-100/85">{t("app.audience")}</p>
          </div>
          <div className="text-xs text-brand-200/70">PDPL 151/2020 · OSCAL · Prowler</div>
          <svg aria-hidden className="absolute -bottom-24 -end-24 h-96 w-96 text-brand-700/40" viewBox="0 0 200 200" fill="currentColor">
            <path d="M100 10l70 26v52c0 44-30 80-70 98-40-18-70-54-70-98V36z" />
          </svg>
        </div>
        <div className="flex flex-col">
          <div className="flex justify-end p-4">
            <LangSwitch />
          </div>
          <div className="flex flex-1 items-center justify-center px-6 pb-12">
            <form onSubmit={submit} className="w-full max-w-sm" noValidate>
              <div className="mb-8 lg:hidden">
                <img src="/favicon.svg" alt="" className="mb-3 h-10 w-10" />
                <p className="text-sm text-slate-600">{t("app.tagline")}</p>
              </div>
              <h1 className="text-2xl font-semibold text-ink">{needsSetup ? t("login.setupTitle") : mfaToken ? t("mfa.title") : t("login.title")}</h1>
              <p className="mt-1 mb-6 text-sm text-slate-600">{needsSetup ? t("login.setupSubtitle") : mfaToken ? t("mfa.prompt") : t("login.subtitle")}</p>
              {error && (
                <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                  {error}
                </div>
              )}
              {mfaToken ? (
                <>
                  <div className="mb-6">
                    <label className="label" htmlFor="mfa-code">
                      {t("mfa.code")}
                    </label>
                    <input
                      id="mfa-code"
                      className="input text-center font-mono text-lg tracking-[0.4em]"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={7}
                      autoFocus
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      aria-describedby="mfa-prompt"
                      dir="ltr"
                    />
                    <p id="mfa-prompt" className="mt-1 text-xs text-slate-500">
                      {t("mfa.prompt")}
                    </p>
                  </div>
                  <button type="submit" className="btn-primary w-full py-2.5" disabled={busy || code.replace(/\s/g, "").length !== 6}>
                    {t("mfa.verify")}
                  </button>
                  <button type="button" className="btn-ghost mt-2 w-full" onClick={() => { setMfaToken(null); setError(null); }}>
                    {t("common.cancel")}
                  </button>
                </>
              ) : (
              <>
              {needsSetup && (
                <div className="mb-4">
                  <label className="label" htmlFor="displayName">
                    {t("login.displayName")}
                  </label>
                  <input id="displayName" className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
                </div>
              )}
              <div className="mb-4">
                <label className="label" htmlFor="username">
                  {t("login.username")}
                </label>
                <input id="username" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required dir="ltr" />
              </div>
              <div className="mb-6">
                <label className="label" htmlFor="password">
                  {t("login.password")}
                </label>
                <input
                  id="password"
                  type="password"
                  className="input"
                  autoComplete={needsSetup ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  aria-describedby={needsSetup ? "pwhint" : undefined}
                  dir="ltr"
                />
                {needsSetup && (
                  <p id="pwhint" className="mt-1 text-xs text-slate-500">
                    {t("login.passwordHint")}
                  </p>
                )}
              </div>
              <button type="submit" className="btn-primary w-full py-2.5" disabled={busy || !username || !password}>
                {needsSetup ? t("login.setupSubmit") : t("login.submit")}
              </button>
              {!needsSetup && <p className="mt-6 text-xs text-slate-500">{t("login.demoHint")}</p>}
              </>
              )}
            </form>
          </div>
        </div>
      </div>
      <Disclaimer />
    </div>
  );
}
