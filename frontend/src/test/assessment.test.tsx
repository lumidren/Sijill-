import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth";
import Assessment from "../pages/Assessment";
import { ME, mockFetch } from "./utils";

const bi = (en: string) => ({ en, ar: en });
const result = (over = {}) => ({ status: "not_assessed", basis: "not_assessed", capped: false, stale: false, reason: "not_assessed", failing_checks: 0, passing_checks: 0, automated_status: null, ...over });
const OVERVIEW = {
  answered: 0,
  total: 2,
  areas: [
    {
      id: "a06",
      label: "A06",
      title: bi("Security of processing"),
      overview: bi("Technical safeguards"),
      score: 0.5,
      answered: 0,
      requirement_count: 2,
      requirements: [
        { id: "a06-01", label: "A06.01", title: bi("Encryption at rest"), statement: bi("Storage is encrypted."), question: bi("Is all storage encrypted?"), guidance: bi(""), technical: true, verified: false, weight: 3, answer: null, evidence_count: 0, result: result({ basis: "automated", status: "partial", automated_status: "partial", failing_checks: 2, passing_checks: 5, reason: "derived_from_checks" }) },
        { id: "a06-02", label: "A06.02", title: bi("Encryption in transit"), statement: bi("TLS everywhere."), question: bi("Is data encrypted in transit?"), guidance: bi(""), technical: true, verified: false, weight: 3, answer: null, evidence_count: 0, result: result() },
      ],
    },
  ],
};

function renderAssessment() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/assessment?area=a06"]}>
        <Routes>
          <Route path="/assessment" element={<Assessment />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("assessment", () => {
  it("lets the DPO answer, warns about the cap, and shows the new status", async () => {
    const calls = mockFetch({
      "/api/auth/me": ME("dpo", ["read", "assessment.write", "evidence.upload"]),
      "/api/assessment": OVERVIEW,
      "PUT /api/assessment/answers/a06-01": { result: result({ status: "partial", basis: "automated", capped: true, automated_status: "partial", failing_checks: 2, passing_checks: 5 }) },
    });
    renderAssessment();
    const card = (await screen.findByText("Is all storage encrypted?")).closest("section")!;
    expect(within(card).getByText(/cannot score above “Partly met”/)).toBeInTheDocument();
    const save = within(card).getByRole("button", { name: "Save answer" });
    expect(save).toBeDisabled();
    await userEvent.click(within(card).getByRole("radio", { name: /Yes, fully/ }));
    await userEvent.type(within(card).getByLabelText("Notes (optional)"), "Encrypted per IT.");
    await userEvent.click(save);
    expect(await within(card).findByRole("status")).toHaveTextContent("Saved. Status is now: Partly met");
    const put = calls.find((c) => c.method === "PUT")!;
    expect(JSON.parse(String(put.body))).toEqual({ status: "compliant", note: "Encrypted per IT." });
  });

  it("is read-only for auditors", async () => {
    mockFetch({ "/api/auth/me": ME("auditor", ["read"]), "/api/assessment": OVERVIEW });
    renderAssessment();
    await screen.findByText("Is all storage encrypted?");
    expect(screen.getByText("Your role can view the assessment but not change answers.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save answer" })).toBeNull();
    expect(screen.getAllByRole("radio")[0]).toBeDisabled();
    expect(screen.queryByText("Attach file")).toBeNull();
  });

  it("shows a plain-language message for a rejected evidence file", async () => {
    mockFetch({
      "/api/auth/me": ME("it", ["read", "evidence.upload"]),
      "/api/assessment": OVERVIEW,
      "POST /api/evidence": new Response(JSON.stringify({ detail: "content_mismatch" }), { status: 415, headers: { "content-type": "application/json" } }),
    });
    renderAssessment();
    const card = (await screen.findByText("Is all storage encrypted?")).closest("section")!;
    const input = within(card).getByText("Attach file").querySelector("input")!;
    await userEvent.upload(input, new File(["MZ"], "scan.pdf", { type: "application/pdf" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("don't match its extension");
  });
});
