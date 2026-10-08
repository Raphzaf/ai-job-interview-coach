# Demo Day script (2 min 45 s)

Target: about 2:45 spoken, ~380 words + a 60-second live demo. Timings are cumulative.
Slide numbers refer to [`presentation-outline.md`](presentation-outline.md).

**Before going on stage**
- `.env` configured with the LLM (badge top-right shows the model), server running: `uvicorn app.main:app`.
- Browser open on http://localhost:8000; run one analysis beforehand (warms up the embedding model), then reload the page.
- Keep the demo answer (step 8 below) in your clipboard.
- Plan B: if the Wi-Fi or the LLM fails, the app keeps working in labelled offline mode; just say "this is the offline fallback".

---

## 1. Introduction (0:00 – 0:10) · slide 1

> "Hi, I'm [name]. My project is the **AI Job Interview & Application Coach**: a RAG application that prepares you for one specific job."

## 2. Project overview (0:10 – 0:20) · slide 1

> "You give it your CV and a job description. It tells you how well you match and why, then interviews you with personalised questions and coaches your answers."

## 3. Problem (0:20 – 0:35) · slide 2

> "Candidates prepare with generic question lists. They don't know which requirements their CV fails to show, and that is exactly what interviewers dig into. And if you paste everything into a chatbot, it confidently invents experience you never had, or gives you an '87% match' nobody can explain."

## 4. Solution (0:35 – 0:45) · slide 3

> "My solution keeps the **scores deterministic and explainable**, and uses the LLM only for language, always **grounded in passages retrieved from your own documents**."

## 5. Users and benefits (0:45 – 0:55) · slide 3

> "It's for job seekers, career changers and bootcamp graduates: you see your gaps before the interviewer does and you practise on the questions that matter for *this* job."

## 6. Technical architecture (0:55 – 1:30) · slides 4–5

> "Here is the pipeline. Documents are extracted (PDF, Word, text) and cleaned without destroying tokens like C++ or '5+ years'. They are split into **section-aware chunks** of at most 200 tokens, measured with the embedding model's own **tokenizer**, because MiniLM truncates after 256 tokens.
> Each chunk becomes a 384-dimension **embedding**, stored in a **FAISS** index together with its metadata, so every result can be traced back to 'CV, Work Experience'.
> For each task, the query is embedded, FAISS returns the top chunks from the CV and the job, and only those go into the prompt, with grounding rules: don't invent, cite sources, say when information is missing. The LLM must answer in JSON, validated with Pydantic.
> The match score is a **weighted formula**: 40% skills, 35% requirement coverage found by semantic search, 15% document similarity, 10% experience."

## 7. Demonstration (1:30 – 2:30) · live

1. "I load a fictional CV and job ad" → **Load sample documents** → **Analyze match**.
2. "88 out of 100, and I can see why: each bar is a signal with its weight."
3. "Matching skills in green; the real gap is **AWS**, plus Kubernetes and Terraform as nice-to-haves."
4. "The insights cite their sources, S1 and S2: chunks retrieved by FAISS."
5. **Start interview practice**: "The question mentions Alex's actual project, not a generic one."
6. Choose **Skill gap** → **New question**: "Now it targets the AWS gap, and it admits the CV doesn't show it."
7. Paste the answer → **Submit**: "I get a rubric score, missing points, and a stronger answer that uses brackets instead of inventing facts."

## 8. Challenges (2:30 – 2:40) · slide 7

> "The hardest parts: cosine similarity is not a percentage, so I calibrated the score on a 3-by-3 CV/job test set; and 'PyTorch **or** TensorFlow' was flagged as a missing skill, so I had to handle alternatives."

## 9. Solutions & results (2:40 – 2:50) · slide 8

> "102 automated tests; in the evaluation every CV scores highest on its matching job, 92% of retrieval queries find the right chunk in the top 3, and all LLM outputs were valid JSON."

## 10. Future steps (2:50 – 2:58) · slide 9

> "Next: hybrid search with re-ranking, multilingual support, and a voice interview mode."

## 11. Conclusion (2:58 – 3:05) · slide 10

> "In short, a real RAG pipeline (embeddings, FAISS, grounded generation) with measurable matching and honest feedback. Thank you!"

---

### Demo answer (step 7)

> At Brightleaf I deployed our FastAPI models with Docker on Google Cloud Run. AWS is new for me, but the concepts map directly: I would use ECS with Fargate for the container and CloudWatch for monitoring. In my first month I would deploy our RAG API there and complete the AWS ML Specialty learning path.

### Likely questions from the jury

| Question | Short answer |
|---|---|
| Where exactly is the RAG? | `app/rag/pipeline.py`: query embedding → FAISS top-k (CV + job) → numbered context → grounded prompt → LLM → Pydantic. The LLM never sees the full documents. |
| Why FAISS and not a vector database? | Tens of vectors per session, in memory: an exact `IndexFlatIP` is microseconds; a DB server would add infrastructure for nothing. |
| Why not let the LLM give the score? | It is not reproducible or explainable. The score is a documented formula; the LLM explains it. |
| How do you limit hallucinations? | Retrieval-only context, explicit rules, citations shown in the UI, computed facts the LLM may not change, JSON validation, placeholders instead of invented facts. It reduces, it doesn't eliminate. |
| What if the LLM is down? | One repair attempt for invalid JSON, then a labelled offline fallback using the same retrieved context. |
| Why MiniLM? | Local, free, fast on CPU, reproducible, 384 dimensions; swappable via one setting. |
