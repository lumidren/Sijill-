import { useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Card, PageHeader } from "../components/ui";
import { fmtNum } from "../i18n";

function DocIcon({ kind }: { kind: "pdf" | "data" | "list" }) {
  const d =
    kind === "pdf"
      ? "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6M8 13h8M8 17h5"
      : kind === "list"
        ? "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"
        : "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6";
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700" aria-hidden>
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d={d} />
      </svg>
    </span>
  );
}

function Dl({ href, children, primary }: { href: string; children: ReactNode; primary?: boolean }) {
  return (
    <a href={href} className={primary ? "btn-primary" : "btn-secondary"} download>
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <path d="M12 4v12m0 0 5-5m-5 5-5-5M4 20h16" />
      </svg>
      {children}
    </a>
  );
}

function ReportCard({ icon, title, desc, children }: { icon: "pdf" | "data" | "list"; title: string; desc: string; children: ReactNode }) {
  return (
    <Card>
      <div className="flex gap-4">
        <DocIcon kind={icon} />
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-slate-600">{desc}</p>
          <div className="mt-4 flex flex-wrap gap-2">{children}</div>
        </div>
      </div>
    </Card>
  );
}

function OscalImport() {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.post<{ runs: number; results: number }>("/api/reports/oscal/assessment-results/import", fd);
      setMsg({ ok: true, text: t("reports.importDone", { runs: fmtNum(r.runs), results: fmtNum(r.results) }) });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "error";
      setMsg({ ok: false, text: t(`checks.errors.${code}`, { defaultValue: t("common.error") }) });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <ReportCard icon="data" title={t("reports.importTitle")} desc={t("reports.importDesc")}>
      <label className={`btn-secondary cursor-pointer ${busy ? "pointer-events-none opacity-60" : ""}`}>
        {busy ? t("checks.importing") : t("checks.chooseFile")}
        <input ref={input} type="file" accept=".json,application/json" className="sr-only" onChange={onFile} />
      </label>
      {msg && (
        <p role={msg.ok ? "status" : "alert"} className={`w-full text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>
          {msg.text}
        </p>
      )}
    </ReportCard>
  );
}

export default function Reports() {
  const { t } = useTranslation();
  const { can } = useAuth();
  return (
    <>
      <PageHeader title={t("reports.title")} subtitle={t("reports.subtitle")} />
      <div className="grid gap-5 lg:grid-cols-2">
        <ReportCard icon="pdf" title={t("reports.compliance")} desc={t("reports.complianceDesc")}>
          <Dl href="/api/reports/readiness.pdf?lang=en" primary>
            {t("reports.pdfEn")}
          </Dl>
          <Dl href="/api/reports/readiness.pdf?lang=ar" primary>
            {t("reports.pdfAr")}
          </Dl>
        </ReportCard>
        <ReportCard icon="list" title={t("reports.gaps")} desc={t("reports.gapsDesc")}>
          <Dl href="/api/reports/gaps.pdf?lang=en">{t("reports.pdfEn")}</Dl>
          <Dl href="/api/reports/gaps.pdf?lang=ar">{t("reports.pdfAr")}</Dl>
          <Dl href="/api/reports/gaps.csv">{t("reports.csv")}</Dl>
        </ReportCard>
        <ReportCard icon="list" title={t("reports.evidence")} desc={t("reports.evidenceDesc")}>
          <Dl href="/api/reports/evidence-pack.zip">{t("reports.zip")}</Dl>
        </ReportCard>
        <ReportCard icon="data" title={t("reports.oscalTitle")} desc={t("reports.oscalDesc")}>
          <div className="w-full space-y-3">
            {[
              ["/api/reports/oscal/assessment-results", t("reports.oscalAr"), t("reports.arDesc")],
              ["/api/reports/oscal/poam", t("reports.oscalPoam"), t("reports.poamDesc")],
              ["/api/catalog/oscal", t("reports.oscalCatalog"), t("reports.catalogDesc")],
            ].map(([href, label, desc]) => (
              <div key={href} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3">
                <div>
                  <div className="text-sm font-medium">{label}</div>
                  <div className="text-xs text-slate-500">{desc}</div>
                </div>
                <Dl href={href}>JSON</Dl>
              </div>
            ))}
          </div>
        </ReportCard>
        {can("checks.write") && <OscalImport />}
      </div>
      <p className="mt-6 text-xs text-slate-500">{t("reports.notice")}</p>
    </>
  );
}
