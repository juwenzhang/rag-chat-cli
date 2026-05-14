import { chatApi } from "@/lib/api";

import { bffError, readJson, withAuthStream } from "../../_bff";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface ChatStreamBody {
  session_id: string;
  content: string;
  use_rag?: boolean;
}

export async function POST(req: Request) {
  const body = await readJson<ChatStreamBody>(req);
  if (!body.session_id || !body.content) {
    return bffError(
      "MISSING_FIELDS",
      "session_id and content are required.",
      400
    );
  }
  return withAuthStream((token) => chatApi.openChatStream(token, body));
}
