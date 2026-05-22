import { cookies } from "next/headers";

import {
  LOCALE_COOKIE,
  messages,
  resolveLocale,
  type MessageKey,
} from "./messages";

export async function getServerI18n() {
  const locale = resolveLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  const dictionary = messages[locale];

  return {
    locale,
    messages: dictionary,
    t: (key: MessageKey, vars?: Record<string, string | number>) => {
      const template = dictionary[key] ?? key;
      if (!vars) return template;
      return template.replace(/\{(\w+)\}/g, (match, name: string) => {
        const value = vars[name];
        return value == null ? match : String(value);
      });
    },
  };
}
