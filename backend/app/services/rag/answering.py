"""
RAG answer generation.

Public API
----------
    generate_answer(
        question: str,
        user_id: str,
        model: str,
        history: list[dict],
        top_k: int = 5,
    ) -> dict

Return value
------------
{
    "answer": str,
    "model": str,
    "sources": list[dict],
}

Architecture rules:
  - Uses retrieval.py for vector search.
  - Uses get_client().chat_completions() for generation.
  - Uses the configured Ollama model and optional Ollama fallback model.
"""

from __future__ import annotations

import logging
from typing import List

from app.services.rag.retrieval import retrieve_chunks, retrieve_chunks_diversified
from app.services.wrapper.client import (
    WrapperError,
    get_client,
    get_generation_fallback_model,
)

log = logging.getLogger(__name__)

_DEFAULT_MINIMUM_DOCUMENT_COUNT = 2

_SYSTEM_TEMPLATE = """\
You are a knowledgeable and helpful AI tutor. Answer the student's question \
accurately and clearly.

First, carefully read the context sources provided below and decide whether \
they contain information relevant to the student's question.

IF the context contains relevant information:
- Answer the question using the context.
- Cite sources using [Source N] notation.
- When multiple sources are relevant, synthesize them into one answer.
- If some retrieved sources are weak or irrelevant, rely on the relevant ones only.
- If the answer is long, break it into clearly labelled sections with headings.
- Be thorough and complete; do not stop mid-answer.

IF the context does NOT contain relevant information about the question:
- Reply with ONLY this exact line and nothing else: [NO_CONTEXT]
- Do NOT attempt to answer from general knowledge.
- Do NOT provide any explanation.

Context from the student's uploaded documents:
{context_block}
"""

_NO_CONTEXT_SYSTEM = """\
You are a knowledgeable and helpful AI tutor. Answer the student's question \
accurately and clearly. No document context is available; answer from your \
general knowledge.
- If the answer is long, break it into clearly labelled sections with headings.
- Be thorough and complete; do not stop mid-answer.
"""


def _build_context_block(sources: List[dict]) -> str:
    if not sources:
        return "(no relevant document context found)"

    lines = []
    for index, source in enumerate(sources, start=1):
        title = source.get("document_title", "Unknown")
        snippet = source.get("snippet", "").strip()
        source_type = source.get("source_type", "")
        filename = source.get("filename")
        label = filename if filename else title
        lines.append(f"[Source {index}] {label} ({source_type}):\n{snippet}")
    return "\n\n".join(lines)


def _chat_with_fallback(model: str, messages: list, max_tokens: int = 4096) -> tuple[str, str]:
    """
    Attempt chat completion with *model*.

    If OLLAMA_FALLBACK_MODEL is configured, retry once with that model.
    Returns (answer_text, model_used).
    """
    fallback_chain = [model]
    fallback_model = get_generation_fallback_model()
    if fallback_model and fallback_model != model:
        fallback_chain.append(fallback_model)

    client = get_client()
    last_exc = None

    for index, attempt_model in enumerate(fallback_chain):
        is_last = index == len(fallback_chain) - 1
        try:
            response = client.chat_completions(
                model=attempt_model,
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
                max_retries=None if is_last else 0,
            )
            text = response["choices"][0]["message"]["content"]
            if attempt_model != model:
                log.info(
                    "answering: primary model %s failed, used fallback %s",
                    model,
                    attempt_model,
                )
            return text, attempt_model
        except (WrapperError, KeyError, IndexError, TypeError) as exc:
            log.warning("answering: model %s failed: %s", attempt_model, exc)
            last_exc = exc

    raise WrapperError(f"All models failed for answer generation. Last error: {last_exc}")


def generate_answer(
    question: str,
    user_id: str,
    model: str,
    history: List[dict] | None = None,
    top_k: int = 5,
    document_ids: List[str] | None = None,
    use_general_knowledge: bool = False,
) -> dict:
    """
    Generate a RAG-augmented answer for *question*.

    Returns:
        answer: str
        model: str
        sources: list[dict]
        out_of_context: bool
    """
    history = history or []
    out_of_context = False

    if use_general_knowledge:
        sources = []
    else:
        try:
            minimum_document_count = _minimum_document_count(
                top_k=top_k,
                document_ids=document_ids,
            )
            retrieve_kwargs = {
                "query_text": question,
                "user_id": user_id,
                "top_k": top_k,
                "document_ids": document_ids if document_ids else None,
            }
            if minimum_document_count > 1:
                sources = retrieve_chunks_diversified(
                    **retrieve_kwargs,
                    minimum_document_count=minimum_document_count,
                )
            else:
                sources = retrieve_chunks(**retrieve_kwargs)
        except WrapperError as exc:
            log.warning("answering: retrieval failed, proceeding without context: %s", exc)
            sources = []

    if use_general_knowledge or not sources:
        system_content = _NO_CONTEXT_SYSTEM
    else:
        system_content = _SYSTEM_TEMPLATE.format(
            context_block=_build_context_block(sources)
        )

    messages = [{"role": "system", "content": system_content}]
    for turn in history:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    answer_text, model_used = _chat_with_fallback(model=model, messages=messages)

    if not use_general_knowledge and answer_text.strip().startswith("[NO_CONTEXT]"):
        out_of_context = True
        answer_text = "The provided documents do not contain information about this topic."
        sources = []
        log.info("answering: out-of-context detected for question=%r", question[:80])

    return {
        "answer": answer_text,
        "model": model_used,
        "sources": sources,
        "out_of_context": out_of_context,
    }


def _minimum_document_count(
    *,
    top_k: int,
    document_ids: List[str] | None,
) -> int:
    if top_k <= 1:
        return 1
    if document_ids is not None and len(document_ids) <= 1:
        return 1
    return min(_DEFAULT_MINIMUM_DOCUMENT_COUNT, top_k)
