"use client";

import type { Editor } from "@tiptap/react";
import {
  ArrowLeft,
  Copy,
  MessageSquare,
  MoreHorizontal,
  Move,
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
import { api } from "@/lib/api/browser";
import {
  ApiError,
  type EffectiveWikiRole,
  type OrgOut,
  type WikiOut,
  type WikiPageDetailOut,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { MovePageDialog } from "./move-page-dialog";
import { SaveIndicator, type WikiSaveStatus } from "./save-indicator";

interface Props {
  page: WikiPageDetailOut;
  wiki: WikiOut;
  role: EffectiveWikiRole;
  orgs: OrgOut[];
  writableWikis: WikiOut[];
}

const AUTOSAVE_MS = 1500;

/**
 * TipTap-based wiki editor (Feishu/Notion-style WYSIWYG).
 *
 * Architecture:
 *   - <TipTapEditor> owns the editable surface. It emits markdown on
 *     every keystroke via ``onChange``; we mirror that into ``body``
 *     state and kick a debounced PATCH.
 *   - <WikiToc> on the right rail rebuilds itself from the current
 *     markdown body; clicks scroll the editor by heading index.
 *   - Title is a plain ``<input>`` above the editor — Feishu's title
 *     lives outside the doc body and it composes more cleanly than
 *     forcing an H1 into TipTap's content.
 */
export function WikiEditorClient({
  page: initialPage,
  wiki,
  role,
  orgs: _orgs,
  writableWikis,
}: Props) {
  const router = useRouter();
  const readOnly = role === "viewer";

  // Canonical page (revision + body) — bumped on every successful PATCH.
  const pageRef = useRef(initialPage);
  const [title, setTitle] = useState(initialPage.title);
  const [body, setBody] = useState(initialPage.body);
  const [status, setStatus] = useState<WikiSaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);

  // ── Save pipeline ────────────────────────────────────────────────
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
      const updated = await api.wikiPages.update(pageRef.current.id, {
        title: titleRef.current,
        body: bodyRef.current,
        revision: pageRef.current.revision,
      });
      pageRef.current = updated;
      setLastSavedAt(new Date());
      setStatus(dirtyRef.current ? "dirty" : "saved");
    } catch (err) {
      // 409 = the page was edited elsewhere since we loaded it. Pull the
      // fresh revision so the next save can win.
      if (err instanceof ApiError && err.status === 409) {
        setStatus("conflict");
        toast.error("This page changed elsewhere — refetching.");
        try {
          pageRef.current = await api.wikiPages.get(pageRef.current.id);
        } catch {
          /* leave the stale page in place — next edit retries */
        }
        return;
      }
      setStatus("dirty");
      toast.error((err as Error).message);
    } finally {
      inFlightRef.current = false;
      if (dirtyRef.current && !readOnly) {
        timerRef.current = setTimeout(flush, AUTOSAVE_MS);
      }
    }
  }, [readOnly]);

  const scheduleSave = useCallback(() => {
    if (readOnly) return;
    dirtyRef.current = true;
    setStatus("dirty");
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void flush(), AUTOSAVE_MS);
  }, [flush, readOnly]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const onTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setTitle(next);
    scheduleSave();
    // Broadcast the title so the wiki sidebar — a sibling subtree under
    // `wiki/layout.tsx` with no shared state — can reflect it instantly.
    // Autosave (above) still owns persistence. Interim bridge until the
    // planned shared client state (Context / store) lands.
    window.dispatchEvent(
      new CustomEvent("wiki:page-title", {
        detail: { pageId: pageRef.current.id, title: next },
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

  // The editor DOM is owned by ProseMirror, which strips any anchor id
  // we'd set imperatively on the next redraw — so the outline jumps by
  // document index instead. `parseToc` and the editor's `<h1>`…`<h6>`
  // are both in document order; filtering out empty-text headings keeps
  // the index aligned with what `parseToc` chose to include.
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
      await api.wikiPages.remove(pageRef.current.id);
    } catch (err) {
      toast.error("Failed to delete");
      throw err;
    }
    toast.success("Page deleted");
    router.push(`/wiki/${wiki.id}`);
    router.refresh();
  };
  const onDuplicate = async () => {
    let copy: WikiPageDetailOut;
    try {
      copy = await api.wikiPages.duplicate(pageRef.current.id);
    } catch {
      toast.error("Failed to duplicate");
      return;
    }
    toast.success("Duplicated");
    router.push(`/wiki/${copy.wiki_id}/p/${copy.id}`);
    router.refresh();
  };
  const onAskAI = async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (dirtyRef.current && !readOnly) await flush();
    let sess: { id: string };
    try {
      sess = await api.chat.sessionFromWiki(pageRef.current.id);
    } catch {
      toast.error("Failed to open chat");
      return;
    }
    router.push(`/chat/${sess.id}`);
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur">
        <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5">
          <Link href={`/wiki/${wiki.id}`}>
            <ArrowLeft className="size-3.5" />
            <span className="max-w-[200px] truncate">{wiki.name}</span>
          </Link>
        </Button>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <SaveIndicator status={status} lastSavedAt={lastSavedAt} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => void onAskAI()}
            className="h-8"
          >
            <MessageSquare className="size-3.5" />
            Ask AI
          </Button>
          {!readOnly && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Page actions"
                >
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem onSelect={() => void onDuplicate()}>
                  <Copy />
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault();
                    setMoveOpen(true);
                  }}
                >
                  <Move />
                  Move to wiki…
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
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-6 pb-24 pt-8 sm:px-12 sm:pt-12">
            <input
              value={title}
              onChange={onTitleChange}
              readOnly={readOnly}
              placeholder="Untitled"
              className={cn(
                "mb-6 w-full border-0 bg-transparent p-0 outline-none",
                "text-4xl font-bold tracking-tight",
                "placeholder:text-muted-foreground/40"
              )}
              aria-label="Page title"
            />
            <TipTapEditor
              initialMarkdown={initialPage.body}
              readOnly={readOnly}
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
        title="Delete this page?"
        description="The page and its content will be removed permanently."
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />

      <MovePageDialog
        open={moveOpen}
        onOpenChange={setMoveOpen}
        currentWikiId={pageRef.current.wiki_id}
        pageId={pageRef.current.id}
        wikis={writableWikis}
        onMoved={(target) => {
          router.push(`/wiki/${target.wiki_id}/p/${target.id}`);
          router.refresh();
        }}
      />
    </div>
  );
}
