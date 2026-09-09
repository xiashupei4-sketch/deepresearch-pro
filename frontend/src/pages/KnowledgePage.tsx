import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { KbDocument, KbSearchHit } from "../lib/types";
import { Badge, Button, Card, EmptyState, Input, Spinner, cx } from "../components/ui";
import { DOC_STATUS_ZH, zh } from "../lib/labels";

const STATUS_TONE: Record<string, "success" | "accent" | "warning" | "danger" | "neutral"> = {
  INDEXED: "success",
  EMBEDDING: "accent",
  CHUNKING: "accent",
  PARSING: "accent",
  UPLOADING: "neutral",
  FAILED: "danger",
};

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function KnowledgePage() {
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KbSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async (): Promise<KbDocument[]> => {
    try {
      const list = await api.listDocuments();
      setDocs(list);
      return list;
    } catch {
      /* backend offline */
      return [];
    }
  };

  useEffect(() => {
    const PROCESSING = new Set(["UPLOADING", "PARSING", "CHUNKING", "EMBEDDING"]);
    let t: number;
    const tick = async () => {
      const list = await refresh();
      const busy = list.some((d) => PROCESSING.has(d.status));
      t = window.setTimeout(() => void tick(), busy ? 3000 : 30000);
    };
    void tick();
    return () => window.clearTimeout(t);
  }, []);

  const upload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      await api.uploadDocument(file);
      await refresh();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setUploading(false);
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchKb(query.trim());
      setHits(res.hits);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setSearching(false);
    }
  };

  const remove = async (id: string) => {
    await api.deleteDocument(id).catch(() => undefined);
    await refresh();
  };

  return (
    <div className="grid h-full grid-cols-[minmax(0,1fr)_minmax(0,1fr)] divide-x divide-border overflow-hidden">
      {/* documents */}
      <div className="flex min-h-0 flex-col">
        <div className="flex items-center justify-between px-4 pt-3.5 pb-3">
          <h2 className="text-[13px] font-semibold">知识库</h2>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            accept=".txt,.md,.pdf,.docx,.csv,.json"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void upload(f);
              e.target.value = "";
            }}
          />
          <Button size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? <Spinner /> : "+"} 上传
          </Button>
        </div>
        {error && <div className="px-4 pb-2 text-[12px] text-danger">{error}</div>}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <div className="flex flex-col gap-1.5">
            {docs.map((d) => (
              <Card key={d.id} className="group px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[12.5px] font-medium">{d.filename}</span>
                  <div className="flex items-center gap-1.5">
                    <Badge tone={STATUS_TONE[d.status] || "neutral"}>{zh(DOC_STATUS_ZH, d.status)}</Badge>
                    <button
                      onClick={() => void remove(d.id)}
                      className="rounded-md px-1 text-[13px] leading-none text-text-subtle opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                      title="删除"
                    >
                      ×
                    </button>
                  </div>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-text-subtle">
                  <span>{fmtSize(d.size_bytes)}</span>
                  <span>·</span>
                  <span>{d.chunk_count} 个分块</span>
                  {d.error && <span className="truncate text-danger">{d.error}</span>}
                </div>
              </Card>
            ))}
            {docs.length === 0 && (
              <EmptyState
                title="暂无文档"
                hint="上传 txt / md / pdf / docx 文件,为研究提供私有语料支撑。"
              />
            )}
          </div>
        </div>
      </div>

      {/* semantic search */}
      <div className="flex min-h-0 flex-col">
        <div className="px-4 pt-3.5 pb-3">
          <h2 className="mb-3 text-[13px] font-semibold">语义检索</h2>
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void search()}
              placeholder="检索已索引的知识…"
              className="rounded-xl"
            />
            <Button onClick={() => void search()} disabled={!query.trim() || searching}>
              {searching ? <Spinner /> : "检索"}
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {hits && (
            <div className="flex flex-col gap-1.5 animate-fade-up">
              {hits.map((h, i) => (
                <Card key={h.id} className={cx("px-3 py-2.5")}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-mono text-[10.5px] text-text-subtle">
                      #{i + 1} · {String(h.metadata?.source_title || h.metadata?.document_id || h.id).slice(0, 40)}
                    </span>
                    <span className="font-mono text-[10.5px] text-accent">{h.score.toFixed(3)}</span>
                  </div>
                  <p className="text-[12px] leading-5 text-text-muted">{h.text.slice(0, 320)}</p>
                </Card>
              ))}
              {hits.length === 0 && <EmptyState title="无匹配结果" hint="换个查询试试。" />}
            </div>
          )}
          {!hits && <EmptyState title="检索语料库" hint="向量 + BM25 混合检索,RRF 融合排序。" />}
        </div>
      </div>
    </div>
  );
}
