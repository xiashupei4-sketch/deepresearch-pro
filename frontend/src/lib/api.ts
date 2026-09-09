import type {
  Evaluation,
  EvidenceItem,
  KbDocument,
  KbSearchHit,
  LlmSettings,
  LlmTestResult,
  Session,
  SourceItem,
  TraceEvent,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      // FastAPI 校验错误的 detail 是数组,取第一条可读消息
      detail = Array.isArray(body.detail) ? body.detail[0]?.msg || detail : body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createResearch: (query: string) =>
    request<Session>("/api/research", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  listSessions: (limit = 30) => request<Session[]>(`/api/research?limit=${limit}`),

  getSession: (id: string) => request<Session>(`/api/research/${id}`),

  getReport: (id: string) =>
    request<{ id: string; report: string | null; status: string; error: string | null }>(
      `/api/research/${id}/report`,
    ),

  getSources: (id: string) => request<SourceItem[]>(`/api/research/${id}/sources`),

  getEvidence: (id: string) => request<EvidenceItem[]>(`/api/research/${id}/evidence`),

  getEvaluation: (id: string) => request<Evaluation>(`/api/research/${id}/evaluation`),

  getTrace: (id: string) => request<TraceEvent[]>(`/api/research/${id}/trace`),

  listDocuments: () => request<KbDocument[]>("/api/knowledge/documents"),

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/knowledge/documents", { method: "POST", body: form }).then(
      (res) => {
        if (!res.ok) throw new Error("上传失败");
        return res.json() as Promise<KbDocument>;
      },
    );
  },

  deleteDocument: (id: string) =>
    request<{ deleted: string }>(`/api/knowledge/documents/${id}`, { method: "DELETE" }),

  searchKb: (query: string, top_k = 8) =>
    request<{ query: string; hits: KbSearchHit[] }>("/api/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k }),
    }),

  deleteResearch: (id: string) =>
    request<{ deleted: string }>(`/api/research/${id}`, { method: "DELETE" }),

  pinResearch: (id: string, pinned: boolean) =>
    request<Session>(`/api/research/${id}/pin`, {
      method: "PATCH",
      body: JSON.stringify({ pinned }),
    }),

  getLlmSettings: () => request<LlmSettings>("/api/settings/llm"),

  updateLlmSettings: (body: { api_key?: string; base_url?: string; model?: string; reset?: boolean }) =>
    request<LlmSettings>("/api/settings/llm", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  testLlmSettings: (body: { api_key?: string; base_url?: string; model?: string }) =>
    request<LlmTestResult>("/api/settings/llm/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

/** Open an SSE stream for live research events. Returns a close function. */
export function openEventStream(
  researchId: string,
  onEvent: (ev: TraceEvent) => void,
  onError?: () => void,
): () => void {
  const es = new EventSource(`/api/research/${researchId}/events`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as TraceEvent);
    } catch {
      /* ignore malformed frames */
    }
  };
  es.onerror = () => onError?.();
  return () => es.close();
}
