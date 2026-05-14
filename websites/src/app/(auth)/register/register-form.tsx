"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useActionState, useRef } from "react";

import { SubmitButton } from "@/components/auth/submit-button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  registerAction,
  sendCodeAction,
  type RegisterState,
  type SendCodeState,
} from "./actions";
import { CountdownButton } from "./countdown-button";

export function RegisterForm() {
  const [state, formAction] = useActionState<RegisterState | undefined, FormData>(
    registerAction,
    undefined
  );
  const [codeState, codeAction] = useActionState<
    SendCodeState | undefined,
    FormData
  >(sendCodeAction, undefined);

  const emailRef = useRef<HTMLInputElement>(null);
  const codeUnavailable = codeState?.status === "unavailable";
  const cooldownKey = `${codeState?.status ?? "idle"}-${codeState?.cooldown ?? 0}`;

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          ref={emailRef}
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          placeholder="you@example.com"
        />
        {state?.fieldErrors?.email && (
          <p className="text-xs text-destructive">{state.fieldErrors.email}</p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="display_name">Display name <span className="text-muted-foreground">(optional)</span></Label>
        <Input
          id="display_name"
          name="display_name"
          type="text"
          autoComplete="nickname"
          placeholder="What should we call you?"
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
        />
        {state?.fieldErrors?.password && (
          <p className="text-xs text-destructive">
            {state.fieldErrors.password}
          </p>
        )}
        <p className="text-xs text-muted-foreground">At least 8 characters.</p>
      </div>

      {!codeUnavailable && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="code">
            Email verification code <span className="text-muted-foreground">(if enabled)</span>
          </Label>
          <div className="flex gap-2">
            <Input
              id="code"
              name="code"
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder="6-digit code"
              autoComplete="one-time-code"
            />
            <CountdownButton
              key={cooldownKey}
              initialSeconds={codeState?.cooldown ?? 0}
              formAction={codeAction}
            />
          </div>
          {state?.fieldErrors?.code && (
            <p className="text-xs text-destructive">
              {state.fieldErrors.code}
            </p>
          )}
          {codeState?.status === "sent" && (
            <p className="text-xs text-success">
              {codeState.message}
            </p>
          )}
          {codeState?.status === "error" && (
            <p className="text-xs text-destructive">{codeState.message}</p>
          )}
        </div>
      )}

      {codeUnavailable && (
        <Alert>
          <AlertDescription className="text-xs">
            {codeState.message}
          </AlertDescription>
        </Alert>
      )}

      {state?.error && (
        <Alert variant="destructive">
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      )}

      <SubmitButton
        idleLabel="Create account"
        pendingLabel="Creating account…"
        icon={<Sparkles />}
      />

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          Sign in
        </Link>
      </p>
    </form>
  );
}
