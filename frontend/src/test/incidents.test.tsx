import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth";
import { BreachClock, liveState, type Clock } from "../components/BreachClock";
import { fmtDateTime } from "../i18n";
import IncidentDetail from "../pages/IncidentDetail";
import Incidents, { toCairoInput } from "../pages/Incidents";
import { ME, mockFetch } from "./utils";

const HOUR = 3_600_000;
const iso = (ms: number) => new Date(ms).toISOString();

function incident(discoveredHoursAgo: number, extra = {}) {
  const now = Date.now();
  const discovered = now - discoveredHoursAgo * HOUR;
  return {
    id: 7, ref: "INC-0007", title: "Lost laptop", description: "Stolen from a car.", status: "open", severity: "high",
    discovered_at: iso(discovered), occurred_at: null, data_categories: ["Contact details"], affected_count: 50, systems: [],
    likely_consequences: "", measures_taken: "", contact: "", individuals_notice_needed: null, regulator_notified_at: null,
    individuals_notified_at: null, source: {},
    clocks: {
      regulator: { due: iso(discovered + 72 * HOUR), done_at: null, state: "running", seconds_left: 0 },
      individuals: { due: iso(discovered + 144 * HOUR), done_at: null, state: "running", seconds_left: 0 },
      regulator_hours: 72, individuals_hours: 144,
    },
    events: [{ id: 1, at: iso(discovered), kind: "created", text: "Lost laptop", actor: "Omar" }],
    ...extra,
  };
}

describe("breach clocks", () => {
  it("an incident recorded 70 hours ago shows two hours left and is urgent", () => {
    const now = new Date();
    const clock: Clock = { due: iso(now.getTime() + 2 * HOUR), done_at: null, state: "running", seconds_left: null };
    expect(liveState(clock, now).state).toBe("urgent");
    render(<BreachClock label="Regulator" clock={clock} now={now} />);
    expect(screen.getByText("2 h 0 m left")).toBeInTheDocument();
    expect(screen.getByText("Urgent")).toBeInTheDocument();
  });

  it("an incident past the deadline shows as overdue", () => {
    const now = new Date();
    const clock: Clock = { due: iso(now.getTime() - 3 * HOUR - 5 * 60_000), done_at: null, state: "running", seconds_left: null };
    render(<BreachClock label="Regulator" clock={clock} now={now} />);
    expect(screen.getByText("Overdue by 3 h 5 m")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
  });

  it("shows warning below a day and done states", () => {
    const now = new Date();
    expect(liveState({ due: iso(now.getTime() + 20 * HOUR), done_at: null, state: "running", seconds_left: null }, now).state).toBe("warning");
    expect(liveState({ due: iso(now.getTime() + 30 * HOUR), done_at: null, state: "running", seconds_left: null }, now).state).toBe("running");
    expect(liveState({ due: iso(now.getTime() - HOUR), done_at: iso(now.getTime() - 2 * HOUR), state: "met", seconds_left: null }, now).state).toBe("met");
  });

  it("displays times in Cairo across midnight", () => {
    // 21:30 UTC on 18 Nov is 23:30 in Cairo (UTC+2); 22:30 UTC is already 19 Nov in Cairo
    expect(fmtDateTime("2026-11-18T21:30:00Z")).toBe("18 Nov 2026, 23:30");
    expect(fmtDateTime("2026-11-18T22:30:00Z")).toBe("19 Nov 2026, 00:30");
    expect(toCairoInput("2026-11-18T22:30:00Z")).toBe("2026-11-19T00:30");
  });

  it("lists incidents with live clocks", async () => {
    mockFetch({ "/api/auth/me": ME("auditor"), "/api/incidents": [incident(70)] });
    render(
      <AuthProvider>
        <MemoryRouter>
          <Incidents />
        </MemoryRouter>
      </AuthProvider>,
    );
    const card = (await screen.findByText("Lost laptop")).closest("li")!;
    expect(within(card).getByText("Urgent")).toBeInTheDocument();
    expect(within(card).getByText(/^2 h \d+ m left$|^1 h 59 m left$/)).toBeInTheDocument();
    expect(screen.queryByText("+ Record a breach")).toBeNull();
  });

  it("fills the notice template and offers notification actions", async () => {
    mockFetch({
      "/api/auth/me": ME("dpo", ["read", "incidents.write"]),
      "/api/incidents/7": incident(80),
      "/api/incidents/7/notice": { subject: "Personal data breach notification: Clinic (INC-0007)", body: "6. What happened: Stolen from a car.\n8. Number of people affected (estimate): 50", note: "Template drafted by Sijill", missing_fields: 3 },
    });
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/incidents/7"]}>
          <Routes>
            <Route path="/incidents/:id" element={<IncidentDetail />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Lost laptop" })).toBeInTheDocument();
    expect(screen.getAllByText("Overdue").length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/What happened: Stolen from a car/)).length).toBe(2);
    expect(screen.getAllByText("3 field(s) still to complete before sending").length).toBe(2);
    expect(screen.getByRole("button", { name: "Mark regulator notified" })).toBeInTheDocument();
  });
});
