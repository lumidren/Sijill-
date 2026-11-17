import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import { ME, mockFetch, renderPage } from "./utils";

const ORGS = {
  current: 1,
  items: [
    { id: 1, name: "Nour Family Clinic", archived: false, created_at: "2026-11-01T00:00:00Z" },
    { id: 2, name: "Delta Pharmacies", archived: false, created_at: "2026-11-02T00:00:00Z" },
  ],
};
const row = (id: number, name: string, extra: object) => ({
  id, name, archived: false, created_at: "2026-11-01T00:00:00Z", overall: 0.62, gaps: 4, risks_high: 0, tasks_overdue: 0,
  requests_overdue: 0, vendors_without_dpa: 0, open_breaches: 0, last_run: null,
  counts: { total: 52, by_basis: { automated: 16, attested: 26, not_assessed: 10 }, by_status: {} }, ...extra,
});
const ADMIN = ME("admin", ["read", "orgs.manage", "users.manage"]);
const body = (calls: { method: string; url: string; body?: unknown }[], method: string, url: string) =>
  JSON.parse(String(calls.filter((c) => c.method === method && c.url === url).at(-1)!.body));

describe("several client organisations", () => {
  it("shows every client side by side and opens one", async () => {
    const calls = mockFetch({
      "/api/auth/me": ADMIN,
      "/api/orgs": ORGS,
      "/api/orgs/all": ORGS.items,
      "/api/orgs/overview": {
        current: 1,
        items: [row(1, "Nour Family Clinic", { last_run: "2026-11-16T08:00:00Z" }), row(2, "Delta Pharmacies", { overall: 0.41, tasks_overdue: 1, requests_overdue: 1, vendors_without_dpa: 1, counts: { total: 52, by_basis: { attested: 52 }, by_status: {} } })],
      },
      "POST /api/orgs/select": { current: 2 },
    });
    renderPage(<AppRoutes />, "/clients");
    expect(await screen.findByRole("heading", { name: "Clients" })).toBeInTheDocument();
    const delta = await screen.findByRole("row", { name: /Delta Pharmacies/ });
    expect(within(delta).getByText("41%")).toBeInTheDocument();
    expect(within(delta).getByRole("img")).toHaveAttribute("aria-label", "Automated evidence: 0, Self-attested: 52, Not assessed: 0");
    expect(within(delta).getByText("Never")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /Nour Family Clinic/ })).getByText("Open now")).toBeInTheDocument();
    await userEvent.click(within(delta).getByRole("button", { name: "Open: Delta Pharmacies" }));
    await waitFor(() => expect(body(calls, "POST", "/api/orgs/select")).toEqual({ id: 2 }));
  });

  it("switches organisation from the sidebar", async () => {
    const calls = mockFetch({ "/api/auth/me": ME("dpo"), "/api/orgs": ORGS, "POST /api/orgs/select": { current: 2 } });
    renderPage(<AppRoutes />, "/account");
    const switcher = (await screen.findAllByLabelText("Organisation"))[0];
    await waitFor(() => expect(switcher).toHaveValue("1"));
    await userEvent.selectOptions(switcher, "2");
    await waitFor(() => expect(body(calls, "POST", "/api/orgs/select")).toEqual({ id: 2 }));
    expect(screen.getAllByRole("link", { name: "Clients" }).length).toBeGreaterThan(0);
  });

  it("hides the switcher and the clients page for a single organisation", async () => {
    mockFetch({ "/api/auth/me": ME("dpo"), "/api/orgs": { current: 1, items: [ORGS.items[0]] } });
    renderPage(<AppRoutes />, "/account");
    expect((await screen.findAllByText("Nour Family Clinic")).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Organisation")).toBeNull();
    expect(screen.queryByRole("link", { name: "Clients" })).toBeNull();
  });

  it("limits a user to chosen organisations", async () => {
    const calls = mockFetch({
      "/api/auth/me": ADMIN,
      "/api/orgs": ORGS,
      "/api/users": [{ ...ME("auditor"), id: 7, display_name: "Salma", is_active: true, last_login_at: null, org_ids: null }],
      "PATCH /api/users/7": {},
    });
    renderPage(<AppRoutes />, "/users");
    const salma = await screen.findByRole("row", { name: /Salma/ });
    expect(within(salma).getByText("All organisations")).toBeInTheDocument();
    await userEvent.click(within(salma).getByRole("button", { name: "Change" }));
    await userEvent.click(screen.getByLabelText("All organisations"));
    await userEvent.click(screen.getByLabelText("Delta Pharmacies"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body(calls, "PATCH", "/api/users/7")).toEqual({ access: [2] }));
  });

  it("creates new accounts for the open organisation only by default", async () => {
    const calls = mockFetch({ "/api/auth/me": ADMIN, "/api/orgs": ORGS, "/api/users": [], "POST /api/users": {} });
    renderPage(<AppRoutes />, "/users");
    const scope = await screen.findByLabelText("Organisations");
    await waitFor(() => expect(scope).toHaveDisplayValue("Only Nour Family Clinic"));
    await userEvent.type(screen.getByLabelText("Name"), "Hany");
    await userEvent.type(screen.getByLabelText("Username"), "hany");
    await userEvent.type(screen.getByLabelText("Initial password"), "long-enough-pw");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(body(calls, "POST", "/api/users")).toMatchObject({ username: "hany", access: [1] }));
  });
});
