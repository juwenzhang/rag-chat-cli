import type { Metadata } from "next";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getServerI18n } from "@/lib/i18n/server";

import { RegisterForm } from "./register-form";

export const metadata: Metadata = {
  title: "Create account",
};

export default async function RegisterPage() {
  const { t } = await getServerI18n();

  return (
    <Card className="glass border-border/60 shadow-2xl shadow-primary/5">
      <CardHeader className="space-y-2 text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-lg shadow-primary/30">
          <span className="text-xl font-bold">R</span>
        </div>
        <CardTitle className="text-2xl">
          {t("auth.register.title", { accent: "" })}{" "}
          <span className="text-brand-gradient">{t("auth.register.titleAccent")}</span>
        </CardTitle>
        <CardDescription>{t("auth.register.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <RegisterForm
          copy={{
            email: t("auth.email"),
            displayName: t("auth.displayName"),
            optional: t("common.optional"),
            displayNamePlaceholder: t("auth.displayNamePlaceholder"),
            password: t("auth.password"),
            passwordHint: t("auth.passwordHint"),
            code: t("auth.code"),
            codeEnabledHint: t("auth.codeEnabledHint"),
            codePlaceholder: t("auth.codePlaceholder"),
            sendCode: t("auth.sendCode"),
            submit: t("auth.register.submit"),
            pending: t("auth.register.pending"),
            hasAccount: t("auth.register.hasAccount"),
            signIn: t("auth.login.submit"),
          }}
        />
      </CardContent>
    </Card>
  );
}
