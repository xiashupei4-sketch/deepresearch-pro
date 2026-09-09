import { create } from "zustand";
import { api, openEventStream } from "../lib/api";
import type {
  Evaluation,
  EvidenceItem,
  Session,
  SourceItem,
  TraceEvent,
} from "../lib/types";

interface ResearchState {
  sessions: Session[];
  currentId: string | null;
  current: Session | null;
  report: string | null;
  sources: SourceItem[];
  evidence: EvidenceItem[];
  evaluation: Evaluation | null;
  events: TraceEvent[];
  liveEvents: TraceEvent[];
  detailLoading: boolean;

  refreshSessions: () => Promise<void>;
  openSession: (id: string) => Promise<void>;
  closeSession: () => void;
  createResearch: (query: string) => Promise<string>;
  pinResearch: (id: string, pinned: boolean) => Promise<void>;
  deleteResearch: (id: string) => Promise<void>;
}

let pollTimer: number | null = null;
let closeStream: (() => void) | null = null;

export const useResearch = create<ResearchState>((set, get) => ({
  sessions: [],
  currentId: null,
  current: null,
  report: null,
  sources: [],
  evidence: [],
  evaluation: null,
  events: [],
  liveEvents: [],
  detailLoading: false,

  refreshSessions: async () => {
    try {
      set({ sessions: await api.listSessions() });
    } catch {
      /* backend offline */
    }
  },

  openSession: async (id) => {
    closeStream?.();
    closeStream = null;
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;

    set({
      currentId: id,
      current: null,
      report: null,
      sources: [],
      evidence: [],
      evaluation: null,
      events: [],
      liveEvents: [],
      detailLoading: true,
    });

    const loadAll = async () => {
      const id0 = get().currentId;
      if (!id0 || id0 !== id) return;
      const [session, report, sources, evidence, evaluation, trace] =
        await Promise.all([
          api.getSession(id),
          api.getReport(id),
          api.getSources(id).catch(() => []),
          api.getEvidence(id).catch(() => []),
          api.getEvaluation(id).catch(() => null),
          api.getTrace(id).catch(() => []),
        ]);
      if (get().currentId !== id) return;
      set({
        current: session,
        report: report.report,
        sources,
        evidence,
        evaluation,
        events: trace,
        detailLoading: false,
      });
    };

    await loadAll().catch(() => set({ detailLoading: false }));

    // live updates: SSE stream + status polling while the run is active
    closeStream = openEventStream(
      id,
      (ev) => {
        if (get().currentId !== id) return;
        set((s) => ({ liveEvents: [...s.liveEvents.slice(-400), ev] }));
        if (
          ev.event_type === "EVALUATION" ||
          ev.event_type === "REPORT_GENERATED" ||
          ev.event_type === "AGENT_END"
        ) {
          void loadAll();
          void get().refreshSessions();
        }
      },
      () => {
        /* stream closed — polling keeps UI fresh */
      },
    );

    pollTimer = window.setInterval(async () => {
      const cur = get().current;
      if (get().currentId !== id) return;
      if (cur && (cur.status === "COMPLETED" || cur.status === "FAILED")) {
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = null;
        return;
      }
      await loadAll().catch(() => undefined);
      void get().refreshSessions();
    }, 2500);
  },

  closeSession: () => {
    closeStream?.();
    closeStream = null;
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
    set({
      currentId: null,
      current: null,
      report: null,
      sources: [],
      evidence: [],
      evaluation: null,
      events: [],
      liveEvents: [],
    });
  },

  createResearch: async (query) => {
    const session = await api.createResearch(query);
    await get().refreshSessions();
    return session.id;
  },

  pinResearch: async (id, pinned) => {
    await api.pinResearch(id, pinned);
    await get().refreshSessions();
  },

  deleteResearch: async (id) => {
    await api.deleteResearch(id);
    if (get().currentId === id) {
      get().closeSession();
    }
    await get().refreshSessions();
  },
}));
