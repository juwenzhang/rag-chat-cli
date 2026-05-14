"use client";

import {
  ArrowRight,
  ExternalLink,
  GitFork,
  Loader2,
  LogIn,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { QACard } from "@/components/share/qa-card";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/browser";
import type { SharePublicOut } from "@/lib/api/types";
import { formatRelative } from "@/lib/utils";

interface Props {
  share: SharePublicOut;
  isAuthed: boolean;
  isOwner: boolean;
}

export function ShareView({ share, isAuthed, isOwner }: Props) {
  const router = useRouter();
  const [forking, setForking] = useState(false);

  const onFork = async () => {
    setForking(true);
    try {
      const meta = await api.chat.sessionFromShare(share.token);
      toast.success("Forked to your conversations");
      router.push(`/chat/${meta.id}`);
    } catch {
      toast.error("Failed to fork");
    } finally {
      setForking(false);
    }
  };

  return (
    <main className="relative min-h-dvh bg-background">
      {/* Brand stripe */}
      <header className="sticky top-0 z-10 border-b border-border/60 bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-md bg-brand-gradient text-white shadow shadow-primary/20">
              <span className="text-xs font-bold">R</span>
            </div>
            <span className="font-semibold tracking-tight">lhx-rag</span>
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <div className="mx-auto w-full max-w-3xl px-4 pb-16 pt-8 sm:px-6 sm:pt-12">
        {/* Title block */}
        <div className="mb-6 space-y-2 sm:mb-8">
          <p className="text-[11px] font-medium uppercase tracking-wider text-primary">
            Shared conversation
          </p>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
            A question and the answer it received
          </h1>
          <p className="text-sm text-muted-foreground">
            Shared {formatRelative(share.created_at)} · This link shows just one
            exchange from a longer conversation.
          </p>
        </div>

        <QACard
          userMessage={share.user_message}
          assistantMessage={share.assistant_message}
          footer={
            <div className="flex w-full flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                {isOwner
                  ? "You shared this — continue where you left off."
                  : isAuthed
                    ? "Want to keep exploring this thread?"
                    : "Sign in to start your own conversation."}
              </p>
              <div className="flex items-center gap-2">
                {isOwner ? (
                  <Button asChild>
                    <Link href={`/chat/${share.session_id}`}>
                      Continue here
                      <ArrowRight />
                    </Link>
                  </Button>
                ) : isAuthed ? (
                  <Button onClick={onFork} disabled={forking}>
                    {forking ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <GitFork />
                    )}
                    Fork as new conversation
                  </Button>
                ) : (
                  <Button asChild>
                    <Link href={`/login?next=/share/${share.token}`}>
                      <LogIn />
                      Sign in to fork
                    </Link>
                  </Button>
                )}
              </div>
            </div>
          }
        />

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>
            Powered by <span className="font-medium text-foreground">lhx-rag</span>
            {" "}— a self-hosted AI runner.
          </span>
          <Link
            href="/"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            Learn more
            <ExternalLink className="size-3" />
          </Link>
        </footer>
      </div>
    </main>
  );
}
