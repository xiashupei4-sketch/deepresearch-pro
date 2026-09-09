import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ThemeToggle, cx } from "./ui";
import { PinnedMark, SessionMenu } from "./SessionMenu";
import { useResearch } from "../store/research";
import type { Session } from "../lib/types";

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso + "Z").getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

const ICON_STROKE = 1.8;

/* 彩色导航图标 —— 清言风格:每个入口一个专属配色的小图标 */
const NAV = [
  {
    to: "/",
    label: "首页",
    color: "#5b64c8",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={ICON_STROKE}>
        <path d="m3 10 9-7 9 7v9a2 2 0 0 1-2 2h-4v-6h-6v6H5a2 2 0 0 1-2-2v-9Z" />
      </svg>
    ),
  },
  {
    to: "/workspace",
    label: "工作区",
    color: "#8b5cf6",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={ICON_STROKE}>
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <path d="M9 3v18M9 9h12" />
      </svg>
    ),
  },
  {
    to: "/knowledge",
    label: "知识库",
    color: "#1f9d61",
    icon: (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={ICON_STROKE}>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4a2 2 0 0 0-2-2H6.5A2.5 2.5 0 0 0 4 4.5v15Z" />
        <path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />
      </svg>
    ),
  },
];

const PLUS_ICON = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={ICON_STROKE}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v8m-4-4h8" />
  </svg>
);

const PANEL_ICON = (expanded: boolean) => (
  <svg
    width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={ICON_STROKE} style={{ transform: expanded ? "none" : "scaleX(-1)" }}
  >
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M9.5 4v16" />
  </svg>
);

const LOGO_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

const USER_ICON = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" />
  </svg>
);

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessions, refreshSessions } = useResearch();
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem("dr.sidebar") !== "collapsed",
  );

  /* 会话列表轮询 —— 供侧边栏“最近对话”使用(全局唯一轮询点) */
  useEffect(() => {
    void refreshSessions();
    const t = window.setInterval(() => void refreshSessions(), 4000);
    return () => window.clearInterval(t);
  }, [refreshSessions]);

  const toggleSidebar = () => {
    setExpanded((e) => {
      localStorage.setItem("dr.sidebar", e ? "collapsed" : "expanded");
      return !e;
    });
  };

  const goHome = () => navigate("/");

  return (
    <div className="flex h-full">
      {/* ------------------------------------------------ 侧边栏(可折叠) */}
      <aside
        className={cx(
          "flex shrink-0 flex-col border-r border-border bg-bg",
          "transition-[width] duration-300 ease-out-soft",
          expanded ? "w-[250px]" : "w-[52px]",
        )}
      >
        {/* 头部:品牌 + 折叠按钮 */}
        <div
          className={cx(
            "flex items-center pt-4 pb-3",
            expanded ? "justify-between pl-4 pr-3" : "flex-col gap-3 px-2",
          )}
        >
          <button
            onClick={goHome}
            title="DeepResearch"
            className="flex h-8 min-w-8 items-center gap-2 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent text-white shadow-soft">
              {LOGO_ICON}
            </span>
            {expanded && (
              <span className="text-[13.5px] font-semibold tracking-tight animate-fade-up whitespace-nowrap">
                DeepResearch
              </span>
            )}
          </button>
          <button
            onClick={toggleSidebar}
            title={expanded ? "收起侧边栏" : "展开侧边栏"}
            className={cx(
              "flex h-7 w-7 items-center justify-center rounded-lg text-text-muted",
              "transition-colors duration-200 hover:bg-surface-2 hover:text-text",
            )}
          >
            {PANEL_ICON(expanded)}
          </button>
        </div>

        {/* 新对话 */}
        {expanded ? (
          <button
            onClick={goHome}
            className={cx(
              "mx-3 flex h-10 shrink-0 items-center gap-2 rounded-xl bg-surface-2 px-3",
              "text-[13px] font-medium text-text transition-all duration-200 ease-out-soft",
              "hover:bg-surface-2/70 active:scale-[0.98]",
            )}
          >
            {PLUS_ICON}
            新对话
          </button>
        ) : (
          <button
            onClick={goHome}
            title="新对话"
            className={cx(
              "mx-auto mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              "text-text-muted transition-colors duration-200 hover:bg-surface-2 hover:text-text",
            )}
          >
            {PLUS_ICON}
          </button>
        )}

        {/* 导航 */}
        <nav
          className={cx(
            "mt-3 flex shrink-0 flex-col",
            expanded ? "gap-0.5 px-3" : "items-center gap-1",
          )}
        >
          {NAV.map((item) =>
            expanded ? (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cx(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-all duration-200 ease-out-soft",
                    isActive
                      ? "bg-surface-2 font-medium text-text"
                      : "text-text-muted hover:bg-surface-2/60 hover:text-text",
                  )
                }
              >
                <span style={{ color: item.color }} className="shrink-0">
                  {item.icon}
                </span>
                {item.label}
              </NavLink>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                title={item.label}
                className={({ isActive }) =>
                  cx(
                    "flex h-8 w-8 items-center justify-center rounded-lg transition-colors duration-200",
                    isActive ? "bg-surface-2" : "hover:bg-surface-2/60",
                  )
                }
              >
                <span style={{ color: item.color }}>{item.icon}</span>
              </NavLink>
            ),
          )}
        </nav>

        {/* 最近对话 */}
        {expanded ? (
          <>
            <div className="px-4 pb-1.5 pt-5 text-[11.5px] text-text-subtle">最近对话</div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
              {sessions.length === 0 && (
                <div className="px-2.5 py-2 text-[12px] leading-5 text-text-subtle">
                  暂无对话,发起一次研究吧
                </div>
              )}
              {sessions.slice(0, 12).map((s: Session) => {
                const active = location.pathname === `/workspace/${s.id}`;
                return (
                  <div
                    key={s.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => navigate(`/workspace/${s.id}`)}
                    onKeyDown={(e) => e.key === "Enter" && navigate(`/workspace/${s.id}`)}
                    title={s.query}
                    className={cx(
                      "group flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-left",
                      "transition-colors duration-200",
                      active ? "bg-surface-2" : "hover:bg-surface-2/60",
                    )}
                  >
                    {s.pinned && <PinnedMark />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] text-text">{s.query}</span>
                      <span className="block truncate text-[11px] text-text-subtle">
                        {timeAgo(s.created_at)}
                      </span>
                    </span>
                    {(s.status === "RUNNING" || s.status === "FAILED") && (
                      <span
                        className={cx(
                          "h-1.5 w-1.5 shrink-0 rounded-full bg-danger group-hover:hidden",
                          s.status === "RUNNING" && "animate-pulse-dot",
                        )}
                      />
                    )}
                    <SessionMenu
                      session={s}
                      className="hidden group-hover:block"
                      onDeleted={() => {
                        /* 删除当前打开的会话时回到首页 */
                        if (location.pathname === `/workspace/${s.id}`) navigate("/");
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <button
            onClick={toggleSidebar}
            title="最近对话"
            className={cx(
              "mx-auto mt-4 flex h-8 w-8 items-center justify-center rounded-lg",
              "text-text-muted transition-colors duration-200 hover:bg-surface-2 hover:text-text",
            )}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={ICON_STROKE}>
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3.5 2" />
            </svg>
          </button>
        )}

        {/* 底部用户信息 */}
        <div
          className={cx(
            "mt-auto shrink-0 border-t border-border",
            expanded ? "flex items-center gap-2.5 px-3.5 py-3" : "flex flex-col items-center gap-1.5 py-3",
          )}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-hover text-white shadow-soft">
            {USER_ICON}
          </span>
          {expanded && (
            <span className="min-w-0 flex-1 animate-fade-up">
              <span className="block truncate text-[12.5px] font-medium text-text">本地用户</span>
              <span className="block truncate text-[11px] text-text-subtle">离线 · Mock 模式</span>
            </span>
          )}
          <ThemeToggle />
        </div>
      </aside>

      {/* ------------------------------------------------ 内容区 */}
      <main className="min-w-0 flex-1 overflow-hidden bg-surface">
        <Outlet />
      </main>
    </div>
  );
}
