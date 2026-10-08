# Presentation outline (slide by slide)

10 slides for a 2–3 minute talk with a ~60 s live demo. Keep text on slides minimal; the spoken text is in [`demo-script.md`](demo-script.md).

---

### Slide 1 · Title
- **AI Job Interview & Application Coach**
- Subtitle: *RAG-powered CV matching, personalised interview questions and grounded feedback*
- Name, bootcamp, date
- Visual: screenshot of the analysis screen (score ring + skill chips)

### Slide 2 · The problem
- Generic interview prep ignores the specific job
- Candidates don't see which requirements their CV fails to show
- Chatbots invent experience and give unexplainable "match %"
- Visual: a generic "Top 50 interview questions" list crossed out

### Slide 3 · The solution & who benefits
- Upload CV + job → transparent match score → personalised interview → coached answers
- Users: job seekers, career changers, bootcamp graduates
- Benefits: know your gaps first, practise the questions that matter, trustworthy feedback with sources

### Slide 4 · RAG architecture
Diagram (from the README):
`Documents → cleaning → chunking (tokenizer) → embeddings (MiniLM, 384-d) → FAISS → top-k retrieval → grounded prompt → LLM → JSON + Pydantic → UI`
- Callouts: "chunks ≤ 200 tokens (model limit 256)", "metadata kept with every vector", "LLM never sees the whole documents"

### Slide 5 · Embeddings & FAISS
- Embedding = meaning as a vector: "built REST services in Flask" ≈ "backend API development in Python"
- Normalised vectors → inner product = cosine similarity
- FAISS `IndexFlatIP`: exact search, microseconds for a CV + job
- Retrieval per task: requirement → CV evidence; question focus → CV + job; answer → context for feedback

### Slide 6 · Measurable matching
- Formula, not an LLM guess:
  - 40% skill overlap (taxonomy, aliases, alternatives)
  - 35% requirement coverage (semantic search evidence)
  - 15% document similarity (calibrated)
  - 10% years of experience
- Missing signals → weights re-normalised
- "An estimate of document fit, not a hiring probability"

### Slide 7 · Live demo
- (Switch to the browser: load samples → analyze → gap question → answer → feedback)

### Slide 8 · Challenges → solutions
| Challenge | Solution |
|---|---|
| Cosine ≠ percentage | Calibrated on a 3×3 CV/job matrix |
| "PyTorch **or** TensorFlow" = false gap | Alternative groups + skill implications |
| Semantic search missed the literal "FAISS" bullet | Light hybrid re-ranking for evidence |
| LLM invalid JSON / outage | Pydantic validation, one repair, labelled offline fallback |
| Generic questions | Planner (category + focus) + retrieved context + 60-word limit |

### Slide 9 · Results & future steps
- 102 automated tests (no API needed)
- Evaluation: matching pair best in 3/3 rows and columns · retrieval hit@3 92% · 13/13 valid LLM JSON · answer scores strong 8.1 > average 2.2 > off-topic 0.2
- Next: hybrid search + re-ranker, multilingual, adaptive difficulty, voice interviews

### Slide 10 · Conclusion
- A real RAG pipeline: embeddings, FAISS, grounded generation, structured outputs
- Explainable scores, visible sources, honest limits
- "Thank you! Questions?"
