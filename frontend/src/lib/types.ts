export type SessionStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface Task {
  id: string;
  title: string;
  description: string;
  task_type: string;
  priority: number;
  dependencies: string[];
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  order_index: number;
}

export interface Session {
  id: string;
  query: string;
  status: SessionStatus;
  objective: string | null;
  iteration: number;
  pinned?: boolean;
  report: string | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  tasks_count?: number;
  tasks?: Task[];
}

export interface LlmSettings {
  mode: "mock" | "openai-compatible";
  base_url: string;
  model: string;
  has_api_key: boolean;
}

export interface LlmTestResult {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  reply?: string;
  error?: string;
  embedding_ok?: boolean;
  embedding_error?: string | null;
}

export interface TraceEvent {
  id: string;
  agent: string;
  event_type: string;
  status: string;
  task_id: string | null;
  input_summary: string | null;
  output_summary: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface SourceItem {
  id: string;
  title: string;
  url: string | null;
  source_type: string;
  domain: string | null;
  claims_used: number;
  created_at: string | null;
}

export interface EvidenceItem {
  id: string;
  source_id: string;
  content: string;
  relevance_score: number;
}

export interface Judge {
  completeness: number;
  relevance: number;
  evidence_quality: number;
  structure: number;
  issues: string[];
}

export interface Evaluation {
  overall_score: number;
  task_completion: number;
  citation_score: number;
  evidence_score: number;
  retrieval_score: number | null;
  tool_success_rate: number | null;
  latency_ms: number | null;
  judge: Judge;
  issues: string[];
  strengths: string[];
  recommendations: string[];
}

export interface KbDocument {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  error: string | null;
  created_at: string | null;
}

export interface KbSearchHit {
  id: string;
  text: string;
  score: number;
  metadata: Record<string, unknown>;
}
