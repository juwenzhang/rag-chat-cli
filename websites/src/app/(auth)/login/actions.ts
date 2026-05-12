"use server";

import { redirect } from "next/navigation";

import { authApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { setSession } from "@/lib/session";

export type LoginState = {
  error?: string;
  fieldErrors?: { email?: string; password?: string };
};

export async function loginAction(
  _prev: LoginState | undefined,
  formData: FormData
): Promise<LoginState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "/chat");

  const fieldErrors: LoginState["fieldErrors"] = {};
  if (!email) fieldErrors.email = "Email is required";
  else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
    fieldErrors.email = "Invalid email";
  if (!password) fieldErrors.password = "Password is required";

  if (Object.keys(fieldErrors).length > 0) {
    return { fieldErrors };
  }

  try {
    const pair = await authApi.login({ email, password });
    await setSession(pair);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 401 || err.status === 400) {
        return { error: "Invalid email or password" };
      }
      return { error: err.message };
    }
    return { error: "Network error — is the backend running?" };
  }

  redirect(next.startsWith("/") ? next : "/chat");
}
