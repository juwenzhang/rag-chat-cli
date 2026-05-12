import { redirect } from "next/navigation";

import { getCurrentUser, getSession } from "@/lib/session";

export default async function Home() {
  const user = await getCurrentUser();
  if (user) redirect("/chat");
  // No valid user. If a stale cookie is hanging around, clear it via
  // the route handler so the proxy doesn't bounce us back here.
  const stale = await getSession();
  redirect(stale ? "/api/auth/clear-and-login" : "/login");
}
