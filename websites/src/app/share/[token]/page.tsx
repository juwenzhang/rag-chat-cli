import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { shareApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getCurrentUser } from "@/lib/session";

import { ShareView } from "./share-view";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ token: string }>;
}

export async function generateMetadata(
  { params }: PageProps
): Promise<Metadata> {
  const { token } = await params;
  try {
    const data = await shareApi.fetchSharePublic(token);
    const snippet =
      data.user_message.content.slice(0, 80).replace(/\s+/g, " ") + "…";
    return {
      title: `Shared conversation — ${snippet}`,
      description: data.assistant_message.content
        .slice(0, 140)
        .replace(/\s+/g, " "),
      robots: { index: false, follow: false },
    };
  } catch {
    return { title: "Shared conversation" };
  }
}

export default async function SharePage({ params }: PageProps) {
  const { token } = await params;
  let data;
  try {
    data = await shareApi.fetchSharePublic(token);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const viewer = await getCurrentUser();
  const isOwner = viewer?.id === data.session_owner_id;
  return (
    <ShareView
      share={data}
      isAuthed={viewer !== null}
      isOwner={isOwner}
    />
  );
}
