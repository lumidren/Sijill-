import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ApiError } from "../api";

export type ReqStatus = "compliant" | "partial" | "non_compliant" | "not_applicable" | "not_assessed";
export type Basis = "automated" | "attested" | "not_assessed";

const STATUS_STYLE: Record<ReqStatus, string> = {
  compliant: "bg-green-50 text-green-800 ring-1 ring-green-600/20",
  partial: "bg-amber-50 text-amber-800 ring-1 ring-amber-600/25",
  non_compliant: "bg-red-50 text-red-800 ring-1 ring-red-600/20",
  not_applicable: "bg-slate-100 text-slate-600 ring-1 ring-slate-400/20",
  not_assessed: "bg-white text-slate-600 ring-1 ring-slate-300",
};
const STATUS_DOT: Record<ReqStatus, string> = {
  compliant: "bg-green-600",
  partial: "bg-amber-500",
  non_compliant: "bg-red-600",
  not_applicable: "bg-slate-400",
  not_assessed: "border border-slate-400 bg-white",
};

export function StatusChip({ status }: { status: ReqStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`chip ${STATUS_STYLE[status]}`}>
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[status]}`} />
      {t(`status.${status}`)}
    </span>
  );
}

const BASIS_STYLE: Record<Basis, string> = {
  automated: "bg-sky-50 text-sky-800 ring-1 ring-sky-600/20",
  attested: "bg-violet-50 text-violet-800 ring-1 ring-violet-600/20",
  not_assessed: "bg-white text-slate-500 ring-1 ring-slate-300",
};

export function BasisChip({ basis }: { basis: Basis }) {
  const { t } = useTranslation();
  // "Not assessed" is already said by the status chip next to it.
  if (basis === "not_assessed") return null;
  const label = basis === "automated" ? t("basis.automatedShort") : basis === "attested" ? t("basis.attestedShort") : t("basis.not_assessed");
  return <span className={`chip ${BASIS_STYLE[basis]}`}>{label}</span>;
}

export function CheckChip({ status }: { status: "PASS" | "FAIL" | "MANUAL" }) {
  const { t } = useTranslation();
  const cls =
    status === "PASS"
      ? "bg-green-50 text-green-800 ring-1 ring-green-600/20"
      : status === "FAIL"
        ? "bg-red-50 text-red-800 ring-1 ring-red-600/20"
        : "bg-slate-100 text-slate-700 ring-1 ring-slate-400/20";
  return <span className={`chip ${cls}`}>{t(`check.${status}`)}</span>;
}

export function Unverified() {
  const { t } = useTranslation();
  return (
    <span
      className="chip border border-dashed border-slate-300 bg-transparent px-1.5 text-[11px] font-normal text-slate-500"
      title={t("common.unverifiedHint")}
    >
      <svg aria-hidden viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor">
        <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 3a.9.9 0 0 1 .9.9v3.3a.9.9 0 1 1-1.8 0V4.9A.9.9 0 0 1 8 4Zm0 8.2a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z" />
      </svg>
      {t("common.unverified")}
      <span className="sr-only">: {t("common.unverifiedHint")}</span>
    </span>
  );
}

export function StaleChip() {
  const { t } = useTranslation();
  return (
    <span className="chip bg-orange-50 text-orange-800 ring-1 ring-orange-600/20" title={t("common.staleHint")}>
      {t("common.stale")}
    </span>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div role="status" className="flex items-center gap-3 py-10 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" aria-hidden />
      {label ?? t("app.loading")}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError | null; onRetry?: () => void }) {
  const { t } = useTranslation();
  if (!error) return null;
  const msg =
    error.status === 403 ? t("common.forbidden") : error.status === 404 ? t("common.notFound") : t(`errors.${error.code}`, { defaultValue: t("common.error") });
  return (
    <div role="alert" className="flex items-center justify-between gap-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <span>{msg}</span>
      {onRetry && (
        <button className="btn-secondary" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint, action, icon }: { title: string; hint?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50/60 px-6 py-10 text-center">
      <div className="mb-3 text-slate-400" aria-hidden>
        {icon ?? (
          <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 7l9-4 9 4-9 4-9-4Z" />
            <path d="M3 12l9 4 9-4M3 17l9 4 9-4" />
          </svg>
        )}
      </div>
      <p className="font-medium text-slate-800">{title}</p>
      {hint && <p className="mt-1 max-w-md text-sm text-slate-600">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Card({ title, children, actions, className = "" }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
