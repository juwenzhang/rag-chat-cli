import type { Metadata } from "next";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { RegisterForm } from "./register-form";

export const metadata: Metadata = {
  title: "Create account",
};

export default function RegisterPage() {
  return (
    <Card className="glass border-border/60 shadow-2xl shadow-primary/5">
      <CardHeader className="space-y-2 text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-lg shadow-primary/30">
          <span className="text-xl font-bold">R</span>
        </div>
        <CardTitle className="text-2xl">
          Get <span className="text-brand-gradient">started</span>
        </CardTitle>
        <CardDescription>
          Conversations, knowledge, and memory — all in one place.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <RegisterForm />
      </CardContent>
    </Card>
  );
}
