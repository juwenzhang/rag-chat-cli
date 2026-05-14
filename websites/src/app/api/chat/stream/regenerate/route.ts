import { chatApi } from "@/lib/api";

import { bffError, readJson, withAuthStream } from "../../../_bff";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface RegenerateBody {
  session_id: string;
  use_rag?: boolean;
}

export async function POST(req: Request) {
  const body = await readJson<RegenerateBody>(req);
  if (!body.session_id) {
    return bffError("MISSING_FIELDS", "session_id is required.", 400);
  }
  return withAuthStream((token) => chatApi.openRegenerateStream(token, body));
}
