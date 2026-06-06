import { ArrowRight, CheckCircle2, Palette, UserRound } from "lucide-react";
import Link from "next/link";

import { LanguageToggle } from "@/components/shell/language-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { requireUser } from "@/lib/auth/session.server";
import { getServerI18n } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const metadata = {
  title: "Account settings · lhx-rag",
};

export default async function AccountSettingsPage() {
  const { user } = await requireUser();
  const { t } = await getServerI18n();

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserRound className="size-5 text-primary" />
            {t("settings.accountTitle")}
          </CardTitle>
          <CardDescription>{t("settings.accountDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <InfoRow label={t("settings.email")} value={user.email} />
          <InfoRow
            label={t("settings.displayName")}
            value={user.display_name || t("settings.noDisplayName")}
          />
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background p-3">
            <div>
              <p className="text-sm font-medium">{t("settings.status")}</p>
              <p className="text-xs text-muted-foreground">{t("settings.active")}</p>
            </div>
            <Badge variant={user.is_active ? "success" : "secondary"}>
              <CheckCircle2 className="size-3" />
              {t("settings.active")}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{t("settings.preferences")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{t("settings.language")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("settings.languageDescription")}
                </p>
              </div>
              <LanguageToggle />
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{t("settings.theme")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("settings.themeDescription")}
                </p>
              </div>
              <ThemeToggle ariaLabel={t("theme.toggle")} tooltip={t("theme.toggle")} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Palette className="size-5 text-primary" />
              {t("settings.modelsTitle")}
            </CardTitle>
            <CardDescription>{t("settings.modelsDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline" className="w-full justify-between">
              <Link href="/settings/providers">
                {t("settings.openModels")}
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 truncate text-sm text-foreground">{value}</p>
    </div>
  );
}
