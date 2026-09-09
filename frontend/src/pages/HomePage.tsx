import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useResearch } from "../store/research";
import { api } from "../lib/api";
import { Card, Spinner, cx } from "../components/ui";
import { LlmSettingsModal } from "../components/LlmSettingsModal";

const EXAMPLES = [
  "对比 RAG 系统中的混合检索与重排序技术路线",
  "调研多智能体编排框架的研究现状",
  "研究检索增强生成的效果评估方法",
];

/* 装饰图卡 —— 水墨风格(与整体黑白基调呼应);加载失败时回退为渐变卡 */
const ART_URL =
  "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=" +
  encodeURIComponent(
    "Traditional Chinese ink wash painting, powerful black bull with flowing golden mane galloping through clouds, white background, elegant bold brush strokes, minimalist composition, high contrast poster art",
  ) +
  "&image_size=square";

const UPLOAD_ACCEPT = ".pdf,.docx,.txt,.md";

export function HomePage() {
  const navigate = useNavigate();
  const { createResearch } = useResearch();
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [artOk, setArtOk] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "DeepResearch Pro";
  }, []);

  /* textarea 自适应高度,光标从左上角开始 */
  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const submit = async () => {
    const q = query.trim();
    if (!q || submitting) return;
    if (q.length < 8) {
      setError("研究问题请至少输入 8 个字,可参考下方示例");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const id = await createResearch(q);
      navigate(`/workspace/${id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setSubmitting(false);
    }
  };

  const flashHint = (tone: "success" | "danger", text: string) => {
    setHint({ tone, text });
    window.setTimeout(() => setHint(null), 3000);
  };

  const uploadFile = async (file: File) => {
    if (uploading) return;
    setUploading(true);
    try {
      const doc = await api.uploadDocument(file);
      flashHint("success", `「${doc.filename}」已上传至知识库,检索时将自动引用`);
    } catch (e) {
      flashHint("danger", String(e instanceof Error ? e.message : e) || "上传失败");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const pill = cx(
    "flex h-9 items-center gap-1.5 rounded-xl border bg-surface px-3.5 text-[13px]",
    "transition-all duration-200 ease-out-soft active:scale-[0.98]",
  );

  return (
    <div className="relative flex h-full flex-col overflow-y-auto">
      {/* 顶栏 */}
      <header className="flex shrink-0 items-center justify-between px-6 pt-4">
        <div className="text-[14px] font-semibold tracking-tight">DeepResearch</div>
        <span className="text-[11.5px] text-text-subtle">离线 · Mock 模式</span>
      </header>

      {/* 居中 Hero */}
      <div className="relative mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-6 pb-14">
        {/* 装饰图卡(≥768px 显示) */}
        <div className="animate-float absolute -top-2 right-0 hidden md:block">
          {artOk ? (
            <img
              src={ART_URL}
              onError={() => setArtOk(false)}
              alt="深度研究"
              className="h-[150px] w-[208px] rounded-2xl border border-black/10 object-cover shadow-soft-lg"
            />
          ) : (
            <div className="flex h-[150px] w-[208px] items-center justify-center rounded-2xl border border-black/10 bg-gradient-to-br from-zinc-900 via-zinc-800 to-zinc-600 shadow-soft-lg">
              <span className="text-[26px] text-amber-200/90">✦</span>
            </div>
          )}
        </div>

        <h1 className="animate-fade-up text-center text-[32px] font-semibold leading-snug tracking-tight">
          今天,想研究点什么? <span className="align-middle">🤔</span>
        </h1>

        {/* 大输入卡片:一个整体,文本从左上角开始 */}
        <Card
          className={cx(
            "mt-10 w-full animate-fade-up rounded-[24px] px-5 pb-3.5 pt-4",
            "transition-colors duration-200 focus-within:border-border-hover",
          )}
        >
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              autoResize();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void submit();
              }
            }}
            rows={2}
            placeholder="输入你想研究的问题…(Enter 发送,Shift+Enter 换行)"
            className={cx(
              "block w-full resize-none bg-transparent text-[14px] leading-6 text-text",
              "placeholder:text-text-subtle focus:outline-none",
            )}
            style={{ minHeight: 56 }}
            autoFocus
          />
          <div className="mt-3 flex items-center justify-between">
            <div className="flex items-center gap-1">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                title="上传文档到知识库"
                className={cx(
                  "flex h-8 w-8 items-center justify-center rounded-full text-text-muted",
                  "transition-colors duration-200 hover:bg-surface-2 hover:text-text",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                )}
              >
                {uploading ? (
                  <Spinner />
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="m21.4 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                )}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept={UPLOAD_ACCEPT}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void uploadFile(f);
                }}
              />
              <button
                onClick={() => setSettingsOpen(true)}
                title="API 配置"
                className={cx(
                  "flex h-8 w-8 items-center justify-center rounded-full text-text-muted",
                  "transition-colors duration-200 hover:bg-surface-2 hover:text-text",
                )}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
                </svg>
              </button>
            </div>
            <div className="flex items-center gap-3">
              <span
                title="引擎:Multi-Agent · Mock LLM(离线)"
                className="flex cursor-default items-center gap-1 text-[12.5px] text-text-muted"
              >
                深度研究
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </span>
              <button
                onClick={() => void submit()}
                disabled={!query.trim() || submitting}
                title="开始研究"
                className={cx(
                  "flex h-9 w-9 items-center justify-center rounded-full transition-all duration-200 ease-out-soft",
                  query.trim() && !submitting
                    ? "bg-text text-surface shadow-soft hover:opacity-85 active:scale-[0.94]"
                    : "cursor-not-allowed bg-surface-2 text-text-subtle",
                )}
              >
                {submitting ? (
                  <Spinner />
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                    <path d="M12 19V5m-7 7 7-7 7 7" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </Card>

        {error && <div className="mt-2.5 text-[12.5px] text-danger">{error}</div>}
        {hint && (
          <div
            className={cx(
              "mt-2.5 text-[12.5px] animate-fade-up",
              hint.tone === "success" ? "text-success" : "text-danger",
            )}
          >
            {hint.text}
          </div>
        )}

        {/* 功能胶囊 */}
        <div className="mt-9 flex animate-fade-up flex-wrap items-center justify-center gap-2.5">
          <button
            onClick={() => textareaRef.current?.focus()}
            className={cx(pill, "border-accent/30 bg-accent-soft text-accent")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3Z" />
            </svg>
            深度研究
          </button>
          <button onClick={() => navigate("/workspace")} className={cx(pill, "border-border text-text hover:border-border-hover")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
              <path d="M14 3v5h5M9 13h6m-6 4h6" />
            </svg>
            研究报告
          </button>
          <button onClick={() => navigate("/knowledge")} className={cx(pill, "border-border text-text hover:border-border-hover")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4a2 2 0 0 0-2-2H6.5A2.5 2.5 0 0 0 4 4.5v15Z" />
              <path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />
            </svg>
            知识库
          </button>
        </div>

        {/* 示例问题(默认展示) */}
        <div className="mt-3.5 flex animate-fade-up flex-wrap justify-center gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => {
                setQuery(ex);
                requestAnimationFrame(autoResize);
              }}
              className={cx(
                "rounded-full border border-border bg-surface px-3 py-1.5 text-left text-[12.5px] text-text-muted",
                "transition-all duration-200 ease-out-soft hover:border-border-hover hover:text-text active:scale-[0.98]",
              )}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* 底部说明 */}
      <footer className="shrink-0 pb-4 text-center text-[11.5px] text-text-subtle">
        内容由 AI 生成,请仔细甄别 · DeepResearch Pro · 多智能体 · RAG · MCP
      </footer>

      <LlmSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
