import { assetApi } from "@/lib/api";

import { withAuth } from "../../_bff";

export async function POST(req: Request) {
  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return Response.json(
      { error: "BAD_REQUEST", message: "file is required" },
      { status: 400 }
    );
  }
  return withAuth((token) => assetApi.uploadImage(token, file));
}
