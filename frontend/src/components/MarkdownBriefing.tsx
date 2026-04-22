import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownBriefingProps {
  content: string;
}

/**
 * Renders the AI-generated morning briefing Markdown with dark-mode styling
 * that matches the dashboard's glass / slate design system.
 *
 * Uses remark-gfm for GitHub Flavored Markdown (tables, strikethrough, task lists,
 * autolinks) — all of which appear in the pipeline's briefing output.
 */
const components: Components = {
  // ── Headings ──────────────────────────────────────────────────────────────
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold text-slate-100 mt-6 mb-3 pb-2 border-b border-slate-700/60">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-semibold text-slate-200 mt-5 mb-2 flex items-center gap-2">
      <span className="w-1 h-5 rounded-full bg-blue-500 flex-shrink-0" />
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-slate-300 mt-4 mb-1.5 uppercase tracking-wide">
      {children}
    </h3>
  ),

  // ── Body text ─────────────────────────────────────────────────────────────
  p: ({ children }) => (
    <p className="text-sm text-slate-300 leading-relaxed mb-3">{children}</p>
  ),

  // ── Emphasis & strong ─────────────────────────────────────────────────────
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-100">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="italic text-slate-400">{children}</em>
  ),

  // ── Lists ─────────────────────────────────────────────────────────────────
  ul: ({ children }) => (
    <ul className="space-y-1.5 mb-3 pl-4">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="space-y-1.5 mb-3 pl-4 list-decimal">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="text-sm text-slate-300 leading-relaxed flex gap-2 items-start">
      <span className="mt-2 w-1.5 h-1.5 rounded-full bg-blue-500/70 flex-shrink-0" />
      <span>{children}</span>
    </li>
  ),

  // ── Blockquote — used for exec summary / key callouts ────────────────────
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-blue-500/50 pl-4 py-1 my-3 bg-blue-500/5 rounded-r-md">
      {children}
    </blockquote>
  ),

  // ── Code ─────────────────────────────────────────────────────────────────
  code: ({ children, className }) => {
    const isBlock = className?.startsWith("language-");
    return isBlock ? (
      <code className="block bg-slate-900 border border-slate-700/60 rounded-lg p-4 text-xs text-slate-300 font-mono leading-relaxed overflow-x-auto mb-3 whitespace-pre">
        {children}
      </code>
    ) : (
      <code className="bg-slate-800 text-blue-300 text-xs font-mono px-1.5 py-0.5 rounded">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <>{children}</>,

  // ── GFM Tables — appear in pattern summary and priority breakdown ─────────
  table: ({ children }) => (
    <div className="overflow-x-auto mb-4 rounded-lg border border-slate-700/50">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-slate-800/80 text-slate-300 text-xs uppercase tracking-wider">
      {children}
    </thead>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-slate-700/40">{children}</tbody>
  ),
  tr: ({ children }) => (
    <tr className="hover:bg-slate-800/30 transition-colors">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2.5 text-left font-semibold text-slate-400">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2.5 text-slate-300">{children}</td>
  ),

  // ── Horizontal rule — section divider in briefings ────────────────────────
  hr: () => <hr className="my-5 border-slate-700/50" />,

  // ── Links ─────────────────────────────────────────────────────────────────
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-400 hover:text-blue-300 underline underline-offset-2 transition-colors"
    >
      {children}
    </a>
  ),
};

export default function MarkdownBriefing({ content }: MarkdownBriefingProps) {
  return (
    <div className="markdown-briefing">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
