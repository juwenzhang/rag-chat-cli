import { getServerI18n } from "@/lib/i18n/server";

import { SettingsNav } from "@/features/settings/components/settings-nav";

export default async function SettingsLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { t } = await getServerI18n();

  return (
    <div className="h-full overflow-y-auto bg-muted/30">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
        <header className="space-y-4">
          <div className="space-y-1.5">
            <h1 className="text-2xl font-semibold tracking-tight">
              {t("settings.title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t("settings.description")}
            </p>
          </div>
          <SettingsNav
            items={[
              { href: "/settings/account", label: t("settings.account") },
              { href: "/settings/providers", label: t("settings.models") },
            ]}
          />
        </header>
        {children}
      </div>
    </div>
  );
}
