"""Prompt templates.

All prompts share the same grounding rules (GROUNDING_RULES). The retrieved
chunks are inserted as numbered sources ([S1], [S2]...) with their origin, so
the model can cite them and the UI can show them. Keeping prompts in one file
makes them easy to review and iterate on, separately from pipeline code.
"""

from __future__ import annotations

import json

from app.document_processing.tokenizer import TokenCounter
from app.models.domain import RetrievedChunk

GROUNDING_RULES = """\
You are an expert, honest career coach and technical interviewer.

Grounding rules (mandatory):
1. The CONTEXT below contains excerpts retrieved from the candidate's CV and the job description. Use it as your primary source of truth.
2. Never invent candidate experience, employers, projects, numbers, skills or certifications that are not in the CONTEXT (or, for answer evaluation, in the candidate's answer).
3. Never invent job requirements that are not in the CONTEXT.
4. If information needed is not in the CONTEXT, say explicitly that it is not available in the documents.
5. Clearly separate facts from the documents (cite them as [S1], [S2]...) from general career advice (prefix it with "General advice:").
6. Answer in English with a JSON object only, exactly following the requested schema. No markdown, no extra text."""


def format_context(chunks: list[RetrievedChunk], counter: TokenCounter, max_tokens: int = 1400) -> tuple[str, list[RetrievedChunk]]:
    """Render retrieved chunks as numbered sources, within a token budget.

    Chunks arrive sorted by relevance, so when the budget is reached it is the
    least relevant context that is dropped. Returns the text and the chunks
    actually used (those are the sources displayed to the user).
    """
    lines: list[str] = []
    used: list[RetrievedChunk] = []
    total = 0
    for result in chunks:
        block = f"[S{len(used) + 1}] ({result.chunk.source_label}, similarity {result.score:.2f})\n{result.chunk.text}"
        tokens = counter.count(block)
        if used and total + tokens > max_tokens:
            break
        lines.append(block)
        used.append(result)
        total += tokens
    return "\n\n".join(lines) if lines else "(no relevant context found)", used


def _schema_hint(example: dict) -> str:
    return json.dumps(example, indent=2, ensure_ascii=False)


# --- Match insights -------------------------------------------------------------

INSIGHTS_SCHEMA = {
    "summary": "2-4 sentences: overall fit, citing sources",
    "strengths": ["strength grounded in the CV, with [S#] citation"],
    "gaps": ["gap relative to the job requirements, with [S#] citation"],
    "recommendations": ["concrete action for the candidate; prefix general tips with 'General advice:'"],
}


def insights_prompt(facts: dict, context: str) -> str:
    return f"""TASK: Write a short, honest CV/job match analysis for the candidate.

The numeric scores and the skill lists below were computed by a deterministic matching engine. Do NOT change, recompute or contradict them; explain them.

COMPUTED FACTS:
{json.dumps(facts, indent=2, ensure_ascii=False)}

CONTEXT:
{context}

Return JSON with this structure:
{_schema_hint(INSIGHTS_SCHEMA)}
Use 2-5 items per list. Recommendations must be specific to this job (e.g. how to address a missing skill, what to highlight)."""


# --- Interview question -----------------------------------------------------------

QUESTION_SCHEMA = {
    "question": "the interview question, addressed to the candidate",
    "category": "technical | experience | behavioral | gap",
    "difficulty": "easy | medium | hard",
    "focus": "the skill or topic targeted",
    "rationale": "why this question matters for THIS job and THIS candidate, citing [S#]",
    "expected_points": ["2-4 points a strong answer should cover"],
}

CATEGORY_GUIDANCE = {
    "technical": "Ask a technical question about the focus skill that the job requires and that the CV claims. Refer to how the candidate used it (from the CV context) and probe depth: design choices, trade-offs, pitfalls.",
    "experience": "Ask the candidate to describe a concrete past experience from their CV that demonstrates the focus requirement. Mention the specific role/project from the CV context.",
    "behavioral": "Ask a behavioral question (answerable with the STAR method) about the focus theme, linked to the job's context (team, stakeholders, responsibilities).",
    "gap": "The focus skill/requirement is requested by the job but NOT evidenced in the CV. Ask a fair question that lets the candidate address this gap: transferable experience, how they would ramp up, or a conceptual question. Do not pretend the CV mentions it.",
}


def question_prompt(category: str, focus: str, context: str, previous_questions: list[str]) -> str:
    previous = "\n".join(f"- {q}" for q in previous_questions) or "(none)"
    return f"""TASK: Generate ONE personalised interview question for this candidate and this job.

CATEGORY: {category}
FOCUS: {focus}
GUIDANCE: {CATEGORY_GUIDANCE[category]}

The question must be specific to the CONTEXT (mention concrete elements such as a project, tool or requirement from it), not a generic question that could be asked to anyone. Do not repeat or paraphrase these previous questions:
{previous}

CONTEXT:
{context}

Return JSON with this structure (category must be "{category}"):
{_schema_hint(QUESTION_SCHEMA)}"""


# --- Answer evaluation --------------------------------------------------------------

EVALUATION_SCHEMA = {
    "criteria": {"relevance": 0, "specificity": 0, "structure": 0, "job_alignment": 0},
    "strengths": ["what the answer does well"],
    "weaknesses": ["what weakens the answer"],
    "missing_points": ["expected points or CV evidence the answer did not use"],
    "improvement_suggestions": ["concrete, actionable suggestion"],
    "improved_answer": "a stronger version of the answer (first person)",
    "grounding_note": "which facts come from the CV/answer vs. what is general advice",
}

RUBRIC = """\
Score each criterion from 0 to 10 (0-3 poor, 4-6 adequate, 7-8 good, 9-10 excellent):
- relevance: does the answer address the question that was actually asked?
- specificity: concrete examples, the candidate's own role, technologies, numbers/outcomes.
- structure: clear and concise; for experience/behavioral questions, Situation-Task-Action-Result.
- job_alignment: does it connect to the job's requirements shown in the CONTEXT?
Interview answers are partly subjective: judge against this rubric, do not claim an answer is objectively right or wrong (except for clear technical errors). A very short or off-topic answer must get low scores."""


def evaluation_prompt(question: str, category: str, expected_points: list[str], answer: str, context: str) -> str:
    points = "\n".join(f"- {p}" for p in expected_points)
    return f"""TASK: Evaluate the candidate's interview answer and coach them.

QUESTION ({category}): {question}

EXPECTED POINTS (from question generation):
{points}

CANDIDATE ANSWER:
\"\"\"{answer}\"\"\"

CONTEXT:
{context}

{RUBRIC}

For improved_answer: keep the candidate's voice, reuse facts from their answer and the CV context only. Where a specific detail would help but is not available, insert a placeholder in square brackets (e.g. "[number of users]") instead of inventing it.

Return JSON with this structure:
{_schema_hint(EVALUATION_SCHEMA)}"""
