import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import AppShell, { setEnabledRoutes } from "./components/AppShell";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Users = lazy(() => import("./pages/Users"));
const AuditLog = lazy(() => import("./pages/AuditLog"));

const ROUTES: { path: string; element: ReactNode }[] = [
  { path: "/", element: <Dashboard /> },
  { path: "/users", element: <Users /> },
  { path: "/audit", element: <AuditLog /> },
];
setEnabledRoutes(ROUTES.map((r) => r.path));

export function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Login />;
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<AppShell />}>
          {ROUTES.map((r) => (
            <Route key={r.path} path={r.path} element={r.element} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
