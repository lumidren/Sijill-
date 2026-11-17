import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth";
import { setLang } from "../i18n";
import Checks from "../pages/Checks";
import Dashboard from "../pages/Dashboard";
import RequirementDetail from "../pages/RequirementDetail";
import Requirements from "../pages/Requirements";
import { ME, mockFetch } from "./utils";

function renderAt(path: string, pattern: string, element: React.ReactElement) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

const counts = {
  total: 52,
  by_status: { compliant: 5, partial: 29, non_compliant: 5, not_assessed: 11, not_applicable: 2 },
  by_basis: { automated: 16, attested: 25, not_assessed: 11 },
  stale: 11,
  capped: 4,
  technical_total: 16,
  technical_automated: 16,
  failing_checks: 36,
};
const area = { id: "a06", label: "A06", title: { en: "Security of processing", ar: "أمن المعالجة" }, overview: { en: "o", ar: "o" }, score: 0.54, weight: 23, by_status: {}, by_basis: {} };

const DASH = {
  overall: 0.42,
  counts,
  areas: [area],
  trend: [
    { at: "2026-11-09T08:00:00Z", overall: 0.443, reason: "check_run" },
    { at: "2026-11-15T23:00:00Z", overall: 0.42, reason: "check_run" },
  ],
  gaps: [{ id: "a02-04", label: "A02.04", title: { en: "Sensitive personal data", ar: "البيانات الحساسة" }, status: "non_compliant", basis: "attested", weight: 3, area_id: "a06", failing_checks: 0, capped: false, stale: true }],
  gap_total: 45,
  regressions: [
    {
      check_id: "s3_bucket_public_access",
      resource: "arn:aws:s3:::nour-patient-scans",
      region: "eu-central-1",
      title: "S3 bucket is not publicly accessible",
      message: "public",
      severity: "critical",
      requirements: ["a06-06"],
      run_id: 7,
      previous_run_id: 5,
      target: "111122223333",
      provider: "aws",
      detected_at: "2026-11-15T23:25:00Z",
    },
  ],
  targets: [{ provider: "aws", target: "111122223333", run_id: 7, started_at: "2026-11-15T23:25:00Z", passed: 123, failed: 32 }],
  last_run: "2026-11-15T23:25:00Z",
  runs_total: 12,
  deadlines: [],
  breaches: [],
  features: { obligations: false, incidents: false },
  organization: { name: "Nour Family Clinic", name_ar: "عيادة نور للأسرة", demo: true },
};

describe("dashboard", () => {
  it("shows the score, the coverage split, the dip and the regression", async () => {
    mockFetch({ "/api/auth/me": ME("dpo"), "/api/posture/dashboard": DASH });
    renderAt("/", "/", <Dashboard />);
    expect(await screen.findByText("Nour Family Clinic")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Readiness score: 42/ })).toBeInTheDocument();
    expect(screen.getByText(/not legal compliance/)).toBeInTheDocument();
    expect(screen.getByText("16 of 16 technical-safeguard requirements have automated evidence.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Dropped 2.3 points/)).toBeInTheDocument();
    expect(screen.getByText("S3 bucket is not publicly accessible")).toBeInTheDocument();
    expect(screen.getByText(/Affects A06.06/)).toBeInTheDocument();
    // features not built are not shown as empty cards
    expect(screen.queryByText("Active breach clocks")).toBeNull();
  });

  it("renders in Arabic with Arabic-Indic digits", async () => {
    await setLang("ar");
    mockFetch({ "/api/auth/me": { ...ME("dpo"), locale: "ar" }, "/api/posture/dashboard": DASH });
    renderAt("/", "/", <Dashboard />);
    expect(await screen.findByText("عيادة نور للأسرة")).toBeInTheDocument();
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("img", { name: /٤٢/ })).toBeInTheDocument();
  });

  it("shows an empty state with an import action when nothing has been collected", async () => {
    mockFetch({ "/api/auth/me": ME("it"), "/api/posture/dashboard": { ...DASH, targets: [], regressions: [], trend: [] } });
    renderAt("/", "/", <Dashboard />);
    expect(await screen.findByText("No automated checks yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import findings" })).toHaveAttribute("href", "/checks");
    expect(screen.getByText("No regressions in the latest runs.")).toBeInTheDocument();
  });
});

const DETAIL = {
  requirement: {
    id: "a06-06",
    label: "A06.06",
    area_id: "a06",
    title: { en: "No public exposure of data stores", ar: "عدم إتاحة مخازن البيانات" },
    statement: { en: "Databases are not reachable from the internet.", ar: "..." },
    question: { en: "Have you confirmed?", ar: "..." },
    guidance: { en: "", ar: "" },
    weight: 3,
    technical: true,
    verified: false,
    source_status: "needed",
    source: "",
  },
  area: { id: "a06", score: 0.54, label: "A06", title: area.title, weight: 23 },
  result: {
    id: "a06-06", label: "A06.06", area_id: "a06", title: { en: "", ar: "" }, weight: 3, technical: true, status: "partial", basis: "automated", value: 0.5,
    attested_status: "compliant", automated_status: "partial", reason: "capped_by_failing_checks", capped: true, stale: false, evidence_at: null,
    failing_checks: 3, passing_checks: 5, verified: false, checks: [],
  },
  stale_days: 30,
  contribution: { points: 1.5, of: 3, area_weight: 23 },
  answer: { status: "compliant", note: "No public buckets.", updated_at: "2026-11-07T08:00:00Z", updated_by: "Dr. Mona Hassan" },
  checks: [
    { check_id: "s3_bucket_public_access", status: "FAIL", passing: 2, failing: 1, failing_resources: ["arn:aws:s3:::nour-patient-scans"], last_observed: "2026-11-15T23:25:00Z", title: "S3 bucket is not publicly accessible", provider: "aws", severity: "critical" },
  ],
  evidence: [],
};

describe("requirement drill-down", () => {
  it("explains a capped status down to the failing resource", async () => {
    mockFetch({ "/api/auth/me": ME("auditor"), "/api/posture/requirements/a06-06": DETAIL });
    renderAt("/requirements/a06-06", "/requirements/:id", <RequirementDetail />);
    expect(await screen.findByText(/Capped at “Partly met” because 3 mapped check\(s\) are failing/)).toBeInTheDocument();
    expect(screen.getByText("arn:aws:s3:::nour-patient-scans", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Contributes 1.5 of 3 possible points/)).toBeInTheDocument();
    expect(screen.getAllByText("Unverified").length).toBeGreaterThan(0);
    // auditors cannot answer
    expect(screen.queryByText("Answer in the assessment")).toBeNull();
  });
});

describe("requirements list", () => {
  it("filters by status from the URL", async () => {
    const req = (id: string, status: string) => ({ ...DETAIL.result, id, label: id.toUpperCase(), status, title: { en: `Req ${id}`, ar: `م ${id}` } });
    mockFetch({
      "/api/auth/me": ME("dpo"),
      "/api/posture": { overall: 0.4, counts, stale_days: 30, areas: [area], requirements: [req("a06-01", "compliant"), req("a06-02", "non_compliant")] },
    });
    renderAt("/requirements?status=gaps", "/requirements", <Requirements />);
    expect(await screen.findByText("Req a06-02")).toBeInTheDocument();
    expect(screen.queryByText("Req a06-01")).toBeNull();
  });
});

describe("checks", () => {
  it("shows a plain-language error for a malformed findings file", async () => {
    mockFetch({
      "/api/auth/me": ME("it", ["read", "checks.write"]),
      "/api/checks/runs": [],
      "POST /api/checks/import": new Response(JSON.stringify({ detail: "not_findings" }), { status: 422, headers: { "content-type": "application/json" } }),
    });
    renderAt("/checks", "/checks", <Checks />);
    const input = (await screen.findByText("Choose file")).querySelector("input")!;
    await userEvent.upload(input, new File(["[1]"], "bad.json", { type: "application/json" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("doesn't look like Prowler OCSF");
  });

  it("does not offer import to auditors", async () => {
    mockFetch({ "/api/auth/me": ME("auditor", ["read"]), "/api/checks/runs": [] });
    renderAt("/checks", "/checks", <Checks />);
    await waitFor(() => expect(screen.getByText("No runs yet.")).toBeInTheDocument());
    const panel = screen.getAllByText("Import findings")[0].closest("section")!;
    expect(within(panel).getByText("You have read-only access.")).toBeInTheDocument();
    expect(screen.queryByText("Choose file")).toBeNull();
  });
});
