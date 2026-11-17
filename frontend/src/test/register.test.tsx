import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth";
import Register from "../pages/Register";
import { ME, mockFetch } from "./utils";

const ROW = {
  id: 1, ref: "C-001", role: "controller", name: "Patient medical records", purpose: "Care", lawful_basis: "", data_subjects: ["Patients"],
  data_categories: ["Medical history"], sensitive_categories: ["Health data"], source: "", recipients: [], cross_border: true,
  transfer_countries: ["Germany"], transfer_safeguards: "", retention: "", security_measures: "", systems: [], client_name: "",
  owner: "", status: "active", updated_at: "2026-11-01T10:00:00Z", issues: ["missing_retention", "missing_transfer_safeguards"],
};

function renderRegister() {
  return render(
    <AuthProvider>
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("processing register", () => {
  it("lists activities with plain-language completeness hints", async () => {
    mockFetch({ "/api/auth/me": ME("auditor"), "/api/register": [ROW] });
    renderRegister();
    expect(await screen.findByText("Patient medical records")).toBeInTheDocument();
    expect(screen.getByText("No retention period")).toBeInTheDocument();
    expect(screen.getByText("Transfer safeguards missing")).toBeInTheDocument();
    expect(screen.queryByText("+ Add activity")).toBeNull();
  });

  it("creates an activity with one item per line and closes on Escape", async () => {
    const calls = mockFetch({ "/api/auth/me": ME("dpo", ["read", "register.write"]), "/api/register": [], "POST /api/register": ROW });
    renderRegister();
    await userEvent.click(await screen.findByText("+ Add activity"));
    expect(screen.getByLabelText("Processing activity")).toHaveFocus();
    await userEvent.type(screen.getByLabelText("Processing activity"), "Staff HR records");
    await userEvent.type(screen.getByLabelText("Whose data (one per line)"), "Employees{enter}Applicants{enter}");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const post = calls.find((c) => c.method === "POST")!;
    const body = JSON.parse(String(post.body));
    expect(body.name).toBe("Staff HR records");
    expect(body.data_subjects).toEqual(["Employees", "Applicants"]);
    await userEvent.click(screen.getByText("+ Add activity"));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
