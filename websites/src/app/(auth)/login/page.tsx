import type { Metadata } from "next";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { LoginForm } from "./login-form";

export const metadata: Metadata = {
  title: "Sign in",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  const next = params.next ?? "/chat";

  return (
    <Card className="glass border-border/60 shadow-2xl shadow-primary/5">
      <CardHeader className="space-y-2 text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-lg shadow-primary/30">
          <span className="text-xl font-bold">R</span>
        </div>
        <CardTitle className="text-2xl">
          Welcome <span className="text-brand-gradient">back</span>
        </CardTitle>
        <CardDescription>
          Sign in to access your conversations, knowledge base, and memory.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <LoginForm next={next} />
      </CardContent>
    </Card>
  );
}
