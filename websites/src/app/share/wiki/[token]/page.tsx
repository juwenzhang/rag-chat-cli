import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { wikiApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";

import { WikiShareView } from "./wiki-share-view";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ token: string }>;
}

export async function generateMetadata(
  { params }: PageProps
): Promise<Metadata> {
  const { token } = await params;
  try {
    const data = await wikiApi.fetchPageSharePublic(token);
    return {
      title: `${data.page_title} — ${data.wiki_name}`,
      description: data.page_body
        .slice(0, 140)
        .replace(/\s+/g, " "),
      robots: { index: false, follow: false },
    };
  } catch {
    return { title: "Shared wiki page" };
  }
}

export default async function WikiSharePage({ params }: PageProps) {
  const { token } = await params;
  let data;
  try {
    data = await wikiApi.fetchPageSharePublic(token);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  return <WikiShareView share={data} />;
}
