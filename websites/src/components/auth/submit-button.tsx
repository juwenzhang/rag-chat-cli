"use client";

import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";

/**
 * Full-width form submit button wired to `useFormStatus` — shows a
 * spinner + `pendingLabel` while the enclosing `<form action>` runs.
 * Shared by the login and register forms (which differ only in copy
 * and leading icon).
 */
export function SubmitButton({
  idleLabel,
  pendingLabel,
  icon,
}: {
  idleLabel: string;
  pendingLabel: string;
  icon: ReactNode;
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="lg" className="w-full" disabled={pending}>
      {pending ? (
        <>
          <Loader2 className="animate-spin" />
          {pendingLabel}
        </>
      ) : (
        <>
          {icon}
          {idleLabel}
        </>
      )}
    </Button>
  );
}
