import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import en from "../i18n/en";
import ar from "../i18n/ar";
import { ME, mockFetch, renderPage } from "./utils";

function keys(o: object, prefix = ""): string[] {
  return Object.entries(o).flatMap(([k, v]) => (typeof v === "string" ? [prefix + k] : keys(v, `${prefix}${k}.`)));
}

describe("i18n", () => {
  it("Arabic has exactly the English keys and no empty strings", () => {
    expect(keys(ar).sort()).toEqual(keys(en).sort());
    const flat = (o: object): string[] => Object.values(o).flatMap((v) => (typeof v === "string" ? [v] : flat(v)));
    expect(flat(ar).every((s) => s.trim().length > 0)).toBe(true);
  });
});

describe("login and shell", () => {
  it("shows the sign-in form when not authenticated", async () => {
    mockFetch({ "/api/auth/me": new Response(JSON.stringify({ detail: "not_authenticated" }), { status: 401 }), "/api/auth/status": { needs_setup: false } });
    renderPage(<AppRoutes />);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument();
  });

  it("offers first-admin setup on an empty install", async () => {
    mockFetch({ "/api/auth/me": new Response("{}", { status: 401 }), "/api/auth/status": { needs_setup: true } });
    renderPage(<AppRoutes />);
    expect(await screen.findByRole("heading", { name: /first administrator/i })).toBeInTheDocument();
  });

  it("shows a clear message on bad credentials", async () => {
    mockFetch({
      "/api/auth/me": new Response("{}", { status: 401 }),
      "/api/auth/status": { needs_setup: false },
      "POST /api/auth/login": new Response(JSON.stringify({ detail: "invalid_credentials" }), { status: 401 }),
    });
    renderPage(<AppRoutes />);
    await userEvent.type(await screen.findByLabelText("Username"), "dpo");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
  });

  it("switches to Arabic with right-to-left layout", async () => {
    mockFetch({
      "/api/auth/me": ME("dpo"),
      "PUT /api/auth/me/locale": { ...ME("dpo"), locale: "ar" },
    });
    renderPage(<AppRoutes />);
    const btn = await screen.findByRole("button", { name: /العربية/ });
    await userEvent.click(btn);
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    expect(await screen.findAllByText("لوحة المتابعة")).not.toHaveLength(0);
  });

  it("hides admin navigation from non-admins", async () => {
    mockFetch({ "/api/auth/me": ME("it", ["read", "checks.write"]) });
    renderPage(<AppRoutes />);
    await screen.findAllByText("Dashboard");
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
  });

  it("auditors see the read-only badge", async () => {
    mockFetch({ "/api/auth/me": ME("auditor", ["read", "audit.read"]) });
    renderPage(<AppRoutes />);
    expect(await screen.findByText("You have read-only access.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Audit log" })).toBeInTheDocument();
  });
});
