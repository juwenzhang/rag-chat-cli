import "server-only";

import { apiFetch } from "@/lib/api/client";
import type {
  MemberOut,
  OrgOut,
  Role,
} from "@/lib/api/types";

export interface CreateOrgBody {
  name: string;
  slug?: string;
}

export interface UpdateOrgBody {
  name?: string;
}

export interface AddMemberBody {
  email: string;
  role?: Role;
}

export interface UpdateMemberRoleBody {
  role: Role;
}

export interface TransferOwnershipBody {
  new_owner_id: string;
}

export async function listOrgs(token: string): Promise<OrgOut[]> {
  return apiFetch<OrgOut[]>("/orgs", { token });
}

export async function createOrg(
  token: string,
  body: CreateOrgBody
): Promise<OrgOut> {
  return apiFetch<OrgOut>("/orgs", { method: "POST", token, body });
}

export async function getOrg(token: string, orgId: string): Promise<OrgOut> {
  return apiFetch<OrgOut>(`/orgs/${orgId}`, { token });
}

export async function updateOrg(
  token: string,
  orgId: string,
  body: UpdateOrgBody
): Promise<OrgOut> {
  return apiFetch<OrgOut>(`/orgs/${orgId}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function deleteOrg(token: string, orgId: string): Promise<void> {
  await apiFetch<void>(`/orgs/${orgId}`, { method: "DELETE", token });
}

export async function listMembers(
  token: string,
  orgId: string
): Promise<MemberOut[]> {
  return apiFetch<MemberOut[]>(`/orgs/${orgId}/members`, { token });
}

export async function addMember(
  token: string,
  orgId: string,
  body: AddMemberBody
): Promise<MemberOut> {
  return apiFetch<MemberOut>(`/orgs/${orgId}/members`, {
    method: "POST",
    token,
    body,
  });
}

export async function updateMember(
  token: string,
  orgId: string,
  userId: string,
  body: UpdateMemberRoleBody
): Promise<MemberOut> {
  return apiFetch<MemberOut>(`/orgs/${orgId}/members/${userId}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function removeMember(
  token: string,
  orgId: string,
  userId: string
): Promise<void> {
  await apiFetch<void>(`/orgs/${orgId}/members/${userId}`, {
    method: "DELETE",
    token,
  });
}

export async function transferOwnership(
  token: string,
  orgId: string,
  body: TransferOwnershipBody
): Promise<OrgOut> {
  return apiFetch<OrgOut>(`/orgs/${orgId}/transfer`, {
    method: "POST",
    token,
    body,
  });
}
