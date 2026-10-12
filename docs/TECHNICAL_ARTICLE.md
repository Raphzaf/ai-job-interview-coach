# What 788,000 job postings taught me about building an honest AI interview coach

*Draft technical article for the bootcamp's "technical article link" (Medium, LinkedIn or dev.to). About 1,100 words. Every number comes from the project's saved results: [GitHub repository](https://github.com/Raphzaf/ai-job-interview-coach).*

---

When you ask a chatbot "how well does my CV match this job?", you get a confident percentage and a polished paragraph. Ask twice and the percentage changes. Ask where it comes from and there is no answer. Sometimes the paragraph praises experience you never had.

For my bootcamp final project I wanted the opposite: an interview coach where **every number can be traced** and the AI only does what it is good at, which is language. I also wanted it to answer a question no single CV can: *what does the market actually ask for?*

The result has two layers:
1. a data-analytics pipeline over about 788,000 job postings;
2. a RAG application that compares a CV with a job and runs a mock interview.

Here is what I learned building it.

## 1. Measure the market before coaching anyone

I used two public sources.
- **The Arbeitnow job-board API:** 3,026 postings from October 2026, mostly in Germany.
- **The `lukebarousse/data_jobs` dataset on Hugging Face:** 784,897 data and tech postings from 2023, Apache-2.0.

I deliberately kept them separate. Their populations differ (all occupations in Germany vs data roles worldwide), so comparing them would have produced fake "trends".

After cleaning with pandas, everything went into **PostgreSQL**: 4.5 million rows, including one row per posting × skill. Two details mattered more than I expected.

- **Least privilege.** Analyses run as a read-only role that cannot even see job description text. If an analysis script has a bug, it cannot damage the data.
- **Denominators.** My first "top skills" query computed the share of skill *mentions* instead of the share of *postings*, which silently inflated rare skills. Since then, every extract carries its own denominator (`postings_with_skill`, `postings_in_group`), so a dashboard cannot average percentages wrongly. Example: SQL appears in **67.5 %** of Data Engineer postings, Python in **64.9 %**, AWS in **38.6 %**.

## 2. With 785,000 rows, everything is "significant"

My first statistical results were exciting: every test rejected the null hypothesis with p-values below 1e-300. That is not a discovery; it is sample size.

So the analysis reports **effect sizes first**: Cliff's δ, Cramér's V, odds ratios and confidence intervals.
- **Do senior postings list more skills?** Yes, but the effect is small to negligible (Cliff's δ between 0.05 and 0.15).
- **Within the same role, which skills are over-represented in senior postings?** A Cochran-Mantel-Haenszel test per skill, with false-discovery-rate correction, found 64 of 71 skills significant, with odds ratios from 0.71 to 1.84. AWS, for example, has an odds ratio of 1.47.
- **What is the advertised salary associated with?** An OLS model on log-salary (R² = 0.26) associates senior status with **+17.2 %**, all else equal.

These are associations from observational data, and I say so on every slide.

## 3. A modest model is still useful, if you evaluate it honestly

Can a posting's skills predict its role? I trained a scikit-learn classifier on 641,060 postings with a **company-grouped split**: no company appears in both training and test data, otherwise the model could memorise companies' templates.

| Model | Macro-F1 |
|---|---|
| Stratified random baseline | 0.142 |
| HistGradientBoosting | **0.393** (accuracy 0.639, top-3 accuracy 0.929) |

0.393 is not impressive, and the confusion matrix explains why: Data Analyst, Data Engineer and Data Scientist postings ask for very similar skills. That overlap *is* the insight. A second experiment (predicting seniority from skills) reached only ROC-AUC 0.625. I kept it in the report as a negative result rather than tuning until it looked better.

## 4. The coach: compute in code, let the LLM explain

The coach takes a CV and a job description, extracts and cleans the text, and splits it into chunks of at most 200 tokens. The chunks are measured with the embedding model's own tokenizer, because `all-MiniLM-L6-v2` silently truncates anything beyond 256 tokens. Each chunk is embedded and indexed with **FAISS**.

The key design decision: **the LLM never decides the match score.** The score is a documented weighted average of four signals computed in code:

| Signal | Weight |
|---|---|
| Skill overlap | 0.40 |
| Requirement coverage, via semantic search for CV evidence | 0.35 |
| Overall semantic similarity | 0.15 |
| Years of experience | 0.10 |

It is deterministic and testable: in my evaluation, matching CV/job pairs scored **94.3** on average and mismatched pairs **31.8**.

One surprise: raw cosine similarity is not a percentage. Unrelated professional texts still scored 0.2 to 0.4 with MiniLM, so I calibrated explicit rescaling anchors on an evaluation matrix and documented them.

The LLM then receives only:
- the **retrieved** chunks relevant to the task, numbered `[S1]`, `[S2]`…;
- the computed facts, as facts it must not change.

It writes the explanation, the interview questions and the feedback. Its output must be JSON that passes a Pydantic schema; if it does not, the app sends one repair request with the exact validation errors. In evaluation, 13 of 13 outputs were valid on the first try. If the LLM is down, a labelled offline mode takes over.

## 5. Where the two layers meet

The bridge between the layers is simple, and that is the point. The data pipeline extracts skills with **the coach's own skill taxonomy**, so "AWS" in 788,000 postings and "AWS" in a CV are the same concept.

When the coach finds a gap, it detects the job's role family from the title and adds market context. For the sample candidate applying to a Machine Learning Engineer job, the gap is AWS, and **AWS appears in 31.1 % of 12,164 Machine Learning Engineer postings**. That number reaches the LLM as a labelled fact, so the coaching can say "this gap is worth preparing" instead of guessing.

**Engineering choices:**
- The market data ships with the app as a 12 KB JSON file, regenerated from the same validated extract as the dashboard. A test checks they are identical, so the coach needs no database and still works offline.
- If the job is outside the data roles covered (a marketing job, say), the coach shows nothing rather than misleading statistics.
- The market context never changes the score.

## What I would tell my past self

1. **Decide where the AI is allowed to be creative.** Language: yes. Numbers: no.
2. **Report effect sizes, not p-values,** whenever your dataset is large.
3. **Split by group** (company, user, patient) whenever rows are not independent.
4. **Carry denominators with your aggregates.** Most dashboard errors are averaged percentages.
5. **Write the test before trusting the number.** The project has 195 automated tests, including one that checks that the figures shown in the coach equal the figures in the dashboard.

The code, the notebooks and the full documentation are on GitHub: <https://github.com/Raphzaf/ai-job-interview-coach>.
