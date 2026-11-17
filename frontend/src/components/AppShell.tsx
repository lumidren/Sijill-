import { Suspense, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth";
import { OrgProvider, useOrg } from "../org";
import { Spinner } from "./ui";
import type { Lang } from "../i18n";

type Item = { to: string; key: string; icon: ReactNode; cap?: string };

const I = (d: string) => (
  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);

const ICONS = {
  evidenceRequests: I("M4 4h16v12H5.2L4 17.2V4Zm4 5h8M8 12h5M15 20l2 2 4-4"),
  clients: I("M3 21h18M6 21V7l6-4 6 4v14M10 11h4M10 15h4M3 10h3m12 0h3"),
  dashboard: I("M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z"),
  requirements: I("M9 5h11M9 12h11M9 19h11M4 5h.01M4 12h.01M4 19h.01"),
  assessment: I("M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"),
  checks: I("M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3Zm-3 9 2 2 4-4"),
  reports: I("M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6M8 13h8M8 17h5"),
  register: I("M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"),
  obligations: I("M8 7V3m8 4V3M4 11h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"),
  incidents: I("M12 8v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z"),
  users: I("M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM21 19v-1a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"),
  audit: I("M12 8v4l2.5 2.5M3.05 11a9 9 0 1 1 .5 4M3 4v4h4"),
  tasks: I("M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"),
  risks: I("M12 3 2 20h20L12 3Zm0 6v5m0 3h.01"),
  requests: I("M4 5h16v11H8l-4 4V5Zm4 4h8M8 12h5"),
  vendors: I("M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6M9 10h.01M15 10h.01"),
  dpias: I("M11 4a7 7 0 1 0 4.9 12l4.6 4.6M8 11l2 2 4-4"),
  policies: I("M7 3h8l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm1 9h8M8 16h6M8 8h4"),
  settings: I("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.3l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-2.2-1.3L14.3 3h-4l-.4 2.4a7.6 7.6 0 0 0-2.2 1.3l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.6l-2 1.6 2 3.4 2.4-1c.7.5 1.4 1 2.2 1.3l.4 2.4h4l.4-2.4c.8-.3 1.5-.8 2.2-1.3l2.4 1 2-3.4-2-1.6c.1-.4.1-.9.1-1.3Z"),
};

export const WORKSPACE: Item[] = [
  { to: "/", key: "dashboard", icon: ICONS.dashboard },
  { to: "/requirements", key: "requirements", icon: ICONS.requirements },
  { to: "/assessment", key: "assessment", icon: ICONS.assessment },
  { to: "/evidence-requests", key: "evidenceRequests", icon: ICONS.evidenceRequests },
  { to: "/checks", key: "checks", icon: ICONS.checks },
  { to: "/reports", key: "reports", icon: ICONS.reports },
  { to: "/register", key: "register", icon: ICONS.register },
  { to: "/obligations", key: "obligations", icon: ICONS.obligations },
  { to: "/incidents", key: "incidents", icon: ICONS.incidents },
];
export const GOVERNANCE: Item[] = [
  { to: "/tasks", key: "tasks", icon: ICONS.tasks },
  { to: "/risks", key: "risks", icon: ICONS.risks },
  { to: "/requests", key: "requests", icon: ICONS.requests },
  { to: "/vendors", key: "vendors", icon: ICONS.vendors },
  { to: "/dpias", key: "dpias", icon: ICONS.dpias },
  { to: "/policies", key: "policies", icon: ICONS.policies },
];
export const ADMIN: Item[] = [
  { to: "/users", key: "users", icon: ICONS.users, cap: "users.manage" },
  { to: "/audit", key: "audit", icon: ICONS.audit, cap: "audit.read" },
  { to: "/settings", key: "settings", icon: ICONS.settings },
];

/** Routes that exist in this build; the shell hides links to features not built yet. */
let enabledRoutes = new Set<string>(["/", "/users", "/audit"]);
export function setEnabledRoutes(routes: string[]) {
  enabledRoutes = new Set(routes);
}

function NavItem({ item, onNavigate }: { item: Item; onNavigate: () => void }) {
  const { t } = useTranslation();
  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
          isActive ? "bg-white/12 text-white" : "text-brand-100/80 hover:bg-white/8 hover:text-white"
        }`
      }
    >
      {item.icon}
      {t(`nav.${item.key}`)}
    </NavLink>
  );
}

export function LangSwitch({ className = "" }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const { changeLang } = useAuth();
  const next: Lang = i18n.language === "ar" ? "en" : "ar";
  return (
    <button
      type="button"
      className={`btn-ghost ${className}`}
      onClick={() => changeLang(next)}
      lang={next}
      aria-label={`${t("app.language")}: ${t("app.switchTo")}`}
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
        <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-9-9h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" />
      </svg>
      {t("app.switchTo")}
    </button>
  );
}

/** Which client organisation the workspace shows. Hidden when the user can open only one. */
export function OrgSwitcher() {
  const { t } = useTranslation();
  const { orgs, current, currentOrg, select } = useOrg();
  if (orgs.length === 0) return null;
  if (orgs.length === 1)
    return (
      <div className="mb-6 truncate px-3 text-xs text-brand-100/90" title={currentOrg?.name}>
        {currentOrg?.name}
      </div>
    );
  return (
    <div className="mb-6 px-1">
      <label htmlFor="org-switch" className="mb-1 block px-2 text-[11px] font-semibold uppercase tracking-wider text-brand-200/70">
        {t("orgs.switch")}
      </label>
      <select
        id="org-switch"
        className="w-full rounded-lg border border-white/15 bg-white/10 px-2.5 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-brand-300 [&>option]:text-ink"
        value={current ?? ""}
        onChange={(e) => select(Number(e.target.value))}
      >
        {orgs.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Disclaimer() {
  const { t } = useTranslation();
  return (
    <footer className="border-t border-slate-200 px-6 py-4 text-xs text-slate-500">
      <p>{t("app.disclaimer")}</p>
    </footer>
  );
}

export default function AppShell() {
  return (
    <OrgProvider>
      <Shell />
    </OrgProvider>
  );
}

function Shell() {
  const { t } = useTranslation();
  const { user, logout, can } = useAuth();
  const { orgs, current, currentOrg } = useOrg();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const visible = (items: Item[]) => items.filter((i) => enabledRoutes.has(i.to) && (!i.cap || can(i.cap)));
  const showClients = enabledRoutes.has("/clients") && (orgs.length > 1 || can("orgs.manage"));

  const sidebar = (
    <div className="flex h-full flex-col bg-brand-900 px-3 py-5 text-white">
      <div className="mb-5 flex items-center gap-2.5 px-2">
        <img src="/favicon.svg" alt="" className="h-8 w-8" />
        <div>
          <div className="text-[15px] font-semibold leading-tight">{t("app.name")}</div>
          <div className="text-[11px] leading-tight text-brand-200/80">PDPL 151/2020</div>
        </div>
      </div>
      <OrgSwitcher />
      <nav aria-label={t("nav.main")} className="flex flex-1 flex-col gap-6 overflow-y-auto">
        {showClients && (
          <div className="flex flex-col gap-0.5">
            <NavItem item={{ to: "/clients", key: "clients", icon: ICONS.clients }} onNavigate={close} />
          </div>
        )}
        <div>
          <div className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-brand-200/70">{t("nav.workspace")}</div>
          <div className="flex flex-col gap-0.5">
            {visible(WORKSPACE).map((i) => (
              <NavItem key={i.to} item={i} onNavigate={close} />
            ))}
          </div>
        </div>
        {visible(GOVERNANCE).length > 0 && (
          <div>
            <div className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-brand-200/70">{t("nav.governance")}</div>
            <div className="flex flex-col gap-0.5">
              {visible(GOVERNANCE).map((i) => (
                <NavItem key={i.to} item={i} onNavigate={close} />
              ))}
            </div>
          </div>
        )}
        {visible(ADMIN).length > 0 && (
          <div>
            <div className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-brand-200/70">{t("nav.admin")}</div>
            <div className="flex flex-col gap-0.5">
              {visible(ADMIN).map((i) => (
                <NavItem key={i.to} item={i} onNavigate={close} />
              ))}
            </div>
          </div>
        )}
      </nav>
      {user && (
        <div className="mt-4 rounded-xl bg-white/8 p-3">
          <div className="truncate text-sm font-medium">{user.display_name}</div>
          <div className="text-xs text-brand-200/80">{t(`roles.${user.role}`)}</div>
          <div className="mt-2 flex gap-3">
            {enabledRoutes.has("/account") && (
              <NavLink to="/account" onClick={close} className="text-xs font-medium text-brand-100 underline-offset-2 hover:underline">
                {t("nav.account")}
              </NavLink>
            )}
            <button className="text-xs font-medium text-brand-100 underline-offset-2 hover:underline" onClick={logout}>
              {t("nav.signOut")}
            </button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        {t("app.skip")}
      </a>
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-slate-900/40" onClick={close} />
          <div className="absolute inset-y-0 start-0 w-64">{sidebar}</div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white/85 px-4 backdrop-blur sm:px-6">
          <button className="btn-ghost lg:hidden" onClick={() => setOpen(true)} aria-label={t("nav.main")}>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="hidden min-w-0 truncate text-sm text-slate-500 sm:block">
            {orgs.length > 1 && currentOrg ? <span className="font-medium text-ink">{currentOrg.name}</span> : t("app.tagline")}
          </div>
          <div className="flex items-center gap-2">
            {user?.role === "auditor" && (
              <span className="chip bg-slate-100 text-slate-700 ring-1 ring-slate-300">{t("common.readOnly")}</span>
            )}
            <LangSwitch />
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Suspense fallback={<Spinner />}>
            {/* Remount the page when the organisation changes, so nothing from the last one lingers. */}
            <Outlet key={current ?? 0} />
          </Suspense>
        </main>
        <Disclaimer />
      </div>
    </div>
  );
}
