import type { Basis, ReqStatus } from "./components/ui";

export interface Bi {
  en: string;
  ar: string;
}

export interface CheckSummary {
  check_id: string;
  status: "PASS" | "FAIL" | null;
  passing: number;
  failing: number;
  failing_resources: string[];
  last_observed: string | null;
  title?: string;
  provider?: string;
  severity?: string;
}

export type Reason = "from_answer" | "capped_by_failing_checks" | "derived_from_checks" | "na_overridden_by_failing_checks" | "not_assessed";

export interface ReqResult {
  id: string;
  label: string;
  area_id: string;
  title: Bi;
  weight: number;
  technical: boolean;
  status: ReqStatus;
  basis: Basis;
  value: number | null;
  attested_status: ReqStatus | null;
  automated_status: ReqStatus | null;
  reason: Reason;
  capped: boolean;
  stale: boolean;
  evidence_at: string | null;
  failing_checks: number;
  passing_checks: number;
  verified: boolean;
  checks: CheckSummary[];
}

export interface AreaResult {
  id: string;
  label: string;
  title: Bi;
  overview: Bi;
  score: number | null;
  weight: number;
  by_status: Partial<Record<ReqStatus, number>>;
  by_basis: Partial<Record<Basis, number>>;
}

export interface Counts {
  total: number;
  by_status: Partial<Record<ReqStatus, number>>;
  by_basis: Partial<Record<Basis, number>>;
  stale: number;
  capped: number;
  technical_total: number;
  technical_automated: number;
  failing_checks: number;
}

export interface Posture {
  overall: number | null;
  counts: Counts;
  stale_days: number;
  areas: AreaResult[];
  requirements: ReqResult[];
}

export interface Regression {
  check_id: string;
  resource: string;
  region: string;
  title: string;
  message: string;
  severity: string;
  requirements: string[];
  run_id: number;
  previous_run_id: number | null;
  target: string;
  provider: string;
  detected_at: string;
}

export interface Deadline {
  id: number;
  kind: string;
  title: string;
  due: string;
  days_left: number;
}

export interface BreachClock {
  id: number;
  title: string;
  status: string;
  regulator_due: string;
  regulator_state: string;
  regulator_done: boolean;
  individuals_due: string | null;
  individuals_state: string;
}

export interface Dashboard {
  overall: number | null;
  counts: Counts;
  areas: AreaResult[];
  trend: { at: string; overall: number; reason: string }[];
  gaps: { id: string; label: string; title: Bi; status: ReqStatus; basis: Basis; weight: number; area_id: string; failing_checks: number; capped: boolean; stale: boolean }[];
  gap_total: number;
  regressions: Regression[];
  targets: { provider: string; target: string; run_id: number; started_at: string; passed: number; failed: number }[];
  last_run: string | null;
  runs_total: number;
  deadlines: Deadline[];
  breaches: BreachClock[];
  features?: { obligations: boolean; incidents: boolean };
  organization?: { name: string; name_ar?: string; demo?: boolean } | null;
}

export interface Run {
  id: number;
  source: string;
  provider: string;
  target: string;
  started_at: string;
  imported_at: string;
  filename: string;
  file_sha256: string;
  total: number;
  passed: number;
  failed: number;
  manual: number;
  unmapped: number;
  regressions?: number;
  fixed?: number;
  previous_run_id?: number | null;
}

export interface DiffItem {
  check_id: string;
  resource: string;
  region: string;
  title: string;
  message: string;
  severity: string;
  requirements: string[];
}

export interface RunDetail extends Run {
  diff: { run_id: number; previous_run_id: number | null; regressions: DiffItem[]; fixed: DiffItem[]; new_failures: DiffItem[] };
  results: (DiffItem & { status: "PASS" | "FAIL" | "MANUAL"; observed_at: string; sha256: string })[];
}

export interface RequirementDetail {
  requirement: {
    id: string;
    label: string;
    area_id: string;
    title: Bi;
    statement: Bi;
    question: Bi;
    guidance: Bi;
    weight: number;
    technical: boolean;
    verified: boolean;
    source_status: string;
    source: string;
  };
  area: { id: string; score: number | null; label: string; title: Bi; weight: number };
  result: ReqResult;
  stale_days: number;
  contribution: { points: number; of: number; area_weight: number } | null;
  answer: { status: ReqStatus; note: string; updated_at: string; updated_by: string | null } | null;
  checks: CheckSummary[];
  evidence: { id: number; filename: string; size: number; sha256: string; content_type: string; uploaded_at: string; description: string }[];
}
