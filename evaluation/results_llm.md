# Evaluation results

- Date: 2026-10-08 09:10
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
| cv_ml_engineer | 87.5 | 61.7 | 41.7 |
| cv_backend_developer | 52.0 | 98.8 | 23.5 |
| cv_marketing_coordinator | 25.5 | 16.5 | 99.0 |

- Matching pair is the best job for every CV: **True**
- Matching pair is the best CV for every job: **True**
- Mean score of matching pairs: **95.1**, mismatched pairs: **36.8**
- Identical score on a repeated run (determinism): **True**

## 3. Output structure validity

13 structured LLM calls (MatchInsights: 1, InterviewQuestion: 6, AnswerEvaluation: 6).

| Valid on first try | Valid after repair | Invalid (offline fallback used) |
|---|---|---|
| 13 | 0 | 0 |

## 4. Interview question relevance

- Category respected: **100%**
- Mentions a job skill/requirement: **83%**
- Mentions CV content (or is a gap question): **100%**
- All questions unique: **True**

| Requested | Category | Job ref | CV ref | Source | Question |
|---|---|---|---|---|---|
| technical | technical | yes | yes | llm | In your open-source Python CV parser using spaCy, how did you manage memory overhead and throughput when processing large batches of documents, and what trade-offs did you consider between Python's multiprocessing and streaming generators? |
| experience | experience | yes | yes | llm | At Brightleaf Analytics, you fine-tuned BERT classifiers using PyTorch and Transformers to route 40,000 monthly tickets. Drawing on your machine learning experience, could you walk me through your end-to-end process for training, evaluating offline performance, and monitoring that system for drift in production? |
| gap | gap | yes | yes | llm | At Brightleaf Analytics, you deployed containerised FastAPI services on Google Cloud Run. Since this role requires deploying ML services on AWS using tools like ECS, Lambda, or SageMaker, how would you translate your GCP container deployment experience to AWS, and which AWS service would you choose to host a RAG API? |
| behavioral | behavioral | no | yes | llm | At Orbis Retail, you partnered with marketing and finance teams on pricing experiments and presented to category managers. Could you describe a time when non-technical stakeholders disagreed with your model's findings or requirements, and how you navigated that pushback to reach an aligned decision? |
| auto | technical | yes | yes | llm | At Brightleaf Analytics, you built a RAG assistant using sentence embeddings and FAISS. When designing that retrieval pipeline, what specific FAISS index type did you choose, and how did you navigate the trade-offs between search latency, memory footprint, and retrieval recall? |
| auto | experience | yes | yes | llm | In your experience as a Machine Learning Engineer building NLP products in Python, could you describe a specific project where you implemented a model using PyTorch, explaining how you structured your PyTorch data loaders, training logic, or custom layers? |

## 5. Answer evaluation consistency

Fixed question: _In your RAG assistant at Brightleaf, how did you design the FAISS-based retrieval and how did you know it worked well?_

| Answer quality | Scores (repeats) | Mean |
|---|---|---|
| strong | 8.2, 8.0 | 8.1 |
| average | 2.2, 2.2 | 2.2 |
| off_topic | 0.2, 0.2 | 0.2 |

- Expected ordering strong > average > off-topic: **True**
- Largest score spread between repeated evaluations of the same answer: **0.2** points (out of 10)
