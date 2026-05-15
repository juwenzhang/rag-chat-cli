"use client";

import type { Editor } from "@tiptap/react";
import {
  ArrowLeft,
  MoreHorizontal,
  Share2,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TipTapEditor } from "@/components/wiki/tiptap-editor";
import { parseToc, WikiToc } from "@/components/wiki/wiki-toc";
import { SaveIndicator, type WikiSaveStatus } from "@/components/wiki/save-indicator";
import { api } from "@/lib/api/browser";
import type { DocumentDetailOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Props {
  document: DocumentDetailOut;
}

const AUTOSAVE_MS = 1500;

export function DocumentEditorClient({ document: initial }: Props) {
  const router = useRouter();
  const docRef = useRef(initial);
  const [title, setTitle] = useState(initial.title || "");
  const [body, setBody] = useState(initial.body);
  const [status, setStatus] = useState<WikiSaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [pendingDelete, setPendingDelete] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dirtyRef = useRef(false);
  const inFlightRef = useRef(false);
  const titleRef = useRef(title);
  const bodyRef = useRef(body);
  titleRef.current = title;
  bodyRef.current = body;

  const flush = useCallback(async () => {
    if (inFlightRef.current) {
      dirtyRef.current = true;
      return;
    }
    inFlightRef.current = true;
    dirtyRef.current = false;
    setStatus("saving");
    try {
      await api.documents.update(docRef.current.id, {
        title: titleRef.current || undefined,
        body: bodyRef.current,
      });
      setLastSavedAt(new Date());
      setStatus(dirtyRef.current ? "dirty" : "saved");
    } catch (err) {
      setStatus("dirty");
      toast.error((err as Error).message);
    } finally {
      inFlightRef.current = false;
      if (dirtyRef.current) {
        timerRef.current = setTimeout(flush, AUTOSAVE_MS);
      }
    }
  }, []);

  const scheduleSave = useCallback(() => {
    dirtyRef.current = true;
    setStatus("dirty");
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void flush(), AUTOSAVE_MS);
  }, [flush]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const onTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setTitle(next);
    scheduleSave();
    // Broadcast the title so the sidebar can reflect it instantly.
    window.dispatchEvent(
      new CustomEvent("doc:title", {
        detail: { docId: docRef.current.id, title: next },
      })
    );
  };

  const onBodyChange = useCallback(
    (markdown: string) => {
      setBody(markdown);
      scheduleSave();
    },
    [scheduleSave]
  );

  // ── TOC ─────────────────────────────────────────────────────────
  const tocItems = useMemo(() => parseToc(body), [body]);

  const editorRef = useRef<Editor | null>(null);
  const jumpToHeading = useCallback((index: number) => {
    const dom = editorRef.current?.view.dom;
    if (!dom) return;
    const headings = Array.from(
      dom.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5, h6")
    ).filter((h) => h.textContent?.trim());
    headings[index]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // ── Page-level ops ──────────────────────────────────────────────
  const onDelete = async () => {
    try {
      await api.documents.remove(docRef.current.id);
    } catch {
      toast.error("Failed to delete");
      return;
    }
    toast.success("Document deleted");
    router.push("/wiki/documents");
    router.refresh();
  };

  const onShare = async () => {
    const url = `${window.location.origin}/wiki/documents/${docRef.current.id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      toast.error("Failed to copy link");
    }
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur">
        <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5">
          <Link href="/wiki/documents">
            <ArrowLeft className="size-3.5" />
            Documents
          </Link>
        </Button>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <SaveIndicator status={status} lastSavedAt={lastSavedAt} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Document actions"
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onSelect={() => void onShare()}>
                <Share2 />
                Copy link
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={(e) => {
                  e.preventDefault();
                  setPendingDelete(true);
                }}
                className="text-destructive focus:bg-destructive/10 focus:text-destructive"
              >
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-6 pb-24 pt-8 sm:px-12 sm:pt-12">
            <input
              value={title}
              onChange={onTitleChange}
              placeholder="Untitled"
              className={cn(
                "mb-6 w-full border-0 bg-transparent p-0 outline-none",
                "text-4xl font-bold tracking-tight",
                "placeholder:text-muted-foreground/40"
              )}
              aria-label="Document title"
            />
            <TipTapEditor
              initialMarkdown={initial.body}
              readOnly={false}
              onChange={onBodyChange}
              onReady={(editor) => {
                editorRef.current = editor;
              }}
            />
          </div>
        </div>
        <WikiToc items={tocItems} onJump={jumpToHeading} />
      </div>

      <ConfirmDialog
        open={pendingDelete}
        onOpenChange={setPendingDelete}
        title="Delete this document?"
        description="The document and its content will be removed permanently."
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />
    </div>
  );
}
