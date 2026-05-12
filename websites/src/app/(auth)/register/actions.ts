"use server";

import { redirect } from "next/navigation";

import { authApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { setSession } from "@/lib/session";

export type RegisterState = {
  error?: string;
  fieldErrors?: {
    email?: string;
    password?: string;
    display_name?: string;
    code?: string;
  };
};

export type SendCodeState = {
  status: "idle" | "sent" | "error" | "unavailable";
  message?: string;
  /** Seconds until next resend allowed. */
  cooldown?: number;
};

export async function registerAction(
  _prev: RegisterState | undefined,
  formData: FormData
): Promise<RegisterState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const displayNameRaw = String(formData.get("display_name") ?? "").trim();
  const display_name = displayNameRaw || undefined;
  const codeRaw = String(formData.get("code") ?? "").trim();
  const code = codeRaw || undefined;

  const fieldErrors: RegisterState["fieldErrors"] = {};
  if (!email) fieldErrors.email = "Email is required";
  else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
    fieldErrors.email = "Invalid email";
  if (!password) fieldErrors.password = "Password is required";
  else if (password.length < 8)
    fieldErrors.password = "At least 8 characters";

  if (Object.keys(fieldErrors).length > 0) {
    return { fieldErrors };
  }

  try {
    await authApi.register({ email, password, display_name, code });
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 409) {
        return { fieldErrors: { email: "Email already registered" } };
      }
      if (err.status === 422) {
        return { error: err.message };
      }
      if (err.status === 400 && /code/i.test(err.message)) {
        return { fieldErrors: { code: "Invalid or expired code" } };
      }
      return { error: err.message };
    }
    return { error: "Network error — is the backend running?" };
  }

  // Auto-login
  try {
    const pair = await authApi.login({ email, password });
    await setSession(pair);
  } catch {
    redirect("/login");
  }
  redirect("/chat");
}

/**
 * Triggers /auth/code/send. Gracefully reports "unavailable" if the
 * backend hasn't shipped that endpoint yet (per docs/AUTH_DESIGN.md §3.1
 * the email-code flow is still pending).
 */
export async function sendCodeAction(
  _prev: SendCodeState | undefined,
  formData: FormData
): Promise<SendCodeState> {
  const email = String(formData.get("email") ?? "").trim();
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { status: "error", message: "Enter a valid email first" };
  }

  try {
    const res = await authApi.sendVerificationCode({
      email,
      purpose: "register",
    });
    return {
      status: "sent",
      message: `Code sent. Expires in ${Math.floor((res.expires_in ?? 600) / 60)} min.`,
      cooldown: 60,
    };
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 404 || err.status === 501) {
        return {
          status: "unavailable",
          message:
            "Email verification not yet enabled on this server — proceed without a code.",
        };
      }
      if (err.status === 429) {
        return {
          status: "error",
          message: "Too many requests. Wait a minute and try again.",
          cooldown: 60,
        };
      }
      return { status: "error", message: err.message };
    }
    return { status: "error", message: "Network error" };
  }
}
