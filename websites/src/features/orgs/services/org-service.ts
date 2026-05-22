import { api } from "@/lib/api/browser";
import type {
  AddMemberBody,
  CreateOrgBody,
  UpdateMemberRoleBody,
  UpdateOrgBody,
} from "@/lib/api/server/orgs";

export const orgService = {
  leaveOrg: (orgId: string, userId: string) => api.orgs.removeMember(orgId, userId),

  deleteOrg: (orgId: string) => api.orgs.remove(orgId),

  listMembers: (orgId: string) => api.orgs.listMembers(orgId),

  addMember: (orgId: string, body: AddMemberBody) => api.orgs.addMember(orgId, body),

  updateMemberRole: (orgId: string, userId: string, body: UpdateMemberRoleBody) =>
    api.orgs.updateMemberRole(orgId, userId, body),

  removeMember: (orgId: string, userId: string) => api.orgs.removeMember(orgId, userId),

  createOrg: (body: CreateOrgBody) => api.orgs.create(body),

  updateOrg: (orgId: string, body: UpdateOrgBody) => api.orgs.update(orgId, body),
};
