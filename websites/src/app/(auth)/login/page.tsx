import type { Metadata } from "next";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getServerI18n } from "@/lib/i18n/server";

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
  const { t } = await getServerI18n();

  return (
    <Card className="glass border-border/60 shadow-2xl shadow-primary/5">
      <CardHeader className="space-y-2 text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-lg shadow-primary/30">
          <span className="text-xl font-bold">R</span>
        </div>
        <CardTitle className="text-2xl">
          {t("auth.login.title", { accent: "" })}{" "}
          <span className="text-brand-gradient">{t("auth.login.titleAccent")}</span>
        </CardTitle>
        <CardDescription>{t("auth.login.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <LoginForm
          next={next}
          copy={{
            email: t("auth.email"),
            password: t("auth.password"),
            forgot: t("auth.login.forgot"),
            submit: t("auth.login.submit"),
            pending: t("auth.login.pending"),
            noAccount: t("auth.login.noAccount"),
            createOne: t("auth.login.createOne"),
          }}
        />
      </CardContent>
    </Card>
  );
}
