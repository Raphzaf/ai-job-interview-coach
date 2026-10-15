# Demo Day script and video plan

**Durations to confirm with the bootcamp's official instructions.** The sources disagree:

| Source | Says |
|---|---|
| Official Google Slides template (slide 5) | "**2-mn video** link" |
| Project brief | Reliable **2–3 minute** live demo, expandable to **15–20 minutes** |
| Later brief | Demo video of **3–4 minutes** |

This script is therefore written as a **2-minute core**. Optional blocks extend it to about 3:30 if a longer video is allowed. Timings are targets; check them with a stopwatch during rehearsal.

All numbers below come from the project's saved results:
- dashboard values: `dashboard/tableau/EXPECTED_VALUES.md`;
- coach values: the sample documents.

---

## Before recording or going on stage (checklist)

- [ ] `.env` contains a working LLM configuration. Check that the badge top-right shows `gemini-flash-latest` (or your model), not "offline".
- [ ] `uvicorn app.main:app` is running. Run **one analysis beforehand** (it warms up the embedding model), then reload the page.
- [ ] The Tableau Public dashboard is open in a second tab: Dashboard 1, no filters.
- [ ] The demo answer (step 6) is in the clipboard.
- [ ] Browser zoom at 110–125 % so text is readable on a projector or video; notifications off.
- [ ] **Plan B:**
  - if the LLM or the Wi-Fi fails, the app keeps working in labelled offline mode; say "this is the offline fallback, same retrieval, simpler generation";
  - if Tableau Public is unreachable, show the dashboard screenshots from `demo_day/screenshots/`.

---

## 2-minute core (video or live)

| Time | Screen | What to say (≈ 260 words) |
|---|---|---|
| 0:00–0:15 | Title slide or the app's home page | "Job seekers prepare for interviews blindly: they don't know what the market wants, or how their CV compares to a specific job. I built the **AI Job Market & Interview Coach**, which goes from job-market data to personalised interview practice." |
| 0:15–0:40 | Tableau Dashboard 1 → set **Role = Data Engineer**, then **Country = Germany** | "First, the market. I collected about 788,000 job postings from a public API and a public dataset, cleaned them with pandas, and loaded them into PostgreSQL. For Data Engineers, SQL appears in 67.5 % of postings, Python in 65 %, and AWS in 39 %. In Germany, Azure overtakes AWS." |
| 0:40–0:55 | Coach → **Load sample documents** → **Analyze match** | "Now a real candidate. The coach reads the CV and the job, splits them into chunks, embeds them, and indexes them with FAISS for semantic search." |
| 0:55–1:20 | Score ring, skills, **Job market context** panel | "The match is 85 out of 100, and every part of the score is explained. The candidate is missing AWS, and the coach connects this to the market: AWS appears in 31 % of Machine Learning Engineer postings. So this gap is worth preparing." |
| 1:20–1:45 | **Start interview practice** → choose **Skill gap** → **New question** → paste the answer → **Submit** | "The interview: the coach retrieves the relevant parts of the CV and the job, and the LLM asks a question about the gap, without pretending the CV mentions AWS. I answer…" |
| 1:45–2:00 | Feedback: score, rubric, stronger answer | "…and get a rubric score, what was missing, and a stronger answer with placeholders instead of invented facts. Data tells you what the market wants; the AI coach helps you prepare for it." |

**Demo answer (clipboard):**
> At Brightleaf I deployed our FastAPI models with Docker on Google Cloud Run. AWS is new for me, but the concepts map directly: I would use ECS with Fargate for the container and CloudWatch for monitoring. In my first month I would deploy our RAG API there and complete the AWS ML Specialty learning path.

---

## Optional extensions (for a 3–4 minute video)

Insert them after 0:40 (data) or after 2:00 (behind the scenes).

| Duration | Screen | Content |
|---|---|---|
| +25 s | Figure `reports/figures/stats/C_senior_skill_odds_ratios.png` | "Is AWS a senior skill? Statistically, yes: a Cochran-Mantel-Haenszel test within each role gives an odds ratio of 1.47 for senior postings. The effect is real but moderate, and I report effect sizes, not just p-values." |
| +25 s | Figure `reports/figures/ml/ML_confusion_matrix.png` | "Can skills predict a role? A gradient-boosting classifier reaches a macro-F1 of 0.39 against 0.14 for a random baseline. Skills carry real information, but Data Analyst, Engineer and Scientist overlap heavily, which is itself an insight." |
| +20 s | Coach → **Under the hood** and **Sources** panels | "Everything the AI says is grounded: sources are numbered, outputs are validated JSON, and if the LLM fails the app falls back to a labelled offline mode. The project has 195 automated tests." |

---

## Recording tips (video)

- Record at 1920×1080 with a screen recorder (OBS, Loom or the macOS screenshot tool). Voice-over can be recorded live or added afterwards.
- LLM calls take about 10–15 s. Cut the waiting time in editing, or click while you talk.
- Upload as **unlisted** on YouTube (or Loom), then paste the link in slide 5 of the template and in the portfolio entry.

## Rehearsal sequence

1. Run the checklist above.
2. Click through the 2-minute core twice **without** speaking, to learn the clicks.
3. Run it twice **with** the script and a stopwatch. Adjust the wording, not the speed.
4. Run it once with the Wi-Fi off, to practise Plan B (offline mode + screenshots).
5. Record the video. Keep the best take; don't edit beyond trimming the waits.
