"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { wikiPageService } from "@/features/wiki/services/wiki-page-service";
import { useWikiStore } from "@/features/wiki/stores/wiki-store";
import { parseToc } from "@/features/wiki/components/wiki-toc";
import { ApiError, type EffectiveWikiRole, type WikiOut, type WikiPageDetailOut } from "@/lib/api/shared/types";

import type { WikiSaveStatus } from "../components/save-indicator";

const AUTOSAVE_MS = 1500;

interface UseWikiPageEditorOptions {
  initialPage: WikiPageDetailOut;
  wiki: WikiOut;
  role: EffectiveWikiRole;
}

export function useWikiPageEditor({
  initialPage,
  wiki,
  role,
}: UseWikiPageEditorOptions) {
  const router = useRouter();
  const readOnly = role === "viewer";
  const setPageTitleOverride = useWikiStore(
    (state) => state.setPageTitleOverride
  );

  const pageRef = useRef(initialPage);
  const [title, setTitle] = useState(initialPage.title);
  const [body, setBody] = useState(initialPage.body);
  const [status, setStatus] = useState<WikiSaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dirtyRef = useRef(false);
  const inFlightRef = useRef(false);
  const titleRef = useRef(title);
  const bodyRef = useRef(body);

  useEffect(() => {
    titleRef.current = title;
    bodyRef.current = body;
  }, [body, title]);

  const flush = useCallback(async () => {
    if (inFlightRef.current) {
      dirtyRef.current = true;
      return;
    }
    inFlightRef.current = true;
    dirtyRef.current = false;
    setStatus("saving");
    try {
      const updated = await wikiPageService.updatePage(pageRef.current.id, {
        title: titleRef.current,
        body: bodyRef.current,
        revision: pageRef.current.revision,
      });
      pageRef.current = updated;
      setLastSavedAt(new Date());
      setStatus(dirtyRef.current ? "dirty" : "saved");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setStatus("conflict");
        toast.error("This page changed elsewhere — refetching.");
        try {
          pageRef.current = await wikiPageService.getPage(pageRef.current.id);
        } catch {
          // Keep stale page; next edit retries.
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

  const updateTitle = useCallback(
    (next: string) => {
      setTitle(next);
      titleRef.current = next;
      scheduleSave();
      setPageTitleOverride(pageRef.current.id, next);
    },
    [scheduleSave, setPageTitleOverride]
  );

  const updateBody = useCallback(
    (markdown: string) => {
      setBody(markdown);
      bodyRef.current = markdown;
      scheduleSave();
    },
    [scheduleSave]
  );

  const deletePage = useCallback(async () => {
    try {
      await wikiPageService.deletePage(pageRef.current.id);
    } catch (err) {
      toast.error("Failed to delete");
      throw err;
    }
    toast.success("Page deleted");
    router.push(`/wiki/${wiki.id}`);
    router.refresh();
  }, [router, wiki.id]);

  const duplicatePage = useCallback(async () => {
    try {
      const copy = await wikiPageService.duplicatePage(pageRef.current.id);
      toast.success("Duplicated");
      router.push(`/wiki/${copy.wiki_id}/p/${copy.id}`);
      router.refresh();
    } catch {
      toast.error("Failed to duplicate");
    }
  }, [router]);

  const askAI = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (dirtyRef.current && !readOnly) await flush();
    try {
      const session = await wikiPageService.createChatFromPage(pageRef.current.id);
      router.push(`/chat/${session.id}`);
    } catch {
      toast.error("Failed to open chat");
    }
  }, [flush, readOnly, router]);

  return {
    readOnly,
    title,
    body,
    status,
    lastSavedAt,
    tocItems: useMemo(() => parseToc(body), [body]),
    updateTitle,
    updateBody,
    deletePage,
    duplicatePage,
    askAI,
  };
}
