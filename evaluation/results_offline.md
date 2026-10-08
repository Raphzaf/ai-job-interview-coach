# Evaluation results

- Date: 2026-10-08 09:10
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Generator: `offline mode (no LLM configured)`

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

No LLM configured: all outputs came from the offline generator and were validated by the same Pydantic schemas.

## 4. Interview question relevance

- Category respected: **100%**
- Mentions a job skill/requirement: **83%**
- Mentions CV content (or is a gap question): **83%**
- All questions unique: **True**

| Requested | Category | Job ref | CV ref | Source | Question |
|---|---|---|---|---|---|
| technical | technical | yes | yes | offline | Your CV mentions: “Open-source CV parser: Python library that extracts skills from resumes with spaCy (300 GitHub stars).”. Can you walk me through how you used Python there: the technical choices you made, the trade-offs, and what you would do differently today? |
| experience | experience | yes | yes | offline | The role asks for: “3+ years of professional experience in machine learning or data science”. Which experience from your background best demonstrates this? Describe the context, your personal role, and the outcome. |
| gap | gap | yes | yes | offline | The job mentions AWS, which does not clearly appear in your CV. What related experience do you have, and how would you get up to speed in your first months? |
| behavioral | behavioral | no | no | offline | Tell me about a time you were collaborating with cross-functional stakeholders (product, business, design). What was the situation, what did you do, and what was the result? |
| auto | technical | yes | yes | offline | Your CV mentions: “Machine Learning Engineer - Brightleaf Analytics, Lyon Mar 2023 - Present”. Can you walk me through how you used Machine Learning there: the technical choices you made, the trade-offs, and what you would do differently today? |
| auto | experience | yes | yes | offline | The role asks for: “Strong Python skills and experience with PyTorch or TensorFlow”. Which experience from your background best demonstrates this? Describe the context, your personal role, and the outcome. |

## 5. Answer evaluation consistency

Fixed question: _In your RAG assistant at Brightleaf, how did you design the FAISS-based retrieval and how did you know it worked well?_

| Answer quality | Scores (repeats) | Mean |
|---|---|---|
| strong | 9.5 | 9.5 |
| average | 8.0 | 8.0 |
| off_topic | 0.8 | 0.8 |

- Expected ordering strong > average > off-topic: **True**
- Largest score spread between repeated evaluations of the same answer: **0.0** points (out of 10)
