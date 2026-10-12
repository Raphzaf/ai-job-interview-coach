# Evaluation results

- Date: 2026-10-12 17:10
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Generator: `gemini-flash-latest (OpenAI-compatible API)`

## 1. Retrieval relevance

12 labelled queries over the sample CV and job description (search restricted to the expected document).

| hit@1 | hit@3 | MRR |
|---|---|---|
| 67% | 92% | 0.81 |

| Query | Doc | Expected text | Rank |
|---|---|---|---|
| Experience building a retrieval-augmented generation assistant | cv | RAG | 1 |
| Fine-tuning transformer classifiers | cv | BERT | 1 |
| Deploying APIs with containers on the cloud | cv | Docker | 1 |
| Demand forecasting for retail stores | cv | forecasting | 1 |
| University degree in data science | cv | M.Sc. | 1 |
| Professional certifications | cv | Google Cloud Professional | 1 |
| Which languages does the candidate speak? | cv | French (native) | 1 |
| Mentoring junior colleagues | cv | Mentored | 2 |
| Required years of experience | job | 3+ years | 1 |
| Cloud platform used for deployment | job | AWS | 2 |
| Optional skills that are a plus | job | Kubernetes | 2 |
| Main responsibilities of the role | job | Design and implement retrieval-augmented | 5 |

## 2. Matching consistency

Overall match score for every CV (rows) against every job (columns):

| CV \ Job | job_ml_engineer | job_backend_developer | job_marketing_manager |
|---|---|---|---|
| cv_ml_engineer | 85.4 | 60.9 | 36.2 |
| cv_backend_developer | 50.2 | 98.8 | 17.5 |
| cv_marketing_coordinator | 16.8 | 9.2 | 98.7 |

- Matching pair is the best job for every CV: **True**
- Matching pair is the best CV for every job: **True**
- Mean score of matching pairs: **94.3**, mismatched pairs: **31.8**
- Identical score on a repeated run (determinism): **True**

## 3. Output structure validity

13 structured LLM calls (MatchInsights: 1, InterviewQuestion: 6, AnswerEvaluation: 6).

| Valid on first try | Valid after repair | Invalid (offline fallback used) |
|---|---|---|
| 13 | 0 | 0 |

## 4. Interview question relevance

- Category respected: **100%**
- Mentions a job skill/requirement: **83%**
- Mentions CV content (or is a gap question): **83%**
- All questions unique: **True**

| Requested | Category | Job ref | CV ref | Source | Question |
|---|---|---|---|---|---|
| technical | technical | yes | yes | llm | In your open-source CV parser library built with Python and spaCy, how did you handle Python's memory management and CPU bottlenecks when processing large batches of resumes, and what architectural trade-offs did you make to keep the library fast and lightweight? |
| experience | experience | yes | yes | llm | At Brightleaf Analytics, you developed a RAG assistant with FAISS and fine-tuned BERT classifiers routing 40,000 monthly tickets. Drawing on your professional ML experience, could you walk me through the end-to-end lifecycle of one of those systems, from dataset preparation and validation to production deployment? |
| gap | gap | yes | yes | llm | At Brightleaf, you deployed containerised FastAPI models on Google Cloud Run, but our stack relies on AWS services like SageMaker or ECS. How would you translate your container deployment experience to AWS, and what factors would you consider when choosing between ECS and SageMaker for serving models? |
| behavioral | behavioral | no | no | llm | In this role, you'll collaborate with product managers and designers to turn user needs into ML features. Can you share a specific time—for example, working with non-technical partners like marketing or category managers—where you had to bridge differing expectations to deliver an ML or data project? |
| auto | technical | yes | yes | llm | When implementing the RAG retrieval pipeline with FAISS at Brightleaf, which indexing method and similarity metric did you choose, and what trade-offs did you encounter between search latency, memory footprint, and recall? |
| auto | experience | yes | yes | llm | You highlight six years of experience building NLP products with Python and PyTorch. Can you walk me through a specific project where you used PyTorch to build or fine-tune a model, explaining how you structured the training pipeline and handled any technical challenges during implementation? |

## 5. Answer evaluation consistency

Fixed question: _In your RAG assistant at Brightleaf, how did you design the FAISS-based retrieval and how did you know it worked well?_

| Answer quality | Scores (repeats) | Mean |
|---|---|---|
| strong | 8.2, 7.8 | 8.0 |
| average | 2.5, 2.8 | 2.6 |
| off_topic | 0.2, 0.0 | 0.1 |

- Expected ordering strong > average > off-topic: **True**
- Largest score spread between repeated evaluations of the same answer: **0.4** points (out of 10)
