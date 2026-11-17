import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { GovernanceCard } from "../components/GovernanceCard";
import Account from "../pages/Account";
import Dpias from "../pages/Dpias";
import Policies from "../pages/Policies";
import Requests from "../pages/Requests";
import Risks from "../pages/Risks";
import Tasks from "../pages/Tasks";
import { ME, mockFetch, renderPage } from "./utils";

vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn(async () => "data:image/png;base64,AAAA") } }));

const json = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status, headers: { "content-type": "application/json" } });
const lastBody = (calls: { method: string; url: string; body?: unknown }[], method: string, url: string) =>
  JSON.parse(String(calls.filter((c) => c.method === method && c.url.startsWith(url)).at(-1)!.body));

const RISK = {
  id: 1, title: "Patient images exposed", description: "", category: "Cloud", likelihood: 4, impact: 5, score: 20, level: "critical",
  residual_likelihood: 2, residual_impact: 5, residual_score: 10, residual_level: "high", treatment: "mitigate", status: "open", owner: "IT",
  requirement_ids: ["a06-06"], controls: "", review_due: null, acceptance_expires_on: null, acceptance_expired: false, acceptance_note: "",
};

describe("two-step sign-in", () => {
  const signedOut = { "/api/auth/me": new Response("{}", { status: 401 }), "/api/auth/status": { needs_setup: false } };

  it("asks for the code after the password and verifies it", async () => {
    const calls = mockFetch({
      ...signedOut,
      "POST /api/auth/login": { mfa_required: true, mfa_token: "tok" },
      "POST /api/auth/mfa/verify": { ...ME("dpo"), mfa_enabled: true },
    });
    renderPage(<AppRoutes />);
    await userEvent.type(await screen.findByLabelText("Username"), "dpo");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Two-step sign-in" })).toBeInTheDocument();
    const verify = screen.getByRole("button", { name: "Verify" });
    expect(verify).toBeDisabled();
    await userEvent.type(screen.getByLabelText("6-digit code"), "123 456");
    await userEvent.click(verify);
    await waitFor(() => expect(lastBody(calls, "POST", "/api/auth/mfa/verify")).toEqual({ mfa_token: "tok", code: "123456" }));
    expect(await screen.findAllByText("Tasks")).not.toHaveLength(0);
  });

  it("sends the user back to the password when the code step expires", async () => {
    mockFetch({ ...signedOut, "POST /api/auth/login": { mfa_required: true, mfa_token: "tok" }, "POST /api/auth/mfa/verify": json(401, "mfa_token_expired") });
    renderPage(<AppRoutes />);
    await userEvent.type(await screen.findByLabelText("Username"), "dpo");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.type(await screen.findByLabelText("6-digit code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("took too long");
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("turns two-step sign-in on from the account page", async () => {
    const calls = mockFetch({
      "/api/auth/me": ME("it"),
      "POST /api/auth/mfa/setup": { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/Sijill:it?secret=JBSWY3DPEHPK3PXP" },
      "POST /api/auth/mfa/enable": { ...ME("it"), mfa_enabled: true },
    });
    renderPage(<Account />);
    await userEvent.click(await screen.findByRole("button", { name: "Turn on" }));
    expect(await screen.findByText("JBSW Y3DP EHPK 3PXP")).toBeInTheDocument();
    expect(await screen.findByRole("img")).toHaveAttribute("src", expect.stringContaining("data:image/png"));
    await userEvent.type(screen.getByLabelText("6-digit code"), "287082");
    await userEvent.click(screen.getByRole("button", { name: "Confirm and turn on" }));
    expect(await screen.findByText("Two-step sign-in is on.")).toBeInTheDocument();
    expect(lastBody(calls, "POST", "/api/auth/mfa/enable")).toEqual({ code: "287082" });
  });
});

describe("governance registers", () => {
  it("shows the risk heat map and keeps acceptance to admins", async () => {
    mockFetch({ "/api/auth/me": ME("dpo", ["read", "governance.write"]), "/api/risks": [RISK] });
    renderPage(<Risks />);
    expect(await screen.findByText("Patient images exposed")).toBeInTheDocument();
    expect(screen.getByRole("gridcell", { name: "1 risk(s) with likelihood 4 and impact 5" })).toHaveTextContent("1");
    expect(screen.getByText("20 • Critical")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept risk" })).toBeNull();
  });

  it("lets an admin accept a risk with a reason and an expiry", async () => {
    const calls = mockFetch({ "/api/auth/me": ME("admin", ["read", "governance.write", "risks.accept"]), "/api/risks": [RISK], "POST /api/risks/1/accept": RISK });
    renderPage(<Risks />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept risk" }));
    await userEvent.type(screen.getByLabelText("Why the organisation accepts it"), "Budget approved for next quarter");
    await userEvent.type(screen.getByLabelText("Acceptance expires on"), "2027-03-01");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(lastBody(calls, "POST", "/api/risks/1/accept")).toEqual({ note: "Budget approved for next quarter", expires_on: "2027-03-01" });
  });

  it("shows request clocks with the placeholder-period warning", async () => {
    mockFetch({
      "/api/auth/me": ME("auditor"),
      "/api/requests": [
        {
          id: 1, ref: "DSR-0001", request_type: "access", requester: "Patient ref P-1042", channel: "Email", received_at: "2026-10-22T09:00:00Z",
          identity_verified: false, status: "in_progress", details: "", outcome: "", owner: "DPO", due_at: "2026-11-21T09:00:00Z",
          days_left: -2, state: "overdue", response_days: 30,
        },
      ],
    });
    renderPage(<Requests />);
    expect(await screen.findByText("Patient ref P-1042")).toBeInTheDocument();
    expect(screen.getByText(/Due 30 days after receipt/)).toHaveTextContent("not a verified legal deadline");
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("2 days overdue")).toBeInTheDocument();
    expect(screen.getByText("Identity not verified yet")).toBeInTheDocument();
  });

  it("screens a DPIA as the criteria are ticked", async () => {
    const calls = mockFetch({
      "/api/auth/me": ME("dpo", ["read", "governance.write"]),
      "/api/dpias": [],
      "/api/register": [{ id: 7, name: "Patient medical records" }],
      "POST /api/dpias": {},
    });
    renderPage(<Dpias />);
    await userEvent.click(await screen.findByRole("button", { name: "+ Add" }));
    await userEvent.type(screen.getByLabelText("Title"), "Teleconsultation app");
    await userEvent.selectOptions(screen.getByLabelText("Processing activity"), "7");
    expect(screen.getByText("Assessment likely not needed (0 criteria)")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Sensitive data (health, biometric, …)"));
    await userEvent.click(screen.getByLabelText("New technology"));
    expect(screen.getByText("Assessment likely needed (2 criteria)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const body = lastBody(calls, "POST", "/api/dpias");
    expect(body.activity_id).toBe(7);
    expect(body.screening).toMatchObject({ sensitive_data: true, new_technology: true, large_scale: false });
  });

  it("shows policy history and lets an admin approve a draft", async () => {
    const calls = mockFetch({
      "/api/auth/me": ME("admin", ["read", "governance.write", "approve"]),
      "/api/policies": [
        {
          id: 3, title: "Breach response plan", version: "0.3", status: "draft", owner: "DPO", summary: "", requirement_ids: ["a07-01"],
          evidence_file_id: null, approved_on: null, review_due: null, days_to_review: null, review_overdue: false,
          history: [{ version: "0.3", status: "draft", at: "2026-11-01T10:00:00Z", by: "DPO" }],
        },
      ],
      "POST /api/policies/3/approve": {},
    });
    renderPage(<Policies />);
    await userEvent.click(await screen.findByRole("button", { name: "History (1)" }));
    expect(screen.getByText(/v0\.3/, { selector: "span" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/policies/3/approve")).toBe(true);
  });

  it("opens a task prefilled from a requirement gap", async () => {
    const calls = mockFetch({ "/api/auth/me": ME("it", ["read", "tasks.write"]), "/api/tasks": [], "POST /api/tasks": {} });
    renderPage(<Tasks />, "/tasks?new=a06-05&title=Multi-factor%20sign-in");
    expect(await screen.findByLabelText("Task")).toHaveValue("Multi-factor sign-in");
    expect(screen.getByLabelText("Requirement ID (optional, e.g. a06-05)")).toHaveValue("a06-05");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(lastBody(calls, "POST", "/api/tasks")).toMatchObject({ requirement_id: "a06-05", source: "gap", status: "todo" });
  });

  it("summarises governance on the dashboard with links", () => {
    const grid = [0, 0, 0, 0, 0].map(() => [0, 0, 0, 0, 0]);
    grid[4][3] = 1;
    render(
      <MemoryRouter>
        <GovernanceCard
          g={{
            tasks: { open: 6, overdue: 2 },
            risks: { open: 5, by_level: { critical: 1, high: 2 }, heat_map: grid, acceptance_expired: 0 },
            requests: { open: 2, overdue: 0, due_soon: 1 },
            vendors: { active: 4, without_dpa: 1 },
            policies: { approved: 1, review_overdue: 1 },
            dpias: { total: 2, approved: 1, pending: 1 },
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /Open tasks\s*6\s*2 overdue/ })).toHaveAttribute("href", "/tasks");
    expect(screen.getByRole("link", { name: /Processors without a contract\s*1/ })).toHaveAttribute("href", "/vendors");
    expect(screen.getByRole("gridcell", { name: "1 risk(s) with likelihood 4 and impact 5" })).toBeInTheDocument();
  });
});
