import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import { setLang } from "../i18n";
import { ME, mockFetch, renderPage } from "./utils";

const POSTURE = {
  overall: 0.5, counts: {}, stale_days: 30,
  areas: [{ id: "a05", label: "A05", title: { en: "Security of processing", ar: "أمن المعالجة" } }],
  requirements: [
    { id: "a05-04", label: "A05.04", area_id: "a05", title: { en: "Backups", ar: "النسخ الاحتياطي" }, status: "non_compliant" },
    { id: "a05-01", label: "A05.01", area_id: "a05", title: { en: "Security policy", ar: "سياسة الأمن" }, status: "compliant" },
  ],
};
const ITEM = {
  id: 11, requirement_id: "a05-04", label: "A05.04", title: { en: "Backups", ar: "النسخ الاحتياطي" },
  question: { en: "Are backups encrypted and tested?", ar: "هل النسخ الاحتياطية مشفرة ومختبرة؟" }, ask: "The last restore test",
  response: "", status: "open", responded_at: null, review_note: "", files: [],
};
const REQ = {
  id: 5, title: "Q4 evidence", recipient: "Omar", recipient_contact: "", message: "", status: "open",
  expires_at: "2026-12-01T00:00:00Z", created_at: "2026-11-18T00:00:00Z", first_opened_at: null, submitted_at: null,
  total: 1, counts: { open: 1, answered: 0, accepted: 0, returned: 0 }, files: 0, items: [ITEM],
};
const ORGS = { "/api/orgs": { current: 1, items: [] } };
const body = (calls: { method: string; url: string; body?: unknown }[], method: string, url: string) =>
  JSON.parse(String(calls.filter((c) => c.method === method && c.url === url).at(-1)!.body));

describe("evidence requests (consultant)", () => {
  it("creates a request from a requirement and shows the link once", async () => {
    const calls = mockFetch({
      "/api/auth/me": ME("dpo", ["read", "evidence_requests.manage"]), ...ORGS,
      "/api/evidence-requests": [], "/api/posture": POSTURE,
      "POST /api/evidence-requests": { ...REQ, token: "tok-abcdefghijklmnopqrstuvwxyz0123456789" },
    });
    renderPage(<AppRoutes />, "/evidence-requests?new=a05-04");
    expect(await screen.findByRole("checkbox", { name: /Backups/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Security policy/ })).not.toBeChecked();
    await userEvent.type(screen.getByLabelText("Title"), "Q4 evidence");
    await userEvent.type(screen.getByLabelText("Recipient"), "Omar");
    await userEvent.type(screen.getByLabelText("What you need: A05.04"), "The last restore test");
    await userEvent.click(screen.getByRole("button", { name: "Create and get the link" }));
    await waitFor(() => expect(body(calls, "POST", "/api/evidence-requests")).toMatchObject({
      title: "Q4 evidence", recipient: "Omar", requirement_ids: ["a05-04"], asks: { "a05-04": "The last restore test" }, expires_days: 14,
    }));
    const dialog = await screen.findByRole("dialog", { name: "Private link ready" });
    expect(within(dialog).getByLabelText("Link")).toHaveValue(`${window.location.origin}/r/tok-abcdefghijklmnopqrstuvwxyz0123456789`);
  });

  it("reviews an answer: accept attaches the files", async () => {
    const answered = { ...REQ, status: "submitted", counts: { open: 0, answered: 1, accepted: 0, returned: 0 },
      items: [{ ...ITEM, status: "answered", response: "Restore tested on 3 Nov.", files: [{ id: 3, filename: "restore.pdf", size: 2048, uploaded_at: "2026-11-17T10:00:00Z", sha256: "ab".repeat(32), evidence_file_id: null }] }] };
    const calls = mockFetch({
      "/api/auth/me": ME("dpo", ["read", "evidence_requests.manage"]), ...ORGS,
      "/api/evidence-requests/5": answered, "POST /api/evidence-requests/5/items/11/review": answered,
    });
    renderPage(<AppRoutes />, "/evidence-requests/5");
    expect(await screen.findByText("Restore tested on 3 Nov.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "restore.pdf" })).toHaveAttribute("href", "/api/evidence-requests/5/files/3/download");
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(body(calls, "POST", "/api/evidence-requests/5/items/11/review")).toEqual({ decision: "accept", note: "" }));
  });

  it("hides management from read-only roles", async () => {
    mockFetch({ "/api/auth/me": ME("auditor"), ...ORGS, "/api/evidence-requests/5": REQ });
    renderPage(<AppRoutes />, "/evidence-requests/5");
    expect(await screen.findByRole("heading", { name: "Q4 evidence" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New link" })).toBeNull();
  });
});

describe("evidence request link (client staff, no account)", () => {
  const VIEW = { organization: { name: "Delta Pharmacies", name_ar: "صيدليات الدلتا" }, title: "Q4 evidence", recipient: "Omar",
    message: "Thanks!", status: "open", expires_at: "2026-12-01T00:00:00Z", max_upload_mb: 20, files_per_item: 10, items: [ITEM] };

  it("answers, attaches a file and submits", async () => {
    const calls = mockFetch({
      "/api/auth/me": new Response("{}", { status: 401 }), "/api/auth/status": { needs_setup: false },
      "/api/public/r/tok123": VIEW,
      "PUT /api/public/r/tok123/items/11": { ...ITEM, status: "answered", response: "Yes, monthly." },
      "POST /api/public/r/tok123/items/11/files": { ...ITEM, status: "answered", response: "Yes, monthly.", files: [{ id: 1, filename: "test.pdf", size: 900, uploaded_at: "x" }] },
      "POST /api/public/r/tok123/submit": { status: "submitted" },
    });
    renderPage(<AppRoutes />, "/r/tok123");
    expect(await screen.findByRole("heading", { name: "Q4 evidence" })).toBeInTheDocument();
    expect(screen.getByText("Are backups encrypted and tested?")).toBeInTheDocument();
    expect(screen.getByText(/The last restore test/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).toBeNull();
    expect(screen.getByRole("button", { name: "Send my answers" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Your answer"), "Yes, monthly.");
    await userEvent.click(screen.getByRole("button", { name: "Save answer" }));
    await waitFor(() => expect(body(calls, "PUT", "/api/public/r/tok123/items/11")).toEqual({ response: "Yes, monthly." }));
    await userEvent.upload(screen.getByLabelText("Attach a file"), new File(["%PDF-1.4"], "test.pdf", { type: "application/pdf" }));
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send my answers" }));
    expect(await screen.findByText("Thank you, your answers were sent.")).toBeInTheDocument();
    expect(screen.getByLabelText("Your answer")).toBeDisabled();
  });

  it("explains an expired link", async () => {
    mockFetch({
      "/api/auth/me": new Response("{}", { status: 401 }), "/api/auth/status": { needs_setup: false },
      "/api/public/r/old": new Response(JSON.stringify({ detail: "link_expired" }), { status: 410, headers: { "content-type": "application/json" } }),
    });
    renderPage(<AppRoutes />, "/r/old");
    expect(await screen.findByRole("heading", { name: "This link has expired." })).toBeInTheDocument();
  });

  it("works in Arabic, right to left", async () => {
    await setLang("ar");
    mockFetch({ "/api/auth/me": new Response("{}", { status: 401 }), "/api/auth/status": { needs_setup: false }, "/api/public/r/tok123": VIEW });
    renderPage(<AppRoutes />, "/r/tok123");
    expect(await screen.findByText("صيدليات الدلتا")).toBeInTheDocument();
    expect(screen.getByText("هل النسخ الاحتياطية مشفرة ومختبرة؟")).toBeInTheDocument();
    expect(document.documentElement.dir).toBe("rtl");
    await setLang("en");
  });
});
