"use client";

import { Languages } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LOCALE_LABELS, LOCALES, type Locale } from "@/lib/i18n/messages";
import { useI18n } from "@/lib/i18n/provider";

export function LanguageToggle() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const { locale, setLocale, t } = useI18n();

  const switchLocale = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    startTransition(() => router.refresh());
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={pending}
          aria-label={t("common.currentLanguage", {
            language: LOCALE_LABELS[locale],
          })}
        >
          <Languages className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        <DropdownMenuLabel>{t("common.language")}</DropdownMenuLabel>
        {LOCALES.map((item) => (
          <DropdownMenuItem
            key={item}
            onSelect={() => switchLocale(item)}
            className={item === locale ? "font-medium text-primary" : undefined}
          >
            {LOCALE_LABELS[item]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
