"use client";

import {
  ArrowLeft,
  Check,
  Copy,
  Loader2,
  MessageSquare,
  MoreHorizontal,
  Move,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { TipTapEditor } from "@/components/wiki/tiptap-editor";
import { parseToc, WikiToc } from "@/components/wiki/wiki-toc";
import type {
  EffectiveWikiRole,
  OrgOut,
  WikiOut,
  WikiPageDetailOut,
} from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

interface Props {
  page: WikiPageDetailOut;
  wiki: WikiOut;
  role: EffectiveWikiRole;
  orgs: OrgOut[];
  writableWikis: WikiOut[];
}

type Status = "idle" | "dirty" | "saving" | "saved" | "conflict";

const AUTOSAVE_MS = 1500;

/**
 * TipTap-based wiki editor (Feishu/Notion-style WYSIWYG).
 *
 * Architecture:
 *   - <TipTapEditor> owns the editable surface. It emits markdown on
 *     every keystroke via ``onChange``; we mirror that into ``body``
 *     state and kick a debounced PATCH.
 *   - <WikiToc> on the right rail rebuilds itself from the current
 *     markdown body; clicks scroll the rendered preview by anchor id.
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
  const [status, setStatus] = useState<Status>("idle");
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
      const res = await fetch(`/api/wiki-pages/${pageRef.current.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: titleRef.current,
          body: bodyRef.current,
          revision: pageRef.current.revision,
        }),
      });
      if (res.status === 409) {
        setStatus("conflict");
        toast.error("This page changed elsewhere — refetching.");
        const fresh = await fetch(`/api/wiki-pages/${pageRef.current.id}`);
        if (fresh.ok) {
          pageRef.current = (await fresh.json()) as WikiPageDetailOut;
        }
        return;
      }
      if (!res.ok) {
        setStatus("dirty");
        toast.error("Failed to save");
        return;
      }
      const updated = (await res.json()) as WikiPageDetailOut;
      pageRef.current = updated;
      setLastSavedAt(new Date());
      setStatus(dirtyRef.current ? "dirty" : "saved");
    } catch (err) {
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
    setTitle(e.target.value);
    scheduleSave();
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
  const jumpToHeading = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // ── Page-level ops ──────────────────────────────────────────────
  const onDelete = async () => {
    const res = await fetch(`/api/wiki-pages/${pageRef.current.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      toast.error("Failed to delete");
      throw new Error("delete failed");
    }
    toast.success("Page deleted");
    router.push(`/wiki/${wiki.id}`);
    router.refresh();
  };
  const onDuplicate = async () => {
    const res = await fetch(
      `/api/wiki-pages/${pageRef.current.id}/duplicate`,
      { method: "POST" }
    );
    if (!res.ok) {
      toast.error("Failed to duplicate");
      return;
    }
    const copy = (await res.json()) as WikiPageDetailOut;
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
    const res = await fetch(
      `/api/chat/sessions/from-wiki/${pageRef.current.id}`,
      { method: "POST" }
    );
    if (!res.ok) {
      toast.error("Failed to open chat");
      return;
    }
    const sess = (await res.json()) as { id: string };
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

function SaveIndicator({
  status,
  lastSavedAt,
}: {
  status: Status;
  lastSavedAt: Date | null;
}) {
  if (status === "saving") {
    return (
      <span className="inline-flex items-center gap-1">
        <Loader2 className="size-3 animate-spin" />
        Saving…
      </span>
    );
  }
  if (status === "conflict") {
    return (
      <span className="inline-flex items-center gap-1 text-destructive">
        Conflict — reloaded
      </span>
    );
  }
  if (status === "dirty") {
    return <span className="text-muted-foreground/70">Unsaved</span>;
  }
  if (status === "saved" && lastSavedAt) {
    return (
      <span className="inline-flex items-center gap-1">
        <Check className="size-3 text-primary" />
        Saved {formatRelative(lastSavedAt.toISOString())}
      </span>
    );
  }
  return null;
}

function MovePageDialog({
  open,
  onOpenChange,
  currentWikiId,
  pageId,
  wikis,
  onMoved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentWikiId: string;
  pageId: string;
  wikis: WikiOut[];
  onMoved: (target: WikiPageDetailOut) => void;
}) {
  const [targetId, setTargetId] = useState(currentWikiId);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setTargetId(currentWikiId);
  }, [open, currentWikiId]);
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || targetId === currentWikiId) {
      onOpenChange(false);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`/api/wiki-pages/${pageId}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_wiki_id: targetId }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          message?: string;
        };
        toast.error(body.message || "Failed to move");
        return;
      }
      const moved = (await res.json()) as WikiPageDetailOut;
      toast.success("Page moved");
      onMoved(moved);
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Move to wiki</DialogTitle>
            <DialogDescription>
              The page leaves its current wiki and lands at the end of the
              destination's root list.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="move-target">Destination wiki</Label>
            <select
              id="move-target"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
            >
              {wikis.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                  {w.id === currentWikiId ? " (current)" : ""}
                </option>
              ))}
            </select>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={targetId === currentWikiId || busy}
            >
              {busy ? "Moving…" : "Move"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
