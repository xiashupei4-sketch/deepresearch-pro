import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useResearch } from "../store/research";
import type { Task, TraceEvent } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Spinner,
  StatusBadge,
  cx,
} from "../components/ui";
import { AGENT_ZH, EVENT_TYPE_ZH, STATUS_ZH, TASK_TYPE_ZH, zh } from "../lib/labels";
import { Markdown } from "../components/Markdown";
import { PinnedMark, SessionMenu } from "../components/SessionMenu";

/* =============================================================== tasks tab */

const TASK_TONE: Record<string, "success" | "accent" | "neutral" | "danger"> = {
  COMPLETED: "success",
  RUNNING: "accent",
  PENDING: "neutral",
  FAILED: "danger",
};

function TaskRow({ task }: { task: Task }) {
  return (
    <div
      className={cx(
        "group flex items-start gap-2.5 rounded-lg border border-transparent px-2.5 py-2",
        "transition-all duration-200 ease-out-soft hover:border-border hover:bg-surface-2",
      )}
    >
      <span
        className={cx(
          "mt-[3px] inline-block h-2 w-2 shrink-0 rounded-full",
          task.status === "COMPLETED" && "bg-success",
          task.status === "RUNNING" && "bg-accent animate-pulse-dot",
          task.status === "PENDING" && "bg-border-hover",
          task.status === "FAILED" && "bg-danger",
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span
            className={cx(
              "truncate text-[12.5px] font-medium",
              task.status === "PENDING" ? "text-text-muted" : "text-text",
            )}
          >
            {task.title}
          </span>
          <span className="shrink-0 font-mono text-[10.5px] text-text-subtle">
            {task.id}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-1.5">
          <Badge tone={TASK_TONE[task.status] || "neutral"}>{zh(STATUS_ZH, task.status)}</Badge>
          <Badge>{zh(TASK_TYPE_ZH, task.task_type)}</Badge>
          {task.dependencies.length > 0 && (
            <span className="text-[10.5px] text-text-subtle">
              ← {task.dependencies.join(", ")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================================================== trace feed */

const EVENT_COLOR: Record<string, string> = {
  TASK_START: "border-l-accent",
  TASK_END: "border-l-success",
  TOOL_CALL: "border-l-warning",
  TOOL_RESULT: "border-l-warning/50",
  REFLECTION: "border-l-accent",
  REPLAN: "border-l-danger",
  EVALUATION: "border-l-success",
  REPORT_GENERATED: "border-l-success",
  ERROR: "border-l-danger",
  AGENT_START: "border-l-accent/50",
  AGENT_END: "border-l-border-hover",
  STAGE: "border-l-border",
};

function TraceRow({ ev }: { ev: TraceEvent }) {
  return (
    <div
      className={cx(
        "border-l-2 py-1 pl-2.5 pr-2 transition-colors duration-200 hover:bg-surface-2",
        EVENT_COLOR[ev.event_type] || "border-l-border",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11.5px] font-medium text-text">
          {zh(AGENT_ZH, ev.agent)}
          <span className="ml-1.5 font-normal text-text-subtle">{zh(EVENT_TYPE_ZH, ev.event_type)}</span>
        </span>
        {ev.duration_ms != null && (
          <span className="font-mono text-[10px] text-text-subtle">{ev.duration_ms}ms</span>
        )}
      </div>
      {(ev.input_summary || ev.output_summary) && (
        <div className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-text-subtle">
          {ev.output_summary || ev.input_summary}
        </div>
      )}
    </div>
  );
}

/* ==================================================================== main */

type RightTab = "report" | "evaluation" | "sources" | "evidence";

const TAB_LABEL: Record<RightTab, string> = {
  report: "报告",
  evaluation: "评估",
  sources: "来源",
  evidence: "证据",
};

export function WorkspacePage() {
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const {
    sessions, refreshSessions, openSession, current, currentId, detailLoading,
    report, sources, evidence, evaluation, events, liveEvents, createResearch,
  } = useResearch();

  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState<RightTab>("report");

  useEffect(() => {
    void refreshSessions();
    if (routeId) void openSession(routeId);
    return () => undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? sessions.filter((s) => s.query.toLowerCase().includes(q)) : sessions;
  }, [sessions, filter]);

  const allEvents = useMemo(() => {
    const seen = new Set(events.map((e) => e.id));
    return [...events, ...liveEvents.filter((e) => !seen.has(e.id))];
  }, [events, liveEvents]);

  const tasks: Task[] = current?.tasks || [];
  const doneCount = tasks.filter((t) => t.status === "COMPLETED").length;
  const running = current?.status === "RUNNING" || current?.status === "PENDING";

  const newResearch = async () => {
    const q = window.prompt("研究问题");
    if (!q?.trim()) return;
    try {
      const id = await createResearch(q.trim());
      navigate(`/workspace/${id}`);
    } catch {
      /* surfaced via status */
    }
  };

  return (
    <div className="grid h-full grid-cols-[240px_minmax(0,1fr)_minmax(0,1.15fr)] divide-x divide-border">
      {/* ------------------------------------------------ column 1: sessions */}
      <div className="flex min-h-0 flex-col">
        <div className="flex items-center justify-between gap-2 px-3 pt-3.5 pb-2">
          <h2 className="text-[13px] font-semibold">会话列表</h2>
          <Button size="sm" variant="outline" onClick={() => void newResearch()}>
            + 新建
          </Button>
        </div>
        <div className="px-3 pb-2">
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="筛选…"
            className="h-8 text-[12.5px]"
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {filtered.map((s) => (
            <div
              key={s.id}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/workspace/${s.id}`)}
              onKeyDown={(e) => e.key === "Enter" && navigate(`/workspace/${s.id}`)}
              className={cx(
                "group mb-0.5 w-full cursor-pointer rounded-lg px-2.5 py-2 text-left transition-all duration-200 ease-out-soft",
                s.id === currentId
                  ? "bg-accent-soft"
                  : "hover:bg-surface-2",
              )}
            >
              <div className="flex items-center gap-1.5">
                {s.pinned && <PinnedMark />}
                <div
                  className={cx(
                    "min-w-0 flex-1 truncate text-[12.5px] font-medium",
                    s.id === currentId ? "text-accent" : "text-text",
                  )}
                >
                  {s.query}
                </div>
                <SessionMenu session={s} className="opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
              </div>
              <div className="mt-1 flex items-center gap-1.5">
                <StatusBadge status={s.status} />
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-2 py-6 text-center text-[12px] text-text-subtle">
              暂无会话
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------- column 2: run + trace */}
      <div className="flex min-h-0 flex-col">
        {!current ? (
          detailLoading ? (
            <div className="flex flex-1 items-center justify-center text-text-subtle">
              <Spinner />
            </div>
          ) : (
            <EmptyState
              title="选择一个研究会话"
              hint="从左侧选择会话,或返回首页发起新研究。"
            />
          )
        ) : (
          <>
            {/* header */}
            <div className="border-b border-border px-4 py-3.5">
              <div className="flex items-start justify-between gap-3">
                <h1 className="min-w-0 flex-1 text-[15px] font-semibold leading-snug tracking-tight">
                  {current.query}
                </h1>
                <StatusBadge status={current.status} />
              </div>
              <div className="mt-1.5 flex items-center gap-3 text-[11.5px] text-text-subtle">
                <span className="font-mono">{current.id.slice(0, 8)}</span>
                <span>第 {current.iteration} 轮迭代</span>
                <span>
                  {doneCount}/{tasks.length} 个任务
                </span>
                {running && (
                  <span className="inline-flex items-center gap-1 text-accent">
                    <Spinner className="h-3 w-3" /> 执行中…
                  </span>
                )}
              </div>
              {current.status === "FAILED" && current.error && (
                <div className="mt-2 rounded-lg bg-danger/10 px-2.5 py-1.5 text-[12px] text-danger">
                  {current.error}
                </div>
              )}
            </div>

            {/* progress bar */}
            <div className="h-[3px] w-full bg-surface-2">
              <div
                className="h-full bg-accent transition-all duration-500 ease-out-soft"
                style={{ width: tasks.length ? `${(doneCount / tasks.length) * 100}%` : "0%" }}
              />
            </div>

            {/* plan */}
            <div className="px-3 pt-3">
              <div className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-text-subtle">
                研究计划
              </div>
              <div className="flex flex-col">
                {tasks.map((t) => (
                  <TaskRow key={t.id} task={t} />
                ))}
                {tasks.length === 0 && (
                  <div className="px-2.5 py-3 text-[12px] text-text-subtle">
                    {running ? "规划中…" : "暂无任务记录。"}
                  </div>
                )}
              </div>
            </div>

            {/* live trace */}
            <div className="mt-3 flex min-h-0 flex-1 flex-col px-3 pb-3">
              <div className="mb-1.5 flex items-center justify-between px-1">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-text-subtle">
                  实时轨迹
                </span>
                {running && (
                  <span className="inline-flex items-center gap-1 text-[10.5px] text-accent">
                    <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" />
                    实时推送中
                  </span>
                )}
              </div>
              <Card className="min-h-0 flex-1 overflow-y-auto py-1">
                {allEvents.length === 0 ? (
                  <div className="px-3 py-4 text-[12px] text-text-subtle">等待事件…</div>
                ) : (
                  [...allEvents].reverse().map((ev) => <TraceRow key={ev.id} ev={ev} />)
                )}
              </Card>
            </div>
          </>
        )}
      </div>

      {/* ------------------------------------------ column 3: artifacts */}
      <div className="flex min-h-0 flex-col">
        {current ? (
          <>
            <div className="flex items-center gap-1 border-b border-border px-3 py-2">
              {(Object.keys(TAB_LABEL) as RightTab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cx(
                    "rounded-lg px-2.5 py-1.5 text-[12.5px] font-medium transition-all duration-200 ease-out-soft",
                    tab === t
                      ? "bg-surface-2 text-text"
                      : "text-text-subtle hover:text-text",
                  )}
                >
                  {TAB_LABEL[t]}
                  {t === "sources" && sources.length > 0 && (
                    <span className="ml-1 text-[10.5px] text-text-subtle">{sources.length}</span>
                  )}
                  {t === "evidence" && evidence.length > 0 && (
                    <span className="ml-1 text-[10.5px] text-text-subtle">{evidence.length}</span>
                  )}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              {tab === "report" &&
                (report ? (
                  <Markdown source={report} />
                ) : (
                  <EmptyState
                    title={running ? "写作完成后将生成报告" : "暂无报告"}
                    icon={<Spinner className="h-4 w-4" />}
                  />
                ))}

              {tab === "evaluation" &&
                (evaluation ? (
                  <div className="flex flex-col gap-4 animate-fade-up">
                    <Card className="flex items-center gap-5 p-4">
                      <div>
                        <div className="text-[32px] font-semibold leading-none tracking-tight text-accent">
                          {Math.round(evaluation.overall_score)}
                        </div>
                        <div className="mt-1 text-[11px] text-text-subtle">综合评分</div>
                      </div>
                      <div className="grid flex-1 grid-cols-2 gap-x-6 gap-y-2.5">
                        {[
                          ["任务完成度", evaluation.task_completion],
                          ["引用得分", evaluation.citation_score],
                          ["证据质量", evaluation.evidence_score],
                          ["评审均分",
                            (evaluation.judge.completeness + evaluation.judge.relevance +
                              evaluation.judge.evidence_quality + evaluation.judge.structure) / 4],
                        ].map(([label, v]) => (
                          <Meter key={label as string} label={label as string} value={v as number} />
                        ))}
                      </div>
                    </Card>
                    {evaluation.issues.length > 0 && (
                      <Section title="问题" items={evaluation.issues} tone="warning" />
                    )}
                    {evaluation.strengths.length > 0 && (
                      <Section title="优势" items={evaluation.strengths} tone="success" />
                    )}
                    {evaluation.recommendations.length > 0 && (
                      <Section title="建议" items={evaluation.recommendations} tone="accent" />
                    )}
                    {evaluation.latency_ms != null && (
                      <div className="text-[11.5px] text-text-subtle">
                        端到端时延 · {(evaluation.latency_ms / 1000).toFixed(1)} 秒
                      </div>
                    )}
                  </div>
                ) : (
                  <EmptyState title="评估尚未生成" />
                ))}

              {tab === "sources" && (
                <div className="flex flex-col gap-1.5">
                  {sources.map((s) => (
                    <Card key={s.id} className="px-3 py-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[12.5px] font-medium">{s.title}</span>
                        <Badge tone={s.claims_used > 0 ? "accent" : "neutral"}>
                          {s.claims_used} 处引用
                        </Badge>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-[11px] text-text-subtle">
                        <Badge>{s.source_type}</Badge>
                        <span className="truncate">{s.domain || s.url}</span>
                      </div>
                    </Card>
                  ))}
                  {sources.length === 0 && <EmptyState title="未收集到来源" />}
                </div>
              )}

              {tab === "evidence" && (
                <div className="flex flex-col gap-1.5">
                  {evidence.map((ev, i) => (
                    <Card key={ev.id} className="px-3 py-2.5">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="font-mono text-[10.5px] text-text-subtle">
                          E{i + 1} · {ev.id.slice(0, 14)}
                        </span>
                        <span className="font-mono text-[10.5px] text-accent">
                          {ev.relevance_score.toFixed(3)}
                        </span>
                      </div>
                      <p className="line-clamp-3 text-[12px] leading-5 text-text-muted">
                        {ev.content}
                      </p>
                    </Card>
                  ))}
                  {evidence.length === 0 && <EmptyState title="暂无证据" />}
                </div>
              )}
            </div>
          </>
        ) : (
          <EmptyState title="未选择会话" />
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- helpers */

function Meter({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[11.5px]">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono text-text-subtle">{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-all duration-700 ease-out-soft"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function Section({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "warning" | "success" | "accent";
}) {
  return (
    <Card className="p-3.5">
      <div className="mb-2 flex items-center gap-2">
        <Badge tone={tone}>{title}</Badge>
      </div>
      <ul className="ml-4 list-disc space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-[12.5px] leading-5 text-text-muted">
            {it}
          </li>
        ))}
      </ul>
    </Card>
  );
}
