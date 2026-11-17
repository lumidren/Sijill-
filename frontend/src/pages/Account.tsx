import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import QRCode from "qrcode";
import { api, ApiError } from "../api";
import { useAuth, type User } from "../auth";
import { Card, PageHeader } from "../components/ui";

function CodeInput({ value, onChange, describedBy }: { value: string; onChange: (v: string) => void; describedBy?: string }) {
  const { t } = useTranslation();
  return (
    <>
      <label className="label" htmlFor="account-code">
        {t("mfa.code")}
      </label>
      <input
        id="account-code"
        className="input max-w-[12rem] text-center font-mono text-lg tracking-[0.4em]"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={7}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={describedBy}
        dir="ltr"
      />
    </>
  );
}

export default function Account() {
  const { t } = useTranslation();
  const { user, setUser } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const enabled = !!user?.mfa_enabled;

  useEffect(() => {
    if (!setup) return setQr(null);
    QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 192 })
      .then(setQr)
      .catch(() => setQr(null));
  }, [setup]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError && e.code === "invalid_code" ? t("mfa.invalid") : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  const clean = code.replace(/\s/g, "");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const me = await api.post<User>(enabled ? "/api/auth/mfa/disable" : "/api/auth/mfa/enable", { code: clean });
      setUser(me);
      setSetup(null);
      setCode("");
    });
  };

  if (!user) return null;
  return (
    <>
      <PageHeader title={t("nav.account")} subtitle={`${user.display_name} · ${t(`roles.${user.role}`)}`} />
      <Card title={t("mfa.title")}>
        <p className="text-sm text-slate-600">{t("mfa.subtitle")}</p>
        <p className={`mt-3 inline-block chip ${enabled ? "bg-green-50 text-green-800 ring-1 ring-green-600/20" : "bg-amber-50 text-amber-900"}`} role="status">
          {enabled ? t("mfa.enabled") : t("mfa.disabled")}
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {error}
          </p>
        )}

        {!enabled && !setup && (
          <div className="mt-4">
            <button className="btn-primary" disabled={busy} onClick={() => run(async () => setSetup(await api.post("/api/auth/mfa/setup", {})))}>
              {t("mfa.start")}
            </button>
          </div>
        )}

        {!enabled && setup && (
          <form onSubmit={submit} className="mt-5 space-y-5">
            <div>
              <p className="text-sm font-medium">1. {t("mfa.step1")}</p>
              <div className="mt-3 flex flex-wrap items-center gap-5">
                {qr && <img src={qr} alt={t("mfa.step1")} className="h-48 w-48 rounded-lg border border-slate-200" />}
                <div>
                  <div className="text-xs text-slate-500">{t("mfa.key")}</div>
                  <code className="mt-1 block break-all rounded bg-slate-100 px-2 py-1 font-mono text-sm" dir="ltr">
                    {setup.secret.replace(/(.{4})/g, "$1 ").trim()}
                  </code>
                </div>
              </div>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">2. {t("mfa.step2")}</p>
              <CodeInput value={code} onChange={setCode} />
            </div>
            <div className="flex gap-2">
              <button className="btn-primary" disabled={busy || clean.length !== 6}>
                {t("mfa.confirm")}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setSetup(null)}>
                {t("common.cancel")}
              </button>
            </div>
          </form>
        )}

        {enabled && (
          <form onSubmit={submit} className="mt-5 space-y-3">
            <p id="off-hint" className="text-sm text-slate-600">
              {t("mfa.turnOffHint")}
            </p>
            <CodeInput value={code} onChange={setCode} describedBy="off-hint" />
            <div>
              <button className="btn-secondary" disabled={busy || clean.length !== 6}>
                {t("mfa.turnOff")}
              </button>
            </div>
          </form>
        )}
      </Card>
    </>
  );
}
