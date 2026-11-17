import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../auth";

export type Routes = Record<string, unknown | ((init?: RequestInit) => unknown)>;

/** Stub window.fetch with a map of "METHOD /path" or "/path" -> JSON body (or fn). */
export function mockFetch(routes: Routes) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method || "GET").toUpperCase();
    calls.push({ method, url, body: init?.body });
    const path = url.split("?")[0];
    const key = [`${method} ${url}`, `${method} ${path}`, url, path].find((k) => k in routes);
    if (!key) return new Response(JSON.stringify({ detail: "not_found" }), { status: 404, headers: { "content-type": "application/json" } });
    let value = routes[key];
    if (typeof value === "function") value = (value as (i?: RequestInit) => unknown)(init);
    if (value instanceof Response) return value;
    return new Response(JSON.stringify(value), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

export const ME = (role: "admin" | "dpo" | "it" | "auditor", caps: string[] = ["read"]) => ({
  id: 1,
  username: role,
  display_name: role.toUpperCase(),
  role,
  locale: "en",
  capabilities: caps,
});

export function renderPage(ui: ReactElement, path = "/") {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </AuthProvider>,
  );
}
