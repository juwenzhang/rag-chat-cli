"use client";

import type { Editor } from "@tiptap/react";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useWikiPageEditor } from "@/features/wiki/hooks/use-wiki-page-editor";
import { useI18n } from "@/lib/i18n/provider";
import type {
  EffectiveWikiRole,
  OrgOut,
  WikiOut,
  WikiPageDetailOut,
} from "@/lib/api/shared/types";

import { MovePageDialog } from "../move-page-dialog";
import { WikiEditorBody } from "./wiki-editor-body";
import { WikiEditorHeader } from "./wiki-editor-header";
import { WikiPageShareDialog } from "../wiki-page-share-dialog";

interface Props {
  page: WikiPageDetailOut;
  wiki: WikiOut;
  role: EffectiveWikiRole;
  orgs: OrgOut[];
  writableWikis: WikiOut[];
}

/** TipTap-based wiki editor view. Business orchestration lives in `useWikiPageEditor`. */
export function WikiEditorClient({
  page: initialPage,
  wiki,
  role,
  writableWikis,
}: Props) {
  const router = useRouter();
  const { t } = useI18n();
  const editor = useWikiPageEditor({ initialPage, wiki, role });
  const [pendingDelete, setPendingDelete] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const editorRef = useRef<Editor | null>(null);

  const jumpToHeading = useCallback((index: number) => {
    const dom = editorRef.current?.view.dom;
    if (!dom) return;
    const headings = Array.from(
      dom.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5, h6")
    ).filter((heading) => heading.textContent?.trim());
    headings[index]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <div className="flex h-full flex-col">
      <WikiEditorHeader
        wiki={wiki}
        readOnly={editor.readOnly}
        status={editor.status}
        lastSavedAt={editor.lastSavedAt}
        copy={{
          askAI: t("wiki.editor.askAI"),
          share: t("wiki.editor.share"),
          pageActions: t("wiki.editor.pageActions"),
          duplicate: t("wiki.editor.duplicate"),
          move: t("wiki.editor.move"),
          delete: t("wiki.editor.delete"),
        }}
        onAskAI={() => void editor.askAI()}
        onShare={() => setShareOpen(true)}
        onDuplicate={() => void editor.duplicatePage()}
        onMove={() => setMoveOpen(true)}
        onDelete={() => setPendingDelete(true)}
      />

      <WikiEditorBody
        title={editor.title}
        initialMarkdown={initialPage.body}
        readOnly={editor.readOnly}
        tocItems={editor.tocItems}
        titlePlaceholder={t("wiki.editor.titlePlaceholder")}
        onTitleChange={editor.updateTitle}
        onBodyChange={editor.updateBody}
        onEditorReady={(instance) => {
          editorRef.current = instance;
        }}
        onJumpToHeading={jumpToHeading}
      />

      <ConfirmDialog
        open={pendingDelete}
        onOpenChange={setPendingDelete}
        title="Delete this page?"
        description="The page and its content will be removed permanently."
        confirmLabel="Delete"
        destructive
        onConfirm={editor.deletePage}
      />

      <MovePageDialog
        open={moveOpen}
        onOpenChange={setMoveOpen}
        currentWikiId={initialPage.wiki_id}
        pageId={initialPage.id}
        wikis={writableWikis}
        onMoved={(target) => {
          router.push(`/wiki/${target.wiki_id}/p/${target.id}`);
          router.refresh();
        }}
      />

      <WikiPageShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        pageId={initialPage.id}
        pageTitle={editor.title}
      />
    </div>
  );
}
