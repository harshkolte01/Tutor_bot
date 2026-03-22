from __future__ import annotations

import logging
from typing import Any

from flask import current_app

from app.db.models.document import Document
from app.db.models.quiz import Quiz
from app.db.models.quiz_question import QuizQuestion
from app.db.models.quiz_question_source import QuizQuestionSource
from app.extensions import db
from app.services.analytics.events import EVENT_QUIZ_CREATED, record_event
from app.services.quiz.spec_parser import QuizRequestSpec
from app.services.quiz.validator import (
    QuizValidationError,
    extract_quiz_json,
    validate_quiz_payload,
)
from app.services.rag.retrieval import retrieve_chunks, retrieve_chunks_diversified
from app.services.wrapper.client import WrapperError, get_client

log = logging.getLogger(__name__)

PRIMARY_MODEL = "openrouter/google/gemma-3-27b-it:free"
FALLBACK_MODEL = "gemini/gemini-2.5-flash"
MAX_VALIDATION_ATTEMPTS = 3
MAX_SOURCE_DOCUMENT_COVERAGE = 3


class QuizGenerationError(RuntimeError):
    """Raised when quiz generation cannot complete successfully."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def generate_and_store_quiz(user_id: str, spec: QuizRequestSpec) -> Quiz:
    sources = _retrieve_context_sources(user_id=user_id, spec=spec)
    generated_payload, model_used = _generate_valid_payload(spec=spec, sources=sources)

    quiz = Quiz(
        user_id=user_id,
        title=generated_payload["title"],
        instructions=generated_payload.get("instructions"),
        spec_json=spec.to_dict(),
        total_marks=spec.total_marks,
        time_limit_sec=spec.time_limit_sec,
        model_used=model_used,
    )

    try:
        db.session.add(quiz)
        db.session.flush()

        source_map = {int(source["chunk_id"]): source for source in sources}
        for question_payload in generated_payload["questions"]:
            question = QuizQuestion(
                quiz_id=quiz.id,
                question_index=question_payload["question_index"],
                type=question_payload["type"],
                question_text=question_payload["question_text"],
                options_json=question_payload.get("options"),
                correct_json=question_payload["correct_json"],
                marks=question_payload["marks"],
                explanation=question_payload.get("explanation"),
            )
            db.session.add(question)
            db.session.flush()

            for chunk_id in question_payload["citation_chunk_ids"]:
                source = source_map[chunk_id]
                db.session.add(
                    QuizQuestionSource(
                        question_id=question.id,
                        chunk_id=chunk_id,
                        document_id=source["document_id"],
                        similarity_score=source["score"],
                        snippet=source.get("snippet"),
                    )
                )

        record_event(
            user_id=user_id,
            event_type=EVENT_QUIZ_CREATED,
            entity_type="quiz",
            entity_id=quiz.id,
            metadata={
                "quiz_id": quiz.id,
                "topic": spec.topic,
                "question_count": spec.question_count,
                "total_marks": spec.total_marks,
                "document_ids": spec.document_ids or [],
            },
        )
        db.session.commit()
        return quiz
    except Exception:
        db.session.rollback()
        raise


def _retrieve_context_sources(user_id: str, spec: QuizRequestSpec) -> list[dict[str, Any]]:
    top_k = min(max(spec.question_count * 2, 6), 12)
    allowed_document_ids = _load_allowed_document_ids(user_id=user_id, spec=spec)
    if not allowed_document_ids:
        raise QuizGenerationError(
            "No ready document content was found for this quiz request.",
            status_code=400,
        )

    target_document_count = _target_source_document_count(
        question_count=spec.question_count,
        allowed_document_count=len(allowed_document_ids),
        top_k=top_k,
    )

    try:
        if target_document_count > 1:
            sources = retrieve_chunks_diversified(
                query_text=spec.retrieval_query,
                user_id=user_id,
                top_k=top_k,
                document_ids=allowed_document_ids,
                minimum_document_count=target_document_count,
            )
        else:
            sources = retrieve_chunks(
                query_text=spec.retrieval_query,
                user_id=user_id,
                top_k=top_k,
                document_ids=allowed_document_ids,
            )
    except WrapperError as exc:
        log.error("quiz retrieval failed for user=%s: %s", user_id, exc)
        raise QuizGenerationError(
            "AI service unavailable, please try again.",
            status_code=503,
        ) from exc

    if not sources:
        raise QuizGenerationError(
            "No ready document content was found for this quiz request.",
            status_code=400,
        )

    return sources


def _generate_valid_payload(
    spec: QuizRequestSpec,
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    minimum_document_coverage = _document_coverage_target(
        sources=sources,
        question_count=spec.question_count,
    )
    raw_response, model_used = _chat_with_fallback(_build_generation_messages(spec, sources))
    raw_for_validation = raw_response

    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        try:
            payload = extract_quiz_json(raw_for_validation)
            validated = validate_quiz_payload(
                payload=payload,
                spec=spec,
                available_sources=sources,
                minimum_document_coverage=minimum_document_coverage,
            )
            return validated, model_used
        except QuizValidationError as exc:
            if attempt >= MAX_VALIDATION_ATTEMPTS:
                raise QuizGenerationError(
                    "Quiz generation failed validation after multiple attempts.",
                    status_code=502,
                ) from exc

            raw_for_validation, model_used = _chat_with_fallback(
                _build_repair_messages(
                    spec=spec,
                    sources=sources,
                    previous_response=raw_for_validation,
                    errors=exc.errors,
                )
            )

    raise QuizGenerationError("Quiz generation did not complete.", status_code=502)


def _chat_with_fallback(messages: list[dict[str, str]]) -> tuple[str, str]:
    client = get_client()
    primary_model = current_app.config.get("WRAPPER_DEFAULT_MODEL", PRIMARY_MODEL) or PRIMARY_MODEL
    model_chain = [primary_model]
    if FALLBACK_MODEL not in model_chain:
        model_chain.append(FALLBACK_MODEL)

    last_exc = None
    for index, model in enumerate(model_chain):
        try:
            response = client.chat_completions(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=4000,
                max_retries=None if index == len(model_chain) - 1 else 0,
            )
            content = response["choices"][0]["message"]["content"]
            return content, model
        except (WrapperError, KeyError, IndexError, TypeError) as exc:
            log.warning("quiz generation failed with model %s: %s", model, exc)
            last_exc = exc

    raise QuizGenerationError(
        f"AI service unavailable during quiz generation: {last_exc}",
        status_code=503,
    )


def _build_generation_messages(
    spec: QuizRequestSpec,
    sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    allowed_types = ", ".join(spec.question_types)
    source_block = _build_source_block(sources)
    document_coverage_rule = _build_document_coverage_rule(
        sources=sources,
        question_count=spec.question_count,
    )
    type_instructions: list[str] = []
    if "mcq_single" in spec.question_types:
        type_instructions.append(
            "- For mcq_single, provide 4 answer options and set correct_answer as "
            '{"option_index": 0}.'
        )
    if "true_false" in spec.question_types:
        type_instructions.append(
            '- For true_false, options must be ["True", "False"] and correct_answer '
            'must point to the correct option.'
        )

    system_prompt = (
        "You create grounded quiz JSON from the supplied study sources.\n"
        "Use only the information present in the provided sources.\n"
        "Return valid JSON only. Do not wrap it in markdown fences.\n"
        "Each question must include at least one citation chunk_id from the source list.\n"
        f"{document_coverage_rule}\n"
        "Do not invent chunk IDs or unsupported facts."
    )

    question_rules = "\n".join(type_instructions) if type_instructions else "- Use the requested question types."
    user_prompt = (
        f"Create a quiz with exactly {spec.question_count} questions.\n"
        f"Topic: {spec.topic}\n"
        f"Title: {spec.title}\n"
        f"Difficulty: {spec.difficulty}\n"
        f"Allowed question types: {allowed_types}\n"
        f"Total marks across all questions: {spec.total_marks}\n"
        f"Time limit in seconds: {spec.time_limit_sec if spec.time_limit_sec is not None else 'none'}\n"
        f"Additional instructions: {spec.instructions or 'none'}\n\n"
        "Return a JSON object with this exact shape:\n"
        "{\n"
        '  "title": "string",\n'
        '  "instructions": "string or null",\n'
        '  "questions": [\n'
        "    {\n"
        '      "type": "mcq_single or true_false",\n'
        '      "question_text": "string",\n'
        '      "options": ["option 1", "option 2"],\n'
        '      "correct_answer": {"option_index": 0},\n'
        '      "marks": 1,\n'
        '      "explanation": "short explanation",\n'
        '      "citations": [123, 456]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Question rules:\n"
        f"{question_rules}\n"
        "- Keep questions concise and answerable from the cited sources.\n"
        "- Avoid duplicate questions.\n"
        "- Cite 1 to 3 chunk IDs per question.\n\n"
        "Coverage rules:\n"
        f"{document_coverage_rule}\n\n"
        "Available sources:\n"
        f"{source_block}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_repair_messages(
    spec: QuizRequestSpec,
    sources: list[dict[str, Any]],
    previous_response: str,
    errors: list[str],
) -> list[dict[str, str]]:
    error_block = "\n".join(f"- {error}" for error in errors)
    source_block = _build_source_block(sources)
    document_coverage_rule = _build_document_coverage_rule(
        sources=sources,
        question_count=spec.question_count,
    )
    repair_prompt = (
        "The previous quiz response was invalid.\n"
        "Fix it and return corrected JSON only, with no markdown fences.\n"
        f"The quiz must still contain exactly {spec.question_count} questions.\n"
        f"Allowed question types: {', '.join(spec.question_types)}\n"
        "Every question must cite existing chunk IDs from the provided sources.\n\n"
        f"Coverage rules:\n{document_coverage_rule}\n\n"
        f"Validation errors:\n{error_block}\n\n"
        f"Previous response:\n{previous_response}\n\n"
        f"Available sources:\n{source_block}"
    )
    return [
        {
            "role": "system",
            "content": "Repair quiz JSON so it satisfies the validation rules exactly.",
        },
        {"role": "user", "content": repair_prompt},
    ]


def _build_source_block(sources: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for source in sources:
        snippet = (source.get("snippet") or "").strip().replace("\r", " ").replace("\n", " ")
        if len(snippet) > 450:
            snippet = snippet[:447].rstrip() + "..."
        lines.append(
            f"chunk_id={source['chunk_id']} | document_id={source['document_id']} | "
            f"title={source.get('document_title', 'Unknown')} | score={source.get('score', 0)}\n"
            f"{snippet}"
        )
    return "\n\n".join(lines)


def _load_allowed_document_ids(user_id: str, spec: QuizRequestSpec) -> list[str]:
    query = Document.query.filter(
        Document.user_id == user_id,
        Document.is_deleted.is_(False),
        Document.current_ingestion_id.isnot(None),
    )
    if spec.document_ids:
        query = query.filter(Document.id.in_(spec.document_ids))

    documents = query.order_by(Document.created_at.desc()).all()
    return [document.id for document in documents]


def _target_source_document_count(
    *,
    question_count: int,
    allowed_document_count: int,
    top_k: int,
) -> int:
    if allowed_document_count <= 1 or question_count <= 1 or top_k <= 1:
        return 1
    return min(
        allowed_document_count,
        question_count,
        top_k,
        MAX_SOURCE_DOCUMENT_COVERAGE,
    )


def _document_coverage_target(
    *,
    sources: list[dict[str, Any]],
    question_count: int,
) -> int:
    unique_document_ids = {
        source["document_id"]
        for source in sources
        if source.get("document_id")
    }
    return _target_source_document_count(
        question_count=question_count,
        allowed_document_count=len(unique_document_ids),
        top_k=len(sources),
    )


def _build_document_coverage_rule(
    *,
    sources: list[dict[str, Any]],
    question_count: int,
) -> str:
    document_coverage_target = _document_coverage_target(
        sources=sources,
        question_count=question_count,
    )
    if document_coverage_target <= 1:
        return "Use the most relevant supplied document chunks."
    return (
        f"Cover at least {document_coverage_target} different documents across the full quiz. "
        "Do not let a single document supply every question when multiple documents are available."
    )
