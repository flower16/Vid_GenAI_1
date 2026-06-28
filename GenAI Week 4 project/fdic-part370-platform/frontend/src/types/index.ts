export type ORCCode =
  | "SGL" | "JNT" | "TST" | "CRA" | "EBP" | "BUS"
  | "GOV1" | "GOV2" | "GOV3" | "MSA" | "PBA" | "DIT"
  | "ANC" | "BIA" | "DOE";

export interface Owner { party_id: string; name: string; ownership_pct?: number; }
export interface Beneficiary { party_id: string; name: string; interest_pct?: number; }
export interface Participant { party_id: string; name: string; vested_interest?: number; }

export interface Customer {
  customer_id: string;
  first_name: string;
  last_name: string;
  ssn_tin: string;
  customer_type?: string;
  address?: string;
  email?: string;
  phone?: string;
}

export interface Account {
  account_number: string;
  customer_id: string;
  product_type: string;
  balance: number;
  accrued_interest: number;
  hold_amount: number;
  orc: ORCCode;
  owners: Owner[];
  beneficiaries: Beneficiary[];
  participants: Participant[];
  // BUS (12 CFR 330.11) eligibility. null/undefined = independent activity
  // assumed; false = pass through to members; sole_proprietorship → owner's SGL.
  independent_activity?: boolean | null;
  sole_proprietorship?: boolean;
}

export interface CoverageResult {
  orc: ORCCode;
  aggregated_pi: string;
  coverage_limit: string;
  insured_amount: string;
  uninsured_amount: string;
  rationale: string;
  accounts_included: string[];
  evidence: Record<string, unknown>;
}

export interface ValidationFinding {
  code: string; severity: "PASS" | "WARNING" | "FAIL"; message: string; field?: string;
}

export interface PendingDecision {
  is_pending: boolean; reason?: string; account_number?: string; detail: string;
}

export interface DeterminationResponse {
  determination_id: string;
  customer_findings: ValidationFinding[];
  account_findings: ValidationFinding[];
  applicable_rules: Record<string, any>;
  orc_classification: Record<string, any>;
  coverage_results: CoverageResult[];
  pending_decisions: PendingDecision[];
  output_files: Record<string, any>;
  summary_report: any;
  eval_results: { name: string; status: string; detail: string }[];
  trace: any[];
}

export const ORC_OPTIONS: { code: ORCCode; label: string }[] = [
  { code: "SGL", label: "SGL — Single Ownership" },
  { code: "JNT", label: "JNT — Joint Ownership" },
  { code: "TST", label: "TST — Revocable Trust / POD" },
  { code: "CRA", label: "CRA — Certain Retirement Accounts" },
  { code: "EBP", label: "EBP — Employee Benefit Plan" },
  { code: "BUS", label: "BUS — Business / Corporation" },
  { code: "GOV1", label: "GOV1 — Public Unit (In-State)" },
  { code: "GOV2", label: "GOV2 — Public Unit (Out-of-State)" },
  { code: "GOV3", label: "GOV3 — Public Unit (Federal)" },
  { code: "MSA", label: "MSA — Mortgage Servicing Account" },
  { code: "PBA", label: "PBA — Public Bond Account" },
  { code: "DIT", label: "DIT — Deposit of an IDI" },
  { code: "ANC", label: "ANC — Annuity Contract" },
  { code: "BIA", label: "BIA — Bank Investment / Broker" },
  { code: "DOE", label: "DOE — Decedent's Estate" },
];
