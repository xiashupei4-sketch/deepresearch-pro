import { useEffect } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useTheme } from "../store/theme";
import { STATUS_ZH, zh } from "../lib/labels";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ Button */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline" | "danger";
  size?: "sm" | "md";
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-xl font-medium transition-all duration-200 ease-out-soft",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-[12.5px]" : "h-9 px-3.5 text-[13.5px]",
        variant === "primary" &&
          "bg-accent text-white shadow-soft hover:bg-accent-hover active:scale-[0.98]",
        variant === "ghost" && "text-text-muted hover:bg-surface-2 hover:text-text",
        variant === "outline" &&
          "border border-border bg-surface text-text hover:border-border-hover active:scale-[0.98]",
        variant === "danger" &&
          "bg-danger/10 text-danger hover:bg-danger/20 active:scale-[0.98]",
        className,
      )}
      {...rest}
    />
  );
}

/* -------------------------------------------------------------------- Card */

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "rounded-xl border border-border bg-surface shadow-soft transition-colors duration-200",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------- Badge */

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium leading-4",
        tone === "neutral" && "bg-surface-2 text-text-muted",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "success" && "bg-success/10 text-success",
        tone === "warning" && "bg-warning/10 text-warning",
        tone === "danger" && "bg-danger/10 text-danger",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    COMPLETED: "bg-success",
    RUNNING: "bg-accent animate-pulse-dot",
    PENDING: "bg-text-subtle",
    FAILED: "bg-danger",
  };
  return (
    <span
      className={cx("inline-block h-1.5 w-1.5 shrink-0 rounded-full", map[status] || "bg-text-subtle")}
    />
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "COMPLETED"
      ? "success"
      : status === "RUNNING"
        ? "accent"
        : status === "FAILED"
          ? "danger"
          : "neutral";
  return (
    <Badge tone={tone}>
      <StatusDot status={status} />
      {zh(STATUS_ZH, status)}
    </Badge>
  );
}

/* ------------------------------------------------------------------ Spinner */

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        "inline-block h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent",
        className,
      )}
      style={{ animationDuration: "0.8s" }}
    />
  );
}

/* -------------------------------------------------------------------- Input */

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "h-9 w-full rounded-xl border border-border bg-surface px-3 text-[13.5px] text-text",
        "placeholder:text-text-subtle transition-colors duration-200",
        "hover:border-border-hover focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20",
        className,
      )}
      {...rest}
    />
  );
}

/* --------------------------------------------------------------- EmptyState */

export function EmptyState({
  icon,
  title,
  hint,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-12 text-center animate-fade-up">
      {icon && <div className="mb-1 text-text-subtle">{icon}</div>}
      <div className="text-[13.5px] font-medium text-text">{title}</div>
      {hint && <div className="max-w-xs text-[12.5px] leading-5 text-text-subtle">{hint}</div>}
    </div>
  );
}

/* -------------------------------------------------------------- ThemeToggle */

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      title="切换主题"
      className={cx(
        "flex h-7 w-7 items-center justify-center rounded-lg text-text-muted",
        "transition-colors duration-200 hover:bg-surface-2 hover:text-text",
      )}
    >
      {theme === "dark" ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
        </svg>
      )}
    </button>
  );
}

/* -------------------------------------------------------------------- Modal */

export function Modal({
  open,
  title,
  onClose,
  children,
  width = 420,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 animate-fade-up"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      // 阻止冒泡:弹窗可能嵌套在可点击条目(如会话列表项)内,点击不应触发父级跳转
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="w-full rounded-2xl border border-border bg-surface shadow-soft-lg"
        style={{ maxWidth: width }}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <h3 className="text-[14px] font-semibold text-text">{title}</h3>
          <button
            onClick={onClose}
            title="关闭"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-text-muted transition-colors duration-200 hover:bg-surface-2 hover:text-text"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ ConfirmDialog */

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "确认删除",
  cancelLabel = "取消",
  onConfirm,
  onCancel,
  busy = false,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return (
    <Modal open={open} title={title} onClose={onCancel} width={380}>
      <div className="text-[13px] leading-6 text-text-muted">{message}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={busy}>
          {busy ? <Spinner /> : null}
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
