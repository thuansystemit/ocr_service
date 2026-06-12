"""Few-shot RAG retrieval + extraction prompt assembly (T-040).

Retrieval embeds the parsed document text and pulls the top-K most similar
labelled examples for *this tenant + schema* from Qdrant (the tenant filter and
post-query assertion are enforced inside ``QdrantService``). The prompt builder
injects those examples ahead of the document so the LLM has in-context guidance
without fine-tuning.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.domain.embeddings import get_embedder
from app.observability.logging import get_logger
from app.services.qdrant import get_qdrant_service

log = get_logger(__name__)

_MAX_EMBED_CHARS = 8000


async def retrieve_examples(
    *, tenant_id: UUID | str, schema_id: UUID | str, text: str, limit: int = 3
) -> list[dict[str, Any]]:
    """Top-K tenant-scoped few-shot examples for the given document text.

    Failures here are non-fatal: extraction can proceed zero-shot, so a Qdrant
    outage degrades quality rather than failing the document.
    """
    try:
        vector = await get_embedder().embed(text[:_MAX_EMBED_CHARS])
        return await get_qdrant_service().search(
            tenant_id=tenant_id, schema_id=schema_id, vector=vector, limit=limit
        )
    except Exception as exc:
        log.warning("rag.retrieval_failed", error=str(exc))
        return []


def build_extraction_prompt(
    *,
    text: str,
    schema_name: str,
    json_schema: dict[str, Any],
    required_fields: list[str],
    examples: list[dict[str, Any]],
) -> str:
    parts: list[str] = [
        f"You are an expert at extracting structured data from {schema_name} documents.",
        "Extract the fields defined by this JSON Schema. Return values as strings; "
        "use null for fields you cannot find. Report your own confidence in [0,1].",
        "",
        "JSON Schema:",
        json.dumps(json_schema, indent=2),
    ]
    if required_fields:
        parts += ["", "Required fields: " + ", ".join(required_fields)]

    if examples:
        parts += ["", "Here are labelled examples from similar documents:"]
        for i, ex in enumerate(examples, start=1):
            snippet = str(ex.get("input_text", ""))[:500]
            expected = json.dumps(ex.get("expected_json", {}), indent=2)
            parts += [f"\nExample {i} input:\n{snippet}", f"Example {i} output:\n{expected}"]

    parts += ["", "Now extract from this document:", "---", text, "---"]
    return "\n".join(parts)
