export type Activity = "learn" | "recall" | "implement" | "transfer";
export type Assistance = "none" | "minor" | "guided" | "substantial";
export interface Problem {
  id: string;
  title: string;
  prompt: string;
  signature: string;
  constraints: string[];
  examples: {
    inputs: Record<string, unknown>;
    output: unknown;
    explanation?: string;
  }[];
  topic?: string;
  related_url?: string;
}
export interface Finding {
  dimension:
    "recall" | "explanation" | "constraints" | "misconception" | "repair";
  value: "success" | "failure" | "unknown";
  evidence: string;
  explanation: string;
  source?: string;
}
export interface Session {
  session_id: string;
  revision: number;
  code_digest: string;
  activity: Activity;
  assessment_mode?: "independent" | "practice";
  initial_reasoning?: { approach: string; quality: string };
  code: string | null;
  problem: Problem;
  phase: string;
  phase_started_at: string | null;
  elapsed_seconds: number;
  budget_minutes: number;
  break_suggested: boolean;
  budget_reached: boolean;
  revealed_hints?: string[];
  worked_example?: string;
  worked_explanation?: string;
  timing_uncertain?: { reason: string };
  assessment_before_help?: { status: string };
}
export interface Practice {
  practice_id: string;
  status: string;
  index: number;
  budget_minutes: number;
  elapsed_seconds: number;
  stages: { type: string; label: string; status: string; error_id?: string }[];
}
export interface CheckResult {
  status: string;
  code_digest?: string;
  all_passed?: boolean;
  passed_cases?: number;
  total_cases?: number;
  message?: string;
  checkpoint_count?: number;
  public_failures?: { example: number; error: string }[];
}
export interface StudyState {
  session: Session | null;
  practice: Practice | null;
  sync: { status: string; message: string };
  check: CheckResult | null;
  repair: {
    error_id: string;
    application: string;
    started_at: string | null;
    revision?: number;
    check?: { status: string; message?: string };
    coach_review?: { value: string; explanation?: string };
  } | null;
  completion: {
    session_id: string;
    message: string;
    published: boolean;
  } | null;
  unpublished_count: number;
  remote_attempts: { branch: string }[];
}
export interface Repair {
  event_id: string;
  skill: string;
  repair_prompt: string;
  eligible: boolean;
}
export interface Queue {
  main: Problem | null;
  activity: Activity;
  reason: string;
  minutes: number;
  due: Problem[];
  postponed: Problem[];
  repairs: Repair[];
  support: Problem[];
  short_recall: Problem[];
  weekend: boolean;
}
export interface Metric {
  passed: number;
  total: number;
  rate: number | null;
}
export interface Progress {
  cohort: {
    delayed: Metric;
    unseen: Metric;
    coaching_interruptions: number;
    coaching_turns: number;
    help_escalations: number;
    latency_median_seconds: number | null;
    latency_samples: number;
  };
  independent: Metric;
  unaided: Metric;
  delayed: Metric;
  unseen: Metric;
  assistance: Record<Assistance, number>;
  timing_seconds: Record<string, number>;
  recorded_total_minutes: number;
  baseline_sessions: number;
  baseline_target: number;
  administration_median_minutes: number | null;
  administration_target_met: boolean | null;
  legacy_timing_incomplete: boolean;
  topics: {
    id: string;
    name?: string;
    title?: string;
    available?: boolean;
    ready?: boolean;
    retained?: boolean;
    [key: string]: unknown;
  }[];
}
export interface Evaluation {
  session_id: string;
  revision: number;
  recommended_rating: string;
  recall_outcome: string;
  tests_passed: boolean;
  tests_current: boolean;
  active_minutes: number;
  assistance_level: Assistance;
  rating_rationale: string;
  evidence: Finding[];
}
export interface CoachMessage {
  request_id: string;
  session_id: string;
  kind: string;
  message: string;
  status: string;
  created_at: string;
  reply?: string;
  error?: string;
  diff?: string;
  findings?: Finding[];
  takeaway?: string;
  code_digest: string;
  assistance?: Assistance;
  application_revision?: number;
  proposal_applied?: boolean;
}
export interface CoachStatus {
  connection: string;
  message: string;
  auth_url: string | null;
  usage: {
    known: boolean;
    blocked: boolean;
    conserving: boolean;
    remaining: number | null;
    windows: { remaining: number; resets_at?: number }[];
  };
  models: { id: string; name: string; efforts: string[] }[];
  preferences: {
    automatic: boolean;
    approach: boolean;
    check: boolean;
    model: string | null;
    effort: string | null;
  };
  requests: CoachMessage[];
  active_request: string | null;
}
