import { api } from "@/lib/api/browser";
import type { UpdateDocumentBody } from "@/lib/api/server/knowledge";
import type { UpdateWikiPageBody } from "@/lib/api/server/wiki";

export const wikiPageService = {
  getPage: (pageId: string) => api.wikiPages.get(pageId),
  updatePage: (pageId: string, body: UpdateWikiPageBody) =>
    api.wikiPages.update(pageId, body),
  deletePage: (pageId: string) => api.wikiPages.remove(pageId),
  duplicatePage: (pageId: string) => api.wikiPages.duplicate(pageId),
  movePage: (pageId: string, body: Parameters<typeof api.wikiPages.move>[1]) =>
    api.wikiPages.move(pageId, body),
  createChatFromPage: (pageId: string) => api.chat.sessionFromWiki(pageId),
  createPageShare: (pageId: string) => api.wikiPages.createShare(pageId),
  revokePageShare: (token: string) => api.wikiPageShares.remove(token),
};

export const wikiService = {
  createWiki: (orgId: string, body: Parameters<typeof api.orgs.createWiki>[1]) =>
    api.orgs.createWiki(orgId, body),
  updateWiki: (wikiId: string, body: Parameters<typeof api.wikis.update>[1]) =>
    api.wikis.update(wikiId, body),
  deleteWiki: (wikiId: string) => api.wikis.remove(wikiId),
  createPage: (wikiId: string, body: Parameters<typeof api.wikis.createPage>[1]) =>
    api.wikis.createPage(wikiId, body),
  listMembers: (wikiId: string) => api.wikis.listMembers(wikiId),
  addMember: (wikiId: string, body: Parameters<typeof api.wikis.addMember>[1]) =>
    api.wikis.addMember(wikiId, body),
  updateMemberRole: (
    wikiId: string,
    userId: string,
    body: Parameters<typeof api.wikis.updateMemberRole>[2]
  ) => api.wikis.updateMemberRole(wikiId, userId, body),
  removeMember: (wikiId: string, userId: string) =>
    api.wikis.removeMember(wikiId, userId),
};

export const documentService = {
  getDocument: (documentId: string) => api.documents.get(documentId),
  createDocument: (body: Parameters<typeof api.documents.create>[0]) =>
    api.documents.create(body),
  updateDocument: (documentId: string, body: UpdateDocumentBody) =>
    api.documents.update(documentId, body),
  deleteDocument: (documentId: string) => api.documents.remove(documentId),
};
