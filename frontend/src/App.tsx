import { lazy, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import AppShell, { setEnabledRoutes } from "./components/AppShell";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Requirements = lazy(() => import("./pages/Requirements"));
const RequirementDetail = lazy(() => import("./pages/RequirementDetail"));
const Checks = lazy(() => import("./pages/Checks"));
const RunDetail = lazy(() => import("./pages/RunDetail"));
const Assessment = lazy(() => import("./pages/Assessment"));
const Reports = lazy(() => import("./pages/Reports"));
const Register = lazy(() => import("./pages/Register"));
const Obligations = lazy(() => import("./pages/Obligations"));
const Incidents = lazy(() => import("./pages/Incidents"));
const IncidentDetail = lazy(() => import("./pages/IncidentDetail"));
const Users = lazy(() => import("./pages/Users"));
const Settings = lazy(() => import("./pages/Settings"));
const AuditLog = lazy(() => import("./pages/AuditLog"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Risks = lazy(() => import("./pages/Risks"));
const Requests = lazy(() => import("./pages/Requests"));
const Vendors = lazy(() => import("./pages/Vendors"));
const Dpias = lazy(() => import("./pages/Dpias"));
const Policies = lazy(() => import("./pages/Policies"));
const Account = lazy(() => import("./pages/Account"));
const Clients = lazy(() => import("./pages/Clients"));

const ROUTES: { path: string; element: ReactNode }[] = [
  { path: "/", element: <Dashboard /> },
  { path: "/clients", element: <Clients /> },
  { path: "/requirements", element: <Requirements /> },
  { path: "/requirements/:id", element: <RequirementDetail /> },
  { path: "/checks", element: <Checks /> },
  { path: "/checks/runs/:id", element: <RunDetail /> },
  { path: "/assessment", element: <Assessment /> },
  { path: "/reports", element: <Reports /> },
  { path: "/register", element: <Register /> },
  { path: "/obligations", element: <Obligations /> },
  { path: "/incidents", element: <Incidents /> },
  { path: "/incidents/:id", element: <IncidentDetail /> },
  { path: "/tasks", element: <Tasks /> },
  { path: "/risks", element: <Risks /> },
  { path: "/requests", element: <Requests /> },
  { path: "/vendors", element: <Vendors /> },
  { path: "/dpias", element: <Dpias /> },
  { path: "/policies", element: <Policies /> },
  { path: "/account", element: <Account /> },
  { path: "/users", element: <Users /> },
  { path: "/audit", element: <AuditLog /> },
  { path: "/settings", element: <Settings /> },
];
setEnabledRoutes(ROUTES.map((r) => r.path));

export function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Login />;
  return (
      <Routes>
        <Route element={<AppShell />}>
          {ROUTES.map((r) => (
            <Route key={r.path} path={r.path} element={r.element} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
