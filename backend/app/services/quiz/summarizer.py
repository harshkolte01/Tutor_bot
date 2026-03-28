from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.db.models.quiz import Quiz
from app.services.wrapper.client import WrapperError, get_client, get_generation_model

log = logging.getLogger(__name__)

def summarize_attempt(quiz: Quiz, grading_result: dict[str, Any]) -> dict[str, Any]:
    fallback_summary = _build_fallback_summary(quiz=quiz, grading_result=grading_result)

    try:
        response = get_client().chat_completions(
            model=get_generation_model(),
            messages=_build_messages(quiz=quiz, grading_result=grading_result),
            temperature=0.2,
            max_tokens=800,
        )
        raw_content = response["choices"][0]["message"]["content"]
        summary_payload = _extract_json_object(raw_content)
        return _normalize_summary(summary_payload, fallback_summary)
    except (WrapperError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        log.warning("quiz summary generation failed, using fallback summary: %s", exc)
        return fallback_summary


def _build_messages(quiz: Quiz, grading_result: dict[str, Any]) -> list[dict[str, str]]:
    question_lines: list[str] = []
    for item in grading_result["results"]:
        question = item["question"]
        chosen_json = item.get("chosen_json") or {}
        chosen_text = chosen_json.get("option_text") or "No answer"
        correct_text = (question.correct_json or {}).get("option_text") or "Unknown"
        status = "correct" if item.get("is_correct") else "incorrect"
        if item.get("is_correct") is None:
            status = "unanswered"

        question_lines.append(
            f"Q{question.question_index + 1}: {status} | chosen={chosen_text} | "
            f"correct={correct_text} | marks_awarded={item['marks_awarded']}/{question.marks}"
        )

    system_prompt = (
        "You are generating a concise performance summary for a student's quiz attempt.\n"
        "Return valid JSON only with this shape:\n"
        "{\n"
        '  "overall": "string",\n'
        '  "strengths": ["string"],\n'
        '  "improvements": ["string"],\n'
        '  "recommended_next_step": "string"\n'
        "}\n"
        "Do not include markdown fences."
    )

    user_prompt = (
        f"Quiz title: {quiz.title}\n"
        f"Score: {grading_result['score']} / {grading_result['total_marks']}\n"
        f"Accuracy: {grading_result['accuracy_pct']}%\n"
        f"Correct: {grading_result['correct_count']}\n"
        f"Incorrect: {grading_result['incorrect_count']}\n"
        f"Unanswered: {grading_result['unanswered_count']}\n\n"
        "Question outcomes:\n"
        + "\n".join(question_lines)
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_json_object(raw_content: Any) -> dict[str, Any]:
    if isinstance(raw_content, dict):
        return raw_content
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise ValueError("summary response was empty")

    text = raw_content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
            last_error = ValueError("summary JSON was not an object")
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    raise ValueError(f"could not parse summary JSON: {last_error}")


def _normalize_summary(
    summary_payload: dict[str, Any],
    fallback_summary: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(fallback_summary)

    overall = _clean_text(summary_payload.get("overall"))
    if overall:
        normalized["overall"] = overall

    strengths = _normalize_list(summary_payload.get("strengths"))
    if strengths:
        normalized["strengths"] = strengths

    improvements = _normalize_list(summary_payload.get("improvements"))
    if improvements:
        normalized["improvements"] = improvements

    next_step = _clean_text(summary_payload.get("recommended_next_step"))
    if next_step:
        normalized["recommended_next_step"] = next_step

    return normalized


def _build_fallback_summary(quiz: Quiz, grading_result: dict[str, Any]) -> dict[str, Any]:
    accuracy_pct = grading_result["accuracy_pct"]
    correct_count = grading_result["correct_count"]
    incorrect_count = grading_result["incorrect_count"]
    unanswered_count = grading_result["unanswered_count"]
    answered_count = grading_result["answered_count"]

    if accuracy_pct >= 90:
        overall = f"Excellent work on {quiz.title}. You showed strong command of the material."
        strengths = ["You answered most questions correctly with consistent accuracy."]
        improvements = ["Keep practicing to maintain this level of performance."]
    elif accuracy_pct >= 60:
        overall = f"Good progress on {quiz.title}. You understand several key ideas but still have gaps to close."
        strengths = [f"You answered {correct_count} question(s) correctly."]
        improvements = ["Review the questions you missed and compare your answers with the correct options."]
    else:
        overall = f"You need more review on {quiz.title}. This attempt shows that the core concepts need reinforcement."
        strengths = ["You completed the attempt, which is a strong starting point for review."]
        improvements = ["Revisit the source material and focus on the basics before taking another attempt."]

    if incorrect_count > 0:
        improvements.append(f"You missed {incorrect_count} answered question(s).")
    if unanswered_count > 0:
        improvements.append(f"You left {unanswered_count} question(s) unanswered.")

    if answered_count == 0:
        strengths = ["Start by attempting each question so your understanding can be measured."]

    recommended_next_step = (
        "Review the explanations for missed questions, revisit the source material, and retake a short quiz."
    )

    return {
        "overall": overall,
        "strengths": strengths,
        "improvements": improvements,
        "recommended_next_step": recommended_next_step,
        "accuracy_pct": accuracy_pct,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "unanswered_count": unanswered_count,
        "score": grading_result["score"],
        "total_marks": grading_result["total_marks"],
    }


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            normalized.append(text)
    return normalized


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
