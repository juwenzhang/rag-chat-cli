"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useActionState, useRef } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SubmitButton } from "@/features/auth/components/submit-button";

import {
  registerAction,
  sendCodeAction,
  type RegisterState,
  type SendCodeState,
} from "./actions";
import { CountdownButton } from "./countdown-button";

export interface RegisterFormCopy {
  email: string;
  displayName: string;
  optional: string;
  displayNamePlaceholder: string;
  password: string;
  passwordHint: string;
  code: string;
  codeEnabledHint: string;
  codePlaceholder: string;
  sendCode: string;
  submit: string;
  pending: string;
  hasAccount: string;
  signIn: string;
}

export function RegisterForm({ copy }: { copy: RegisterFormCopy }) {
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
        <Label htmlFor="email">{copy.email}</Label>
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
        <Label htmlFor="display_name">
          {copy.displayName} {" "}
          <span className="text-muted-foreground">({copy.optional})</span>
        </Label>
        <Input
          id="display_name"
          name="display_name"
          type="text"
          autoComplete="nickname"
          placeholder={copy.displayNamePlaceholder}
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="password">{copy.password}</Label>
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
        <p className="text-xs text-muted-foreground">{copy.passwordHint}</p>
      </div>

      {!codeUnavailable && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="code">
            {copy.code} {" "}
            <span className="text-muted-foreground">({copy.codeEnabledHint})</span>
          </Label>
          <div className="flex gap-2">
            <Input
              id="code"
              name="code"
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder={copy.codePlaceholder}
              autoComplete="one-time-code"
            />
            <CountdownButton
              key={cooldownKey}
              initialSeconds={codeState?.cooldown ?? 0}
              idleLabel={copy.sendCode}
              formAction={codeAction}
            />
          </div>
          {state?.fieldErrors?.code && (
            <p className="text-xs text-destructive">
              {state.fieldErrors.code}
            </p>
          )}
          {codeState?.status === "sent" && (
            <p className="text-xs text-success">{codeState.message}</p>
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

      <SubmitButton idleLabel={copy.submit} pendingLabel={copy.pending} icon={<Sparkles />} />

      <p className="text-center text-sm text-muted-foreground">
        {copy.hasAccount} {" "}
        <Link
          href="/login"
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {copy.signIn}
        </Link>
      </p>
    </form>
  );
}
