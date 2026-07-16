export interface User {
  userId: number;
  userName: string;
  employeeId: number | null;
  employeeName: string | null;
  lawfirmName: string | null;
  canApprove: boolean;
}

export interface CaseRow {
  id: number;
  no: string | null;
  preNo: string | null;
  status: number;
  statusName: string;
  shouliDate: string | null;
  createTime: string | null;
  caseCategoryName: string | null;
  baseTypeName: string | null;
  causeAction: string | null;
  caseHeadName?: string | null;
  wtrNames: string | null;
  dsrNames: string | null;
  tosNames: string | null;
  empNames: string | null;
  chargeAmount: number | null;
  otherCharge: number | null;
  yishou: number | null;
  weishou: number | null;
}

export interface CaseListResponse {
  total: number;
  rows: CaseRow[];
}

export interface PendingResponse {
  filing: CaseRow[];
  closing: CaseRow[];
}

export interface AutomationStatus {
  enabled: boolean;
  mode: "shadow" | "active";
  shadow_remaining_seconds: number;
  poll_minutes: number;
  last_checked_at: string | null;
  last_error: string | null;
  events: {
    at: string;
    kind: string;
    case_id?: number;
    case_no?: string;
    action?: string;
    reasons?: string[];
    message?: string;
  }[];
}

export interface ConflictFinding {
  matched_name: string;
  relation: string;
  severity: string;
  case_id: number;
  case_no: string | null;
  status: number;
  status_name: string | null;
  wtr_names: string | null;
  tos_names: string | null;
  cause: string | null;
}

export interface DuplicateFinding {
  severity: string;
  relation: string;
  case_id: number;
  case_no: string | null;
  status: number | null;
  status_name: string | null;
  wtr_names: string | null;
  tos_names: string | null;
  cause: string | null;
  emp_names: string | null;
  principal_overlap: string[];
  opponent_overlap: string[];
  cause_match: boolean;
}

export interface DocTemplate {
  name: string;
  isSelected: boolean;
}

export interface DocTemplatesResponse {
  case_no: string | null;
  templates: DocTemplate[];
  principal_legal_persons: string[];
  principal_orgs: string[];
}

export interface DocDownloadSaved {
  template: string;
  path: string;
  size: number;
  valid_docx: boolean;
  auto_added: boolean;
}

export interface DocDownloadResponse {
  ok: boolean;
  case_no: string;
  dir: string;
  saved: DocDownloadSaved[];
  notes: string[];
}

export interface AssistantOverview {
  helper_app: boolean;
  wechat_evidence: boolean;
  python3: boolean;
  engines: { mineru: boolean; visionocr: boolean; legalocr: boolean };
  output_dir: string;
  wechat_output_dir: string;
}

export interface AssistantJob {
  id: string;
  kind: "convert" | "wechat" | "organize";
  title: string;
  status: "running" | "done" | "failed";
  detail: string;
  created_at: string;
  finished_at: string | null;
  inputs: string[];
  outputs: string[];
  log_tail: string;
  error: string | null;
}

export interface ApprovalReview {
  lawcase_id: number;
  case_no: string | null;
  status: number;
  status_name: string;
  base_type_name: string | null;
  non_litigation?: boolean;
  completeness: {
    result: string;
    missing: string[];
    warnings: string[];
    non_litigation?: boolean;
    criminal_case?: boolean;
  };
  cause: {
    result: string;
    cause_text: string | null;
    matches?: { id: number | null; name: string; is_leaf: boolean; is_root: boolean; path: string }[];
    blockers?: string[];
    warnings?: string[];
    suggestions?: string[];
  };
  conflict: {
    result: string;
    principals: string[];
    opponents: string[];
    blockers: string[];
    findings: ConflictFinding[];
    limitations: string[];
  };
  duplicate_filing: {
    result: string;
    blockers: string[];
    findings: DuplicateFinding[];
    limitations: string[];
  };
  fee_explanation: {
    result: string;
    amount: number | null;
    memo: string | null;
    memo_amounts?: number[];
    blockers?: string[];
    non_litigation?: boolean;
    note?: string;
  };
  risk_charge: {
    result: string;
    verdict?: "preliminary_pass" | "issues_found";
    charge_method: string | null;
    scheme?: string | null;
    subject_amount: number | null;
    registered_fee?: number | null;
    scheme_amounts?: number[];
    graduated_cap: number | null;
    cap_breakdown?: { range: string; rate: string; portion: number; fee: number }[];
    prohibited_matches?: string[];
    issues?: string[];
    suggestions?: string[];
    notes?: string[];
    basis?: string;
  };
  gate_errors: string[];
  detail: Record<string, unknown>;
}
