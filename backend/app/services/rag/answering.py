"""
RAG answer generation.

Public API
----------
    generate_answer(
        question: str,
        user_id:  str,
        model:    str,
        history:  list[dict],   # prior {"role": ..., "content": ...} turns
        top_k:    int = 5,
    ) -> dict

Return value
------------
{
    "answer":   str,            – assistant's reply
    "model":    str,            – model slug actually used
    "sources":  list[dict],     – chunk citations (chunk_id, document_id,
                                   snippet, score, document_title,
                                   source_type, filename)
}

Architecture rules:
  - Uses retrieve_chunks() from retrieval.py for vector search.
  - Calls wrapper via get_client().chat_completions().
  - Falls back to routeway/glm-4.5-air:free when the primary model fails.
"""

from __future__ import annotations

import logging
from typing import List

from app.services.rag.retrieval import retrieve_chunks, retrieve_chunks_diversified
from app.services.wrapper.client import WrapperError, get_client

log = logging.getLogger(__name__)

_FALLBACK_FAST   = "gemini/gemini-2.5-flash"   # reliable fallback if primary fails
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
- Be thorough and complete — do not stop mid-answer.

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
- Be thorough and complete — do not stop mid-answer.
"""


def _build_context_block(sources: List[dict]) -> str:
    if not sources:
        return "(no relevant document context found)"
    lines = []
    for i, s in enumerate(sources, start=1):
        title = s.get("document_title", "Unknown")
        snippet = s.get("snippet", "").strip()
        source_type = s.get("source_type", "")
        fname = s.get("filename")
        label = fname if fname else title
        lines.append(f"[Source {i}] {label} ({source_type}):\n{snippet}")
    return "\n\n".join(lines)


def _chat_with_fallback(model: str, messages: list, max_tokens: int = 4096) -> tuple[str, str]:
    """
    Attempt chat completion with *model*. On failure, try fallback chains.

    Returns
    -------
    (answer_text, model_used)
    """
    fallback_chain = [model]

    # Add gemini as fallback if the primary model (gemma) fails.
    for fb in [_FALLBACK_FAST]:
        if fb != model:
            fallback_chain.append(fb)

    client = get_client()
    last_exc = None

    for i, attempt_model in enumerate(fallback_chain):
        is_last = (i == len(fallback_chain) - 1)
        try:
            resp = client.chat_completions(
                model=attempt_model,
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
                # Fail fast on non-last models so 429 immediately tries the next fallback.
                max_retries=None if is_last else 0,
            )
            text = resp["choices"][0]["message"]["content"]
            if attempt_model != model:
                log.info(
                    "answering: primary model %s failed, used fallback %s",
                    model, attempt_model,
                )
            return text, attempt_model
        except (WrapperError, KeyError, IndexError) as exc:
            log.warning("answering: model %s failed: %s", attempt_model, exc)
            last_exc = exc

    raise WrapperError(
        f"All models failed for answer generation. Last error: {last_exc}"
    )


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

    Parameters
    ----------
    question : str
        The user's current message.
    user_id  : str
        UUID of the requesting user (for chunk scoping).
    model    : str
        Primary model slug selected by the router.
    history  : list[dict] | None
        Prior conversation turns as {"role": ..., "content": ...} dicts.
        Do not include the current question; it is appended automatically.
    top_k    : int
        Number of chunks to retrieve (default 5).
    document_ids : list[str] | None
        When provided, restrict RAG search to these document IDs only.
        ``None`` searches all of the user's documents (default behaviour).
    use_general_knowledge : bool
        When True, skip document retrieval entirely and answer from the
        model's general training knowledge.  Used when the user explicitly
        opts in after an out-of-context response.

    Returns
    -------
    dict
        answer          : str
        model           : str (model actually used)
        sources         : list[dict] (retrieval results, possibly empty)
        out_of_context  : bool — True when the retrieved docs don't cover
                          the question and the user must be offered a choice.
    """
    history = history or []
    out_of_context = False

    # ── 1. Retrieve relevant chunks (skipped when user chose general knowledge) ──
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

    # ── 2. Build prompt ──────────────────────────────────────────────────────
    if use_general_knowledge or not sources:
        system_content = _NO_CONTEXT_SYSTEM
    else:
        context_block = _build_context_block(sources)
        system_content = _SYSTEM_TEMPLATE.format(context_block=context_block)

    messages = [{"role": "system", "content": system_content}]

    # Include conversation history (user/assistant turns, no system)
    for turn in history:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Append the current question
    messages.append({"role": "user", "content": question})

    # ── 3. Generate answer ───────────────────────────────────────────────────
    answer_text, model_used = _chat_with_fallback(model=model, messages=messages)

    # ── 4. Detect out-of-context sentinel ────────────────────────────────────
    if not use_general_knowledge and answer_text.strip().startswith("[NO_CONTEXT]"):
        out_of_context = True
        answer_text = "The provided documents do not contain information about this topic."
        sources = []  # no useful sources to cite
        log.info("answering: out-of-context detected for question=%r", question[:80])

    return {
        "answer":         answer_text,
        "model":          model_used,
        "sources":        sources,
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
