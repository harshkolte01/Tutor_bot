from __future__ import annotations

import json
import re
from typing import Any

from app.services.quiz.spec_parser import QuizRequestSpec


class QuizValidationError(ValueError):
    """Raised when a generated quiz payload cannot be normalized safely."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def extract_quiz_json(raw_payload: Any) -> Any:
    if isinstance(raw_payload, (dict, list)):
        return raw_payload
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        raise QuizValidationError(["Model response did not contain quiz JSON."])

    text = raw_payload.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)

    candidates = [text]
    obj_start = text.find("{")
    obj_end = text.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        candidates.append(text[obj_start : obj_end + 1])

    last_error = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    raise QuizValidationError([f"Model response was not valid JSON: {last_error}"])


def validate_quiz_payload(
    payload: Any,
    spec: QuizRequestSpec,
    available_sources: list[dict[str, Any]],
    minimum_document_coverage: int = 1,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise QuizValidationError(["Quiz payload must be a JSON object."])

    errors: list[str] = []
    source_map = {
        int(source["chunk_id"]): source
        for source in available_sources
        if source.get("chunk_id") is not None
    }

    questions_raw = payload.get("questions")
    if not isinstance(questions_raw, list):
        raise QuizValidationError(["Quiz payload must include a questions array."])
    if len(questions_raw) != spec.question_count:
        errors.append(
            f"Expected exactly {spec.question_count} questions, got {len(questions_raw)}."
        )

    normalized_questions: list[dict[str, Any]] = []
    provided_marks: list[float | None] = []

    for index, question_raw in enumerate(questions_raw):
        question_errors, normalized_question, marks_value = _normalize_question(
            question_raw=question_raw,
            index=index,
            spec=spec,
            source_map=source_map,
        )
        errors.extend(question_errors)
        if normalized_question is not None:
            normalized_questions.append(normalized_question)
            provided_marks.append(marks_value)

    if minimum_document_coverage > 1:
        cited_document_ids: set[str] = set()
        for question in normalized_questions:
            for chunk_id in question["citation_chunk_ids"]:
                source = source_map.get(chunk_id)
                document_id = source.get("document_id") if source else None
                if document_id:
                    cited_document_ids.add(document_id)
        if len(cited_document_ids) < minimum_document_coverage:
            errors.append(
                "Quiz must cite at least "
                f"{minimum_document_coverage} different documents across all questions."
            )

    if errors:
        raise QuizValidationError(errors)

    marks = _finalize_marks(provided_marks=provided_marks, total_marks=spec.total_marks)
    for question, mark in zip(normalized_questions, marks):
        question["marks"] = mark

    title = _clean_text(payload.get("title")) or spec.title
    instructions = _clean_text(payload.get("instructions")) or spec.instructions

    return {
        "title": title[:255],
        "instructions": instructions,
        "questions": normalized_questions,
    }


def _normalize_question(
    question_raw: Any,
    index: int,
    spec: QuizRequestSpec,
    source_map: dict[int, dict[str, Any]],
) -> tuple[list[str], dict[str, Any] | None, float | None]:
    label = f"questions[{index}]"
    if not isinstance(question_raw, dict):
        return [f"{label} must be an object."], None, None

    errors: list[str] = []
    question_type = _normalize_question_type(question_raw.get("type"))
    if question_type not in spec.question_types:
        allowed = ", ".join(spec.question_types)
        errors.append(f"{label}.type must be one of: {allowed}.")

    question_text = _clean_text(
        question_raw.get("question_text") or question_raw.get("prompt")
    )
    if not question_text:
        errors.append(f"{label}.question_text is required.")

    options = _normalize_options(question_type, question_raw.get("options"), label, errors)
    correct_json = _normalize_correct_answer(
        question_type=question_type,
        raw_value=question_raw.get("correct_answer", question_raw.get("answer")),
        options=options,
        label=label,
        errors=errors,
    )
    citation_chunk_ids = _normalize_citations(
        raw_value=question_raw.get("citations", question_raw.get("citation_chunk_ids")),
        label=label,
        source_map=source_map,
        errors=errors,
    )

    marks = _coerce_positive_float(question_raw.get("marks"))
    explanation = _clean_text(question_raw.get("explanation"))

    if errors:
        return errors, None, None

    return (
        [],
        {
            "question_index": index,
            "type": question_type,
            "question_text": question_text,
            "options": options,
            "correct_json": correct_json,
            "marks": marks,
            "explanation": explanation,
            "citation_chunk_ids": citation_chunk_ids,
        },
        marks,
    )


def _normalize_question_type(raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        return ""
    normalized = raw_value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "mcq": "mcq_single",
        "multiple_choice": "mcq_single",
        "single_choice": "mcq_single",
        "truefalse": "true_false",
        "true_or_false": "true_false",
    }
    return aliases.get(normalized, normalized)


def _normalize_options(
    question_type: str,
    raw_value: Any,
    label: str,
    errors: list[str],
) -> list[str] | None:
    if question_type == "true_false":
        return ["True", "False"]

    if not isinstance(raw_value, list) or len(raw_value) < 2:
        errors.append(f"{label}.options must be a list with at least 2 entries.")
        return None

    options: list[str] = []
    for option in raw_value:
        option_text = _clean_text(option)
        if not option_text:
            errors.append(f"{label}.options contains an empty value.")
            return None
        options.append(option_text)
    return options


def _normalize_correct_answer(
    question_type: str,
    raw_value: Any,
    options: list[str] | None,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not options:
        errors.append(f"{label} could not determine options for correct_answer validation.")
        return None

    candidate = raw_value
    if isinstance(raw_value, dict):
        for key in ("option_index", "index", "answer", "correct_option", "correct_answer"):
            if key in raw_value:
                candidate = raw_value[key]
                break

    index = _resolve_answer_index(candidate, options, question_type=question_type)
    if index is None:
        errors.append(f"{label}.correct_answer must reference one of the provided options.")
        return None

    return {
        "option_index": index,
        "option_text": options[index],
    }


def _resolve_answer_index(
    candidate: Any,
    options: list[str],
    *,
    question_type: str,
) -> int | None:
    if isinstance(candidate, bool) and question_type == "true_false":
        return 0 if candidate else 1

    if isinstance(candidate, int):
        if candidate == 0:
            return 0
        if 0 < candidate <= len(options):
            return candidate - 1
        if 0 <= candidate < len(options):
            return candidate
        return None

    if isinstance(candidate, str):
        value = candidate.strip()
        if not value:
            return None

        lowered = value.lower()
        if lowered.isdigit():
            return _resolve_answer_index(int(lowered), options, question_type=question_type)

        if len(lowered) == 1 and lowered in "abcdefghijklmnopqrstuvwxyz":
            alpha_index = ord(lowered) - ord("a")
            if 0 <= alpha_index < len(options):
                return alpha_index

        for index, option in enumerate(options):
            if option.strip().lower() == lowered:
                return index

    return None


def _normalize_citations(
    raw_value: Any,
    label: str,
    source_map: dict[int, dict[str, Any]],
    errors: list[str],
) -> list[int]:
    if not isinstance(raw_value, list) or not raw_value:
        errors.append(f"{label}.citations must be a non-empty list of chunk IDs.")
        return []

    citation_chunk_ids: list[int] = []
    for item in raw_value:
        chunk_id = item.get("chunk_id") if isinstance(item, dict) else item

        try:
            chunk_id = int(chunk_id)
        except (TypeError, ValueError):
            errors.append(f"{label}.citations contains a non-integer chunk ID.")
            return []

        if chunk_id not in source_map:
            errors.append(f"{label}.citations references unknown chunk_id {chunk_id}.")
            return []
        if chunk_id not in citation_chunk_ids:
            citation_chunk_ids.append(chunk_id)

    return citation_chunk_ids


def _finalize_marks(provided_marks: list[float | None], total_marks: float) -> list[float]:
    if (
        provided_marks
        and all(mark is not None and mark > 0 for mark in provided_marks)
        and abs(sum(provided_marks) - total_marks) <= 0.05
    ):
        marks = [round(float(mark), 2) for mark in provided_marks]
        delta = round(total_marks - sum(marks), 2)
        marks[-1] = round(marks[-1] + delta, 2)
        return marks

    count = len(provided_marks)
    if count == 0:
        return []

    base = round(total_marks / count, 2)
    marks = [base for _ in range(count)]
    delta = round(total_marks - sum(marks), 2)
    marks[-1] = round(marks[-1] + delta, 2)
    return marks


def _coerce_positive_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, 2) if parsed > 0 else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
