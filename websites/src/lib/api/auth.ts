import "server-only";

import { apiFetch } from "@/lib/api/client";
import type { TokenPair, UserOut } from "@/lib/api/types";

export interface RegisterParams {
  email: string;
  password: string;
  display_name?: string;
  /** Email verification code (future — once backend exposes /auth/code/send). */
  code?: string;
}

export interface LoginParams {
  email: string;
  password: string;
}

export async function register(params: RegisterParams): Promise<UserOut> {
  return apiFetch<UserOut>("/auth/register", {
    method: "POST",
    body: params,
  });
}

export async function login(params: LoginParams): Promise<TokenPair> {
  return apiFetch<TokenPair>("/auth/login", {
    method: "POST",
    body: params,
  });
}

export async function refresh(refresh_token: string): Promise<TokenPair> {
  return apiFetch<TokenPair>("/auth/refresh", {
    method: "POST",
    body: { refresh_token },
  });
}

export async function logout(refresh_token: string): Promise<void> {
  await apiFetch<void>("/auth/logout", {
    method: "POST",
    body: { refresh_token },
  });
}

export async function me(token: string): Promise<UserOut> {
  return apiFetch<UserOut>("/me", { token });
}

/**
 * Future endpoint (per docs/AUTH_DESIGN.md §3.1).
 * Sends a 6-digit code to the user's email; returns once dispatched.
 *
 * For now this is a stub that the backend will provide later — callers
 * should handle 404 / 501 gracefully.
 */
export async function sendVerificationCode(params: {
  email: string;
  purpose: "register" | "reset" | "login_2fa";
}): Promise<{ sent: boolean; expires_in: number }> {
  return apiFetch("/auth/code/send", {
    method: "POST",
    body: params,
  });
}
