import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { LlmSettings, LlmTestResult } from "../lib/types";
import { Badge, Button, Input, Modal, Spinner, cx } from "./ui";

/**
 * API 配置弹窗:把后端 LLM 提供者从 Mock 切换为任意 OpenAI 兼容端点,
 * 或重置回默认(Mock)。配置保存在后端进程内存,重启后回退到环境变量。
 */
export function LlmSettingsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [status, setStatus] = useState<LlmSettings | null>(null);
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<LlmTestResult | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSaved(false);
    setApiKey("");
    setTestResult(null);
    void (async () => {
      try {
        const s = await api.getLlmSettings();
        setStatus(s);
        setBaseUrl(s.base_url || "https://api.openai.com/v1");
        setModel(s.model || "");
      } catch {
        setError("加载当前配置失败,请确认后端服务正在运行");
      }
    })();
  }, [open]);

  const save = async () => {
    setBusy(true);
    setError(null);
    setTestResult(null);
    try {
      const s = await api.updateLlmSettings({
        api_key: apiKey || undefined,
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      setStatus(s);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    setError(null);
    setTestResult(null);
    try {
      const s = await api.updateLlmSettings({ reset: true });
      setStatus(s);
      setApiKey("");
      setBaseUrl("https://api.openai.com/v1");
      setModel("");
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  const field = "block mb-1.5 text-[12px] font-medium text-text-muted";
  const configured = status?.mode === "openai-compatible";

  /** 连通性测试:用表单当前值(空 Key 回退已保存的 Key)发一次最小请求。 */
  const test = async () => {
    setTesting(true);
    setError(null);
    try {
      setTestResult(await api.testLlmSettings({
        api_key: apiKey || undefined,
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      }));
    } catch (e) {
      setTestResult({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal open={open} title="API 配置" onClose={onClose} width={460}>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-[12px] text-text-subtle">当前模式</span>
        {status === null ? (
          <Spinner className="h-3 w-3" />
        ) : configured ? (
          <Badge tone="success">已接入 {status.model || "自定义模型"}</Badge>
        ) : (
          <Badge tone="accent">Mock 离线模式</Badge>
        )}
      </div>

      <div className="flex flex-col gap-3.5">
        <div>
          <label className={field}>Base URL(OpenAI 兼容端点)</label>
          <Input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            className="font-mono text-[12.5px]"
          />
        </div>
        <div>
          <label className={field}>模型名称</label>
          <Input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="例如:gpt-4o-mini / glm-4-plus / qwen-max"
            className="font-mono text-[12.5px]"
          />
        </div>
        <div>
          <label className={field}>
            API Key
            {configured && (
              <span className="ml-1.5 font-normal text-text-subtle">
                已配置(留空则沿用现有 Key)
              </span>
            )}
          </label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…"
            className="font-mono text-[12.5px]"
          />
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-[12px] text-danger">
          {error}
        </div>
      )}
      {saved && !error && (
        <div className="mt-3 rounded-lg bg-success/10 px-3 py-2 text-[12px] text-success">
          已保存,新发起的研究将使用该配置
        </div>
      )}

      {testResult && (
        <div
          className={cx(
            "mt-3 rounded-lg px-3 py-2 text-[12px] leading-5",
            testResult.ok ? "bg-success/10 text-success" : "bg-danger/10 text-danger",
          )}
        >
          {testResult.ok ? (
            <>
              <span className="font-medium">连接成功</span>
              <span className="ml-1.5 text-text-muted">
                {testResult.latency_ms}ms · {testResult.model}
                {testResult.reply ? ` · 模型回复:“${testResult.reply}”` : ""}
              </span>
              {testResult.embedding_ok === false && (
                <div className="mt-1 text-danger">
                  向量服务异常(知识库/检索将不可用):{testResult.embedding_error}
                </div>
              )}
            </>
          ) : (
            <>
              <span className="font-medium">连接失败:</span>
              {testResult.error || "未知错误"}
            </>
          )}
        </div>
      )}

      <div className="mt-5 flex items-center justify-between">
        <button
          onClick={() => void reset()}
          disabled={busy}
          className={cx(
            "text-[12px] text-text-subtle transition-colors duration-200",
            "hover:text-text disabled:opacity-50",
          )}
        >
          恢复默认(Mock)
        </button>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => void test()}
            disabled={testing || busy || !baseUrl.trim()}
            title={configured || apiKey.trim() ? "发一次最小请求验证连通性" : "请先填写 API Key"}
          >
            {testing ? <Spinner /> : null}
            测试连接
          </Button>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button onClick={() => void save()} disabled={busy || !model.trim() || !baseUrl.trim()}>
            {busy ? <Spinner /> : null}
            保存
          </Button>
        </div>
      </div>
    </Modal>
  );
}
