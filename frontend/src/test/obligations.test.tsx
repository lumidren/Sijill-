import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth";
import Obligations from "../pages/Obligations";
import { ME, mockFetch } from "./utils";

const Q = {
  licensing: {
    questions: ["controls_processing", "surveillance"],
    answers: { controls_processing: true, surveillance: true },
    results: [
      { key: "controller_licence", kind: "licence", question: "controls_processing", likely_required: true },
      { key: "marketing_permit", kind: "permit", question: "electronic_marketing", likely_required: false },
      { key: "processor_licence", kind: "licence", question: "processes_for_others", likely_required: null },
    ],
    notes: ["sensitive_data_conditions"],
  },
  applicability: { questions: ["processes_personal_data", "cbe_supervised", "money_transfer_or_exchange"], answers: { processes_personal_data: true, cbe_supervised: true, money_transfer_or_exchange: true }, result: "likely_in_scope", reason: "cbe_exception" },
  licence_validity_years: 3,
};
const ITEMS = [
  { id: 1, kind: "permit", title: "Surveillance permit (CCTV)", reference: "SV-1", status: "active", effective_status: "active", issued_on: "2025-12-12", expires_on: "2026-12-12", review_due: null, expiry_from_default: false, days_to_expiry: 25, days_to_review: null, owner: "Omar", notes: "" },
  { id: 2, kind: "licence", title: "Controller licence", reference: "CL-1", status: "active", effective_status: "active", issued_on: "2026-01-20", expires_on: "2029-01-20", review_due: null, expiry_from_default: true, days_to_expiry: 795, days_to_review: null, owner: "Mona", notes: "" },
  { id: 3, kind: "permit", title: "Old permit", reference: "", status: "active", effective_status: "expired", issued_on: null, expires_on: "2026-11-01", review_due: null, expiry_from_default: false, days_to_expiry: -16, days_to_review: null, owner: "", notes: "" },
];

function renderAt(path: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Obligations />
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("licences and obligations", () => {
  it("shows dates, days left, default-validity marking and expired items", async () => {
    mockFetch({ "/api/auth/me": ME("auditor"), "/api/obligations": ITEMS, "/api/obligations/reminders": [], "/api/obligations/questionnaires": Q });
    renderAt("/obligations");
    expect(await screen.findByText("Surveillance permit (CCTV)")).toBeInTheDocument();
    expect(screen.getByText("in 25 days")).toBeInTheDocument();
    expect(screen.getByText("(default validity, unverified)")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText("16 days overdue")).toBeInTheDocument();
  });

  it("phrases licensing results as likely, never required, and offers tracking", async () => {
    mockFetch({ "/api/auth/me": ME("dpo", ["read", "obligations.write"]), "/api/obligations": [], "/api/obligations/reminders": [], "/api/obligations/questionnaires": Q });
    renderAt("/obligations?tab=licensing");
    expect(await screen.findByText("Controller licence")).toBeInTheDocument();
    expect(screen.getAllByText("Likely required").length).toBeGreaterThan(0);
    expect(screen.getByText("Likely not required")).toBeInTheDocument();
    expect(screen.queryByText(/^Required$/)).toBeNull();
    expect(screen.getByText(/not legal advice/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Track this" }));
    expect(screen.getByLabelText("Title")).toHaveValue("Controller licence");
    expect(screen.getByText(/default validity from Settings \(3 years, unverified\)/)).toBeInTheDocument();
  });

  it("explains the CBE money-transfer exception in the applicability screener", async () => {
    mockFetch({ "/api/auth/me": ME("dpo", ["read", "obligations.write"]), "/api/obligations": [], "/api/obligations/reminders": [], "/api/obligations/questionnaires": Q });
    renderAt("/obligations?tab=applicability");
    expect(await screen.findByText("The law likely applies to you")).toBeInTheDocument();
    expect(screen.getByText(/money transfer and currency exchange companies are treated as in scope/)).toBeInTheDocument();
    expect(screen.getByText("Is it a money transfer company or a currency exchange company?")).toBeInTheDocument();
  });
});
