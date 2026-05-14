"use client";

import { Send } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * "Send code" button with a resend cooldown. `formAction` posts the
 * send-code server action; the button stays disabled and counts down
 * while `initialSeconds > 0`.
 */
export function CountdownButton({
  initialSeconds,
  formAction,
}: {
  initialSeconds: number;
  formAction: (formData: FormData) => void;
}) {
  const [remaining, setRemaining] = useState(initialSeconds);

  useEffect(() => {
    if (remaining <= 0) return;
    const id = setInterval(
      () => setRemaining((n) => Math.max(0, n - 1)),
      1000
    );
    return () => clearInterval(id);
  }, [remaining]);

  return (
    <Button
      type="submit"
      variant="outline"
      formAction={formAction}
      disabled={remaining > 0}
      className={cn("shrink-0", remaining > 0 && "min-w-[110px]")}
    >
      <Send className="size-3.5" />
      {remaining > 0 ? `${remaining}s` : "Send code"}
    </Button>
  );
}
