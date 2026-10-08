"""Lightweight evaluation of the coach.

Run from the project root:

    python -m evaluation.run_evaluation            # uses the LLM configured in .env (or offline)
    python -m evaluation.run_evaluation --offline  # force the offline generator (no API calls)

It evaluates five things and writes evaluation/results_<llm|offline>.md (+ .json):

1. Retrieval relevance   - labelled queries over the sample CV/job: hit@1, hit@3, MRR.
2. Matching consistency  - 3 CVs x 3 jobs: the matching pair must score highest
                           in every row and column; repeated runs must be identical.
3. Output structure      - share of LLM outputs valid on the first try / after the
                           repair round-trip / that needed the offline fallback.
4. Question relevance    - generated questions must reference both the job and the
                           candidate's CV and respect the requested category.
5. Answer evaluation     - graded answers (strong > average > off-topic) must be
                           ranked in that order; repeated scoring must be stable.

This is a sanity benchmark on a handful of fictional documents, not a
research-grade evaluation (see README > Evaluation > Limitations).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.api.dependencies import build_container
from app.core.config import Settings
from app.core.sessions import AskedQuestion
from app.matching.skills import extract_skills
from app.models.schemas import AnalyzeRequest, InterviewQuestion
from app.rag import llm as llm_module

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evaluation" / "data"
CVS = ["cv_ml_engineer", "cv_backend_developer", "cv_marketing_coordinator"]
JOBS = ["job_ml_engineer", "job_backend_developer", "job_marketing_manager"]

# (query, document to search, substring expected in the relevant chunk)
RETRIEVAL_CASES = [
    ("Experience building a retrieval-augmented generation assistant", "cv", "RAG"),
    ("Fine-tuning transformer classifiers", "cv", "BERT"),
    ("Deploying APIs with containers on the cloud", "cv", "Docker"),
    ("Demand forecasting for retail stores", "cv", "forecasting"),
    ("University degree in data science", "cv", "M.Sc."),
    ("Professional certifications", "cv", "Google Cloud Professional"),
    ("Which languages does the candidate speak?", "cv", "French (native)"),
    ("Mentoring junior colleagues", "cv", "Mentored"),
    ("Required years of experience", "job", "3+ years"),
    ("Cloud platform used for deployment", "job", "AWS"),
    ("Optional skills that are a plus", "job", "Kubernetes"),
    ("Main responsibilities of the role", "job", "Design and implement retrieval-augmented"),
]

GRADED_ANSWERS = {
    "strong": (
        "At Brightleaf Analytics I built the retrieval-augmented support assistant. The goal was to cut ticket "
        "handling time. I embedded about 20,000 help-centre articles with a sentence-transformer, indexed them in "
        "FAISS with an exact inner-product index because the corpus was small, and served retrieval plus the LLM "
        "call behind a FastAPI service in Docker on Cloud Run. I built an offline evaluation set to tune chunk size "
        "and top-k. As a result, average handling time dropped by 18%. At larger scale I would move to an HNSW index."
    ),
    "average": (
        "I used FAISS in a project at work for search. It was quite fast and worked well. We used embeddings "
        "and an LLM and it helped the support team."
    ),
    "off_topic": "I enjoy hiking and cooking at the weekend, and I am a very motivated and curious person.",
}
FIXED_QUESTION = InterviewQuestion(
    question="In your RAG assistant at Brightleaf, how did you design the FAISS-based retrieval and how did you know it worked well?",
    category="technical",
    difficulty="medium",
    focus="Vector Databases",
    rationale="The job requires vector search; the CV mentions FAISS in a RAG assistant.",
    expected_points=["Embedding and index choices", "Evaluation of retrieval quality", "Measurable impact"],
)


@dataclass
class LLMCallStats:
    """Counts how structured outputs were obtained (wraps generate_structured)."""

    first_try: int = 0
    repaired: int = 0
    failed: int = 0
    calls_by_schema: dict = field(default_factory=dict)

    def install(self) -> None:
        original = llm_module.generate_structured
        stats = self

        def counting(provider, system, user, schema, max_repairs=1):
            class Counting:
                name = provider.name
                n = 0

                def complete(self, messages, json_mode=True):
                    Counting.n += 1
                    return provider.complete(messages, json_mode)

            wrapper = Counting()
            try:
                result = original(wrapper, system, user, schema, max_repairs)
            except Exception:
                stats.failed += 1
                raise
            if wrapper.n == 1:
                stats.first_try += 1
            else:
                stats.repaired += 1
            stats.calls_by_schema[schema.__name__] = stats.calls_by_schema.get(schema.__name__, 0) + 1
            return result

        # The pipeline imported the function by name, so patch it there too.
        import app.rag.pipeline as pipeline_module

        llm_module.generate_structured = counting
        pipeline_module.generate_structured = counting


def read(name: str) -> str:
    return (DATA / f"{name}.txt").read_text(encoding="utf-8")


def eval_retrieval(pipeline, analysis_session) -> dict:
    retriever = analysis_session.retriever
    hits1 = hits3 = 0
    reciprocal_ranks, rows = [], []
    for query, doc_type, expected in RETRIEVAL_CASES:
        results = retriever.retrieve(query, k=len(retriever.store), doc_type=doc_type)
        rank = next((i + 1 for i, r in enumerate(results) if expected.lower() in r.chunk.text.lower()), None)
        hits1 += rank == 1
        hits3 += rank is not None and rank <= 3
        reciprocal_ranks.append(1 / rank if rank else 0.0)
        rows.append({"query": query, "doc": doc_type, "expected": expected, "rank": rank})
    n = len(RETRIEVAL_CASES)
    return {"hit@1": hits1 / n, "hit@3": hits3 / n, "mrr": sum(reciprocal_ranks) / n, "cases": rows}


def eval_matching(pipeline) -> dict:
    matrix: dict[str, dict[str, float]] = {}
    for cv in CVS:
        matrix[cv] = {}
        for job in JOBS:
            # Matching is deterministic; disable the LLM for this part to save API calls.
            report = pipeline.matcher.analyze(
                pipeline.processor.prepare(read(cv), "cv", cv),
                pipeline.processor.prepare(read(job), "job", job),
                _retriever(pipeline, cv, job),
            )
            matrix[cv][job] = report.overall_score
    diagonal_best_rows = all(max(matrix[cv], key=matrix[cv].get) == JOBS[i] for i, cv in enumerate(CVS))
    diagonal_best_cols = all(max(CVS, key=lambda c: matrix[c][job]) == CVS[i] for i, job in enumerate(JOBS))
    diag = [matrix[CVS[i]][JOBS[i]] for i in range(3)]
    off = [matrix[c][j] for c in CVS for j in JOBS if CVS.index(c) != JOBS.index(j)]
    repeat = pipeline.matcher.analyze(
        pipeline.processor.prepare(read(CVS[0]), "cv", CVS[0]),
        pipeline.processor.prepare(read(JOBS[0]), "job", JOBS[0]),
        _retriever(pipeline, CVS[0], JOBS[0]),
    ).overall_score
    return {
        "matrix": matrix,
        "matching_pair_best_in_every_row": diagonal_best_rows,
        "matching_pair_best_in_every_column": diagonal_best_cols,
        "mean_matching": statistics.mean(diag),
        "mean_mismatched": statistics.mean(off),
        "deterministic": repeat == matrix[CVS[0]][JOBS[0]],
    }


def _retriever(pipeline, cv: str, job: str):
    from app.retrieval.retriever import Retriever

    cv_doc = pipeline.processor.prepare(read(cv), "cv", cv)
    job_doc = pipeline.processor.prepare(read(job), "job", job)
    return Retriever.from_chunks(pipeline.embedder, pipeline.processor.chunk(cv_doc) + pipeline.processor.chunk(job_doc))


def _job_terms(session) -> set[str]:
    terms = {s.name.lower() for s in session.match.matching_skills + session.match.missing_skills}
    terms |= {w.lower() for r in session.match.requirements for w in r.text.split() if len(w) > 6}
    return terms


def _cv_terms(session) -> set[str]:
    words = {w.strip(".,()").lower() for w in session.cv.text.split() if len(w) > 5 and w[0].isupper()}
    return words | {s.lower() for s in extract_skills(session.cv.text)}


def eval_questions(pipeline, session_id: str) -> dict:
    session = pipeline.sessions.get(session_id)
    job_terms, cv_terms = _job_terms(session), _cv_terms(session)
    rows = []
    for category in ["technical", "experience", "gap", "behavioral", None, None]:
        q = pipeline.next_question(session_id, category)
        text = (q.question.question + " " + q.question.focus).lower()
        rows.append({
            "requested": category or "auto",
            "category": q.question.category,
            "category_ok": category is None or q.question.category == category,
            "mentions_job": any(t in text for t in job_terms),
            "mentions_cv": any(t in text for t in cv_terms),
            "generated_by": q.generated_by,
            "question": q.question.question,
        })
    unique = len({r["question"] for r in rows}) == len(rows)
    n = len(rows)
    return {
        "category_ok": sum(r["category_ok"] for r in rows) / n,
        "mentions_job": sum(r["mentions_job"] for r in rows) / n,
        "mentions_cv_or_gap": sum(r["mentions_cv"] or r["category"] == "gap" for r in rows) / n,
        "all_unique": unique,
        "questions": rows,
    }


def eval_answers(pipeline, session_id: str, repeats: int) -> dict:
    session = pipeline.sessions.get(session_id)
    context = session.retriever.retrieve_balanced(FIXED_QUESTION.question, k_per_doc=3)
    session.questions["eval"] = AskedQuestion(question_id="eval", question=FIXED_QUESTION, context=context)
    scores: dict[str, list[float]] = {}
    for label, answer in GRADED_ANSWERS.items():
        scores[label] = [pipeline.evaluate(session_id, "eval", answer).score for _ in range(repeats)]
    means = {k: statistics.mean(v) for k, v in scores.items()}
    spread = max((max(v) - min(v)) for v in scores.values())
    return {
        "scores": scores,
        "means": means,
        "ordering_ok": means["strong"] > means["average"] > means["off_topic"],
        "max_spread_between_repeats": spread,
    }


def render_markdown(results: dict) -> str:
    r, m, s, q, a = (results[k] for k in ("retrieval", "matching", "structure", "questions", "answers"))
    lines = [
        "# Evaluation results",
        "",
        f"- Date: {results['date']}",
        f"- Embedding model: `{results['embedding_model']}`",
        f"- Generator: `{results['generator']}`",
        "",
        "## 1. Retrieval relevance",
        "",
        f"{len(r['cases'])} labelled queries over the sample CV and job description (search restricted to the expected document).",
        "",
        f"| hit@1 | hit@3 | MRR |\n|---|---|---|\n| {r['hit@1']:.0%} | {r['hit@3']:.0%} | {r['mrr']:.2f} |",
        "",
        "| Query | Doc | Expected text | Rank |",
        "|---|---|---|---|",
        *[f"| {c['query']} | {c['doc']} | {c['expected']} | {c['rank'] or 'not found'} |" for c in r["cases"]],
        "",
        "## 2. Matching consistency",
        "",
        "Overall match score for every CV (rows) against every job (columns):",
        "",
        "| CV \\ Job | " + " | ".join(JOBS) + " |",
        "|---|" + "---|" * len(JOBS),
        *[f"| {cv} | " + " | ".join(f"{m['matrix'][cv][j]:.1f}" for j in JOBS) + " |" for cv in CVS],
        "",
        f"- Matching pair is the best job for every CV: **{m['matching_pair_best_in_every_row']}**",
        f"- Matching pair is the best CV for every job: **{m['matching_pair_best_in_every_column']}**",
        f"- Mean score of matching pairs: **{m['mean_matching']:.1f}**, mismatched pairs: **{m['mean_mismatched']:.1f}**",
        f"- Identical score on a repeated run (determinism): **{m['deterministic']}**",
        "",
        "## 3. Output structure validity",
        "",
    ]
    if s["total"]:
        lines += [
            f"{s['total']} structured LLM calls ({', '.join(f'{k}: {v}' for k, v in s['by_schema'].items())}).",
            "",
            "| Valid on first try | Valid after repair | Invalid (offline fallback used) |",
            "|---|---|---|",
            f"| {s['first_try']} | {s['repaired']} | {s['failed']} |",
        ]
    else:
        lines += ["No LLM configured: all outputs came from the offline generator and were validated by the same Pydantic schemas."]
    lines += [
        "",
        "## 4. Interview question relevance",
        "",
        f"- Category respected: **{q['category_ok']:.0%}**",
        f"- Mentions a job skill/requirement: **{q['mentions_job']:.0%}**",
        f"- Mentions CV content (or is a gap question): **{q['mentions_cv_or_gap']:.0%}**",
        f"- All questions unique: **{q['all_unique']}**",
        "",
        "| Requested | Category | Job ref | CV ref | Source | Question |",
        "|---|---|---|---|---|---|",
        *[f"| {x['requested']} | {x['category']} | {'yes' if x['mentions_job'] else 'no'} | {'yes' if x['mentions_cv'] else 'no'} | {x['generated_by']} | {x['question'].replace('|', '/')} |" for x in q["questions"]],
        "",
        "## 5. Answer evaluation consistency",
        "",
        f"Fixed question: _{FIXED_QUESTION.question}_",
        "",
        "| Answer quality | Scores (repeats) | Mean |",
        "|---|---|---|",
        *[f"| {k} | {', '.join(f'{x:.1f}' for x in v)} | {a['means'][k]:.1f} |" for k, v in a["scores"].items()],
        "",
        f"- Expected ordering strong > average > off-topic: **{a['ordering_ok']}**",
        f"- Largest score spread between repeated evaluations of the same answer: **{a['max_spread_between_repeats']:.1f}** points (out of 10)",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="Do not call the LLM; use the offline generator.")
    parser.add_argument("--repeats", type=int, default=2, help="Repeated evaluations per graded answer.")
    args = parser.parse_args()

    settings = Settings(llm_fallback_to_offline=True, log_level="WARNING")
    if args.offline:
        settings = settings.model_copy(update={"llm_provider": "offline"})
    stats = LLMCallStats()
    stats.install()
    container = build_container(settings)
    pipeline = container.pipeline
    print(f"Embeddings: {pipeline.embedder.model_name} | Generator: {pipeline.llm_label}")

    started = time.time()
    analysis = pipeline.analyze(AnalyzeRequest(cv_text=read(CVS[0]), job_text=read(JOBS[0])))
    session = pipeline.sessions.get(analysis.session_id)
    results = {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "embedding_model": pipeline.embedder.model_name,
        "generator": pipeline.llm_label,
        "retrieval": eval_retrieval(pipeline, session),
        "matching": eval_matching(pipeline),
        "questions": eval_questions(pipeline, analysis.session_id),
        "answers": eval_answers(pipeline, analysis.session_id, args.repeats if pipeline.llm else 1),
    }
    results["structure"] = {
        "total": stats.first_try + stats.repaired + stats.failed,
        "first_try": stats.first_try, "repaired": stats.repaired, "failed": stats.failed,
        "by_schema": stats.calls_by_schema,
    }
    name = "results_llm" if pipeline.llm else "results_offline"
    out_dir = ROOT / "evaluation"
    (out_dir / f"{name}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out_dir / f"{name}.md").write_text(render_markdown(results), encoding="utf-8")
    print(render_markdown(results))
    print(f"Done in {time.time() - started:.0f}s -> evaluation/{name}.md")


if __name__ == "__main__":
    main()
