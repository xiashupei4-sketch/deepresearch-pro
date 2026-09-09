import type { ReactNode } from "react";

/**
 * Minimal, dependency-free markdown renderer covering the report subset:
 * headings, ordered/unordered lists, tables, paragraphs and citations [n].
 * (The writer's mock output uses exactly this subset.)
 */
function inline(text: string, keyPrefix: string): ReactNode[] {
  // highlight citation markers like [1] or [12]
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((p, i) =>
    /^\[\d+\]$/.test(p) ? (
      <span
        key={`${keyPrefix}-${i}`}
        className="mx-0.5 inline-flex h-[15px] min-w-[15px] items-center justify-center rounded-full bg-accent-soft px-1 align-[1px] text-[9.5px] font-semibold leading-none text-accent"
      >
        {p.slice(1, -1)}
      </span>
    ) : (
      <span key={`${keyPrefix}-${i}`}>{p}</span>
    ),
  );
}

export function Markdown({ source }: { source: string }) {
  const lines = source.split("\n");
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let table: string[][] | null = null;
  let key = 0;

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={key++}>
        {list.items.map((it, i) => (
          <li key={i}>{inline(it, `li-${key}-${i}`)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };

  const flushTable = () => {
    if (!table || table.length < 2) {
      table = null;
      return;
    }
    const [head, , ...rows] = table;
    blocks.push(
      <table key={key++}>
        <thead>
          <tr>{head.map((c, i) => <th key={i}>{inline(c, `th-${key}-${i}`)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>{r.map((c, ci) => <td key={ci}>{inline(c, `td-${key}-${ri}-${ci}`)}</td>)}</tr>
          ))}
        </tbody>
      </table>,
    );
    table = null;
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const isTableRow = /^\|.*\|$/.test(line.trim());
    if (table && !isTableRow) flushTable();

    if (isTableRow) {
      const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-{3,}:?$/.test(c))) continue; // separator row
      (table ||= []).push(cells);
      continue;
    }

    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      flushList();
      const level = h[1].length;
      const Tag = (level <= 1 ? "h1" : level === 2 ? "h2" : "h3") as "h1" | "h2" | "h3";
      blocks.push(<Tag key={key++}>{inline(h[2], `h-${key}`)}</Tag>);
      continue;
    }
    const ol = /^\d+\.\s+(.*)$/.exec(line);
    if (ol) {
      if (list && !list.ordered) flushList();
      (list ||= { ordered: true, items: [] }).items.push(ol[1]);
      continue;
    }
    const ul = /^[-*]\s+(.*)$/.exec(line);
    if (ul) {
      if (list && list.ordered) flushList();
      (list ||= { ordered: false, items: [] }).items.push(ul[1]);
      continue;
    }
    if (!line.trim()) {
      flushList();
      continue;
    }
    flushList();
    blocks.push(<p key={key++}>{inline(line, `p-${key}`)}</p>);
  }
  flushList();
  flushTable();

  return <div className="report-body">{blocks}</div>;
}
