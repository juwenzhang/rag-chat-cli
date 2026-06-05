"""Optional image captioning helpers for uploaded assets."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from service.llm.client import ChatMessage, LLMError

if TYPE_CHECKING:
    from service.db.models import Asset
    from service.llm.client import LLMClient
    from service.platform.storage.base import ObjectStorage
    from settings import Settings

__all__ = ["describe_image_asset"]

logger = logging.getLogger(__name__)

_IMAGE_DESCRIPTION_PROMPT = (
    "Describe this image for retrieval. Include visible text, objects, chart/table contents, "
    "document fragments, and any useful context. Be concise but specific."
)


async def describe_image_asset(
    *,
    asset: Asset,
    storage: ObjectStorage,
    llm: LLMClient,
    settings: Settings,
) -> str | None:
    """Generate a text caption for an uploaded image when a vision model is configured."""

    if not settings.retrieval.image_caption_enabled:
        return None
    try:
        data = await storage.get_bytes(asset.storage_path)
        data_url = _data_url(asset.content_type, data)
        chunks: list[str] = []
        async for chunk in llm.chat_stream(
            [
                ChatMessage(
                    role="user",
                    content=_IMAGE_DESCRIPTION_PROMPT,
                    image_urls=(data_url,),
                )
            ],
            model=settings.retrieval.image_caption_model,
            tools=None,
        ):
            if chunk.delta:
                chunks.append(chunk.delta)
            if chunk.done:
                break
        caption = "".join(chunks).strip()
        return caption or None
    except (LLMError, OSError, ValueError) as exc:
        logger.warning("image captioning failed asset_id=%s: %s", asset.id, exc)
        return None


def _data_url(content_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"
