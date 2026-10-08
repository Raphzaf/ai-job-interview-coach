"""Offline generator: deterministic, template + heuristic outputs without an LLM.

Why it exists:
- The app stays usable (and demoable) with no API key, no network or when the
  LLM provider is down: the pipeline falls back here and labels the result
  "offline" / "offline-fallback" in the UI. It never pretends to be the LLM.
- It still uses the RAG building blocks: the retrieved context, the match
  analysis and embeddings (for semantic relevance of answers).

It is intentionally simpler than the LLM: question wording comes from
templates and answer scoring from transparent heuristics.
"""

from __future__ import annotations

import re

import numpy as np

from app.embeddings.service import EmbeddingService
from app.matching.matcher import rescale
from app.matching.skills import extract_skills
from app.models.domain import RetrievedChunk
from app.models.schemas import (
    AnswerEvaluation,
    CriteriaScores,
    InterviewQuestion,
    MatchInsights,
    MatchReport,
)
from app.rag.interview_planner import PlannedQuestion

_STAR_MARKERS = {
    "situation": r"\b(when|while|during|at (?:my|our|the)|in my (?:role|previous|last)|project|context)\b",
    "task": r"\b(goal|objective|needed to|had to|challenge|responsible for|task|problem)\b",
    "action": r"\b(i|we) (built|designed|implemented|led|created|developed|decided|used|wrote|set up|introduced|organised|organized|analysed|analyzed|trained|deployed|migrated|automated)\b",
    "result": r"(\bresult|\breduc|\bincreas|\bimprov|\bachiev|\boutcome|\bsaved|\bgrew|\bdelivered|%)",
}


_STOPWORDS = set(
    "a an and are as at be by can did do for from had has have how i in is it its me my of on or our "
    "that the their there this to was we were what when which while who why with you your would about "
    "tell time walk through describe give example there".split()
)


def _shorten(line: str, max_chars: int = 180) -> str:
    line = line.removeprefix("- ").strip()
    return line if len(line) <= max_chars else line[: max_chars - 1].rsplit(" ", 1)[0] + "…"


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9+#.-]{2,}", text.lower()) if w not in _STOPWORDS}


def evidence_line(context: list[RetrievedChunk], focus: str) -> str:
    """Pick the single CV line that best illustrates `focus`.

    Prefer a line that literally mentions the focus skill, in an experience or
    project section rather than the bare skills list; else the top CV chunk.
    """
    cv_chunks = [r.chunk for r in context if r.chunk.doc_type == "cv"]
    focus_skills = set(extract_skills(focus)) or {focus.lower()}
    candidates: list[tuple[int, str]] = []
    for rank, chunk in enumerate(cv_chunks):
        is_skill_list = "skill" in chunk.section.lower()
        for line in chunk.text.split("\n"):
            mentioned = set(extract_skills(line)) & focus_skills or (focus.lower() in line.lower())
            if mentioned:
                candidates.append((rank + (10 if is_skill_list else 0) - ("- " in line[:2]), line))
    if candidates:
        return _shorten(min(candidates)[1])
    return _shorten(cv_chunks[0].text.split("\n")[0]) if cv_chunks else ""


class OfflineGenerator:
    def __init__(self, embedder: EmbeddingService):
        self.embedder = embedder

    # --- Match insights -------------------------------------------------------

    def insights(self, match: MatchReport) -> MatchInsights:
        score = match.overall_score
        level = "strong" if score >= 70 else "moderate" if score >= 45 else "limited"
        matched = [s.name for s in match.matching_skills][:5]
        missing = [s.name for s in match.missing_skills if s.importance == "required"][:4]
        summary = f"The CV shows a {level} match with this job ({score:.0f}/100, computed score)."
        if matched:
            summary += f" Key matching skills: {', '.join(matched)}."
        if missing:
            summary += f" Required skills not found in the CV: {', '.join(missing)}."

        recommendations: list[str] = []
        for skill in missing[:3]:
            recommendations.append(
                f"If you have used {skill}, add a concrete example to your CV; otherwise prepare to explain "
                f"how your related experience transfers and how you would learn it."
            )
        partial = [r for r in match.requirements if r.status == "partial"][:2]
        for r in partial:
            recommendations.append(f"Make your CV more explicit about: “{r.text.rstrip('.')}”.")
        recommendations.append(
            "General advice: quantify achievements (numbers, scale, impact) for the experience most related to this role."
        )
        return MatchInsights(
            summary=summary,
            strengths=match.strengths or ["No explicit strength could be derived from the documents."],
            gaps=match.gaps,
            recommendations=recommendations,
        )

    # --- Interview question ------------------------------------------------------

    def question(self, plan: PlannedQuestion, context: list[RetrievedChunk]) -> InterviewQuestion:
        focus = plan.focus.rstrip(".")
        evidence = evidence_line(context, focus)
        if plan.category == "technical":
            q = (f"Your CV mentions: “{evidence}”. " if evidence else "") + (
                f"Can you walk me through how you used {focus} there: the technical choices you made, "
                f"the trade-offs, and what you would do differently today?"
            )
            points = [f"Concrete use of {focus} in a real project", "Technical decisions and trade-offs",
                      "Measurable outcome or lesson learned"]
            difficulty = "medium"
        elif plan.category == "experience":
            q = (f"The role asks for: “{focus}”. Which experience from your background best demonstrates this? "
                 "Describe the context, your personal role, and the outcome.")
            points = ["A specific example from the CV", "The candidate's own actions", "Quantified result"]
            difficulty = "medium"
        elif plan.category == "gap":
            q = (f"The job mentions {focus}, which does not clearly appear in your CV. "
                 "What related experience do you have, and how would you get up to speed in your first months?")
            points = ["Honest statement of current level", "Transferable experience from the CV",
                      "Concrete learning plan"]
            difficulty = "hard"
        else:
            q = (f"Tell me about a time you were {focus}. What was the situation, what did you do, "
                 "and what was the result?")
            points = ["Situation and task", "Actions taken personally", "Result and what was learned"]
            difficulty = "easy"
        return InterviewQuestion(
            question=q, category=plan.category, difficulty=difficulty, focus=focus[:120],
            rationale=f"Selected by the matching engine: '{focus}' is relevant to the job"
            + (" and is a gap in the CV." if plan.category == "gap" else "."),
            expected_points=points,
        )

    # --- Answer evaluation ----------------------------------------------------------

    def evaluate(
        self, question: InterviewQuestion, answer: str, context: list[RetrievedChunk], job_skills: list[str]
    ) -> AnswerEvaluation:
        words = re.findall(r"\w+", answer)
        n_words = len(words)
        lowered = answer.lower()

        # Relevance: all-MiniLM-L6-v2 is trained for symmetric similarity, so
        # question->answer cosine is a weak signal on its own (a good technical
        # answer measured 0.16, an off-topic one 0.07). It is therefore combined
        # with lexical evidence: key terms and skills of the question reused in the answer.
        vecs = self.embedder.embed([answer, question.question])
        semantic = rescale(float(vecs[0] @ vecs[1]), 0.05, 0.35)
        lexical = min(1.0, len(_content_words(question.question + " " + question.focus) & _content_words(answer)) / 4)
        question_skills = set(extract_skills(question.question + " " + question.focus))
        skill_cov = len(question_skills & set(extract_skills(answer))) / len(question_skills) if question_skills else lexical
        relevance = 10 * max(semantic, 0.5 * lexical + 0.5 * skill_cov)
        if n_words < 15:
            relevance = min(relevance, 3.0)

        # Specificity: numbers, named technologies, first-person actions, enough detail.
        numbers = len(re.findall(r"\d+(?:[.,]\d+)?\s*%?", answer))
        skills_named = extract_skills(answer)
        has_action = bool(re.search(_STAR_MARKERS["action"], lowered))
        specificity = min(10.0, 2 * min(numbers, 2) + 1.5 * min(len(skills_named), 3) + 2 * has_action
                          + (1.5 if n_words >= 60 else 0))

        # Structure: STAR markers for story-type questions (experience/behavioral);
        # for technical/gap questions, a developed answer of reasonable length.
        star = {k: bool(re.search(p, lowered)) for k, p in _STAR_MARKERS.items()}
        uses_star = question.category in ("experience", "behavioral")
        n_sentences = len([x for x in re.split(r"[.!?]+", answer) if x.strip()])
        if uses_star:
            structure = min(10.0, 2 * sum(star.values()) + (2 if 50 <= n_words <= 350 else 0))
        else:
            structure = min(10.0, 2 * min(n_sentences, 3) + (2 if 40 <= n_words <= 300 else 0) + 2 * has_action)

        # Job alignment: required job skills mentioned + similarity to job context.
        job_chunks = [r for r in context if r.chunk.doc_type == "job"]
        job_sim = 0.0
        if job_chunks:
            job_vecs = self.embedder.embed([r.chunk.text for r in job_chunks])
            job_sim = float(np.max(job_vecs @ vecs[0]))
        mentioned = [s for s in skills_named if s in job_skills]
        alignment = 10 * (0.6 * rescale(job_sim, 0.15, 0.6) + 0.4 * min(1.0, len(mentioned) / 2))

        criteria = CriteriaScores(
            relevance=round(relevance), specificity=round(specificity),
            structure=round(structure), job_alignment=round(alignment),
        )

        # Missing points (heuristic): absent STAR components and the focus topic itself.
        missing = [f"No clear {k} described" for k, present in star.items() if not present] if uses_star else []
        if question.focus.lower() not in lowered and not (question_skills & set(skills_named)):
            missing.append(f"No explicit reference to {question.focus}")

        strengths, weaknesses, suggestions = [], [], []
        if criteria.relevance >= 6:
            strengths.append("The answer addresses the question that was asked.")
        else:
            weaknesses.append("The answer only partially addresses the question.")
            suggestions.append("Start by answering the question directly in one sentence, then give your example.")
        if numbers:
            strengths.append("Uses concrete numbers, which makes the impact credible.")
        else:
            weaknesses.append("No measurable outcome is given.")
            suggestions.append("Quantify the result (time saved, accuracy, users, revenue...).")
        if skills_named:
            strengths.append("Names specific technologies: " + ", ".join(skills_named[:5]) + ".")
        missing_star = [k for k, present in star.items() if not present]
        if uses_star and missing_star:
            weaknesses.append("The STAR structure is incomplete (missing: " + ", ".join(missing_star) + ").")
            suggestions.append("Structure the answer as Situation, Task, Action, Result.")
        if n_words < 40:
            weaknesses.append(f"The answer is very short ({n_words} words).")
            suggestions.append("Develop one concrete example in 4-6 sentences.")
        if not mentioned and job_skills:
            suggestions.append("Connect your example to the job's requirements, e.g. " + ", ".join(job_skills[:3]) + ".")

        evidence = evidence_line(context, question.focus) or "[a relevant project from your CV]"
        improved = (
            f"Situation: In a previous role, I worked on the following (from my CV): {evidence} "
            f"Task: I was responsible for [the specific goal related to {question.focus}]. "
            "Action: I [2-3 concrete actions you personally took, naming the tools you used]. "
            "Result: This led to [a measurable outcome], and I learned [a lesson relevant to this role]."
        )
        return AnswerEvaluation(
            criteria=criteria,
            strengths=strengths,
            weaknesses=weaknesses,
            missing_points=missing,
            improvement_suggestions=suggestions or ["Keep the same structure and add one more measurable result."],
            improved_answer=improved,
            grounding_note=(
                "Offline heuristic evaluation (no LLM): scores come from semantic similarity, STAR markers, "
                "numbers and skills detected in the answer. The improved answer is a template; bracketed "
                "parts must be filled with your real experience."
            ),
        )
