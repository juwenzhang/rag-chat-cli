"use client";

import { Check, Copy } from "lucide-react";
import { memo, useState, type ComponentProps, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

interface Props {
  children: string;
  className?: string;
}

/**
 * Renders an assistant turn's content as Markdown.
 *
 * - remark-gfm  : tables, strikethrough, taskboxes, autolinks
 * - rehype-highlight: syntax highlighting via highlight.js
 *
 * We deliberately avoid raw HTML — a malicious model can't smuggle in
 * <script>, <iframe>, etc. Custom renderers add a language badge and
 * a Copy button to code blocks, and wrap tables for horizontal scroll.
 */
function MarkdownImpl({ children, className }: Props) {
  return (
    <div className={cn("markdown-body", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
        ]}
        components={{
          a: ({ href, children, ...rest }) => (
            <a
              href={href}
              target={href?.startsWith("http") ? "_blank" : undefined}
              rel={href?.startsWith("http") ? "noopener noreferrer" : undefined}
              {...rest}
            >
              {children}
            </a>
          ),
          pre: CodeBlock,
          table: ({ children, ...rest }) => (
            <div className="table-wrapper">
              <table {...rest}>{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

export const Markdown = memo(MarkdownImpl);

function CodeBlock({ children, ...rest }: ComponentProps<"pre">) {
  const [copied, setCopied] = useState(false);

  const language = extractLanguage(children);
  const text = extractText(children);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  return (
    <div className="group relative">
      <div className="pointer-events-none absolute inset-x-0 top-0 flex h-8 items-center justify-between px-3.5">
        <span className="select-none font-mono text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">
          {language || ""}
        </span>
        <button
          type="button"
          onClick={onCopy}
          aria-label="Copy code"
          className={cn(
            "pointer-events-auto inline-flex size-6 items-center justify-center rounded-md",
            "text-muted-foreground/80 transition-all hover:bg-foreground/5 hover:text-foreground",
            "opacity-0 group-hover:opacity-100"
          )}
        >
          {copied ? (
            <Check className="size-3.5" />
          ) : (
            <Copy className="size-3.5" />
          )}
        </button>
      </div>
      <pre {...rest}>{children}</pre>
    </div>
  );
}

function extractLanguage(node: ReactNode): string | null {
  const first = Array.isArray(node) ? node[0] : node;
  if (!first || typeof first !== "object" || !("props" in first)) return null;
  const props = (first as { props: { className?: string } }).props;
  const cls = props?.className || "";
  const match = cls.match(/language-([\w-]+)/);
  return match ? match[1] : null;
}

function extractText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return extractText(
      (node as { props: { children?: ReactNode } }).props.children ?? null
    );
  }
  return "";
}
