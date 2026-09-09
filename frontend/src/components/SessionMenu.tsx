import { useEffect, useRef, useState } from "react";
import { ConfirmDialog, cx } from "./ui";
import { useResearch } from "../store/research";
import type { Session } from "../lib/types";

/**
 * 会话三点菜单:悬停显示 ⋮ 按钮,展开“置顶 / 删除”,
 * 删除需二次确认。供侧边栏最近对话与工作区会话列表复用。
 */
export function SessionMenu({
  session,
  onDeleted,
  className,
}: {
  session: Session;
  onDeleted?: (id: string) => void;
  className?: string;
}) {
  const { pinResearch, deleteResearch } = useResearch();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const togglePin = async () => {
    setOpen(false);
    try {
      await pinResearch(session.id, !session.pinned);
    } catch {
      /* 列表刷新会体现失败 */
    }
  };

  const del = async () => {
    setBusy(true);
    try {
      await deleteResearch(session.id);
      setConfirming(false);
      setOpen(false);
      onDeleted?.(session.id);
    } catch {
      /* 忽略,列表刷新会体现失败 */
    } finally {
      setBusy(false);
    }
  };

  const item = cx(
    "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12.5px]",
    "transition-colors duration-150",
  );

  return (
    <div ref={ref} className={cx("relative shrink-0", className)}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        title="更多操作"
        className={cx(
          "flex h-6 w-6 items-center justify-center rounded-md text-text-subtle",
          "transition-colors duration-150 hover:bg-surface-2 hover:text-text",
          open && "bg-surface-2 text-text",
        )}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="5" r="1.7" />
          <circle cx="12" cy="12" r="1.7" />
          <circle cx="12" cy="19" r="1.7" />
        </svg>
      </button>

      {open && (
        <div
          className={cx(
            "absolute right-0 top-7 z-30 w-[132px] rounded-xl border border-border bg-surface",
            "p-1 shadow-soft-lg animate-fade-up",
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <button onClick={togglePin} className={cx(item, "text-text hover:bg-surface-2")}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 17v5m-5-9.5V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v7.5l2.5 2.5h-13L7 12.5Z" />
            </svg>
            {session.pinned ? "取消置顶" : "置顶"}
          </button>
          <button
            onClick={() => {
              setOpen(false);
              setConfirming(true);
            }}
            className={cx(item, "text-danger hover:bg-danger/10")}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M3 6h18m-2 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m4 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
            </svg>
            删除
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        title="删除研究会话"
        message={
          <>
            确定删除会话「<span className="font-medium text-text">{session.query}</span>」吗?
            <br />
            报告、来源、证据与轨迹等数据将被一并清除,且不可恢复。
          </>
        }
        onConfirm={() => void del()}
        onCancel={() => setConfirming(false)}
        busy={busy}
      />
    </div>
  );
}

/** 置顶图钉(列表项标题前的小标记) */
export function PinnedMark({ className }: { className?: string }) {
  return (
    <svg
      className={cx("shrink-0 text-accent", className)}
      width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    >
      <path d="M12 17v5m-5-9.5V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v7.5l2.5 2.5h-13L7 12.5Z" />
    </svg>
  );
}
