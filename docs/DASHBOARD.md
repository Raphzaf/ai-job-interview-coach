# Interactive Dashboard (Phase 7): Design Specification

**Platform:** Tableau Public (free, published with a public link).

**Status: published.** <https://public.tableau.com/app/profile/raphael.zafran/viz/AIJobMarketInterviewCoachMarketDashboards/D1-Overview>
- **Published scope:** Dashboard 1 (2023 overview) and Dashboard 3 (live 2026 snapshot). Dashboards 2 and 4 below remain optional designs and are not in the published workbook.
- **How it was built:** manually in Tableau Public Desktop, following the build guide; the numbers were checked against the expected values, unfiltered and filtered.

| Deliverable | File | Status |
|---|---|---|
| Data files (11 CSV, 9.3 MB) | `dashboard/tableau/data/` | ✅ generated from PostgreSQL by `python -m market.dashboard.export` |
| Validation (25 checks against the database, incl. identical values for shared filters) | `dashboard/tableau/data/validation.json` | ✅ all pass |
| Data dictionary | `dashboard/tableau/data/data_dictionary.json` | ✅ |
| Expected values to check the build | `dashboard/tableau/EXPECTED_VALUES.md` | ✅ |
| Step-by-step build guide | `dashboard/TABLEAU_BUILD_GUIDE.md` | ✅ |
| Tableau workbook + public link | [Tableau Public](https://public.tableau.com/app/profile/raphael.zafran/viz/AIJobMarketInterviewCoachMarketDashboards/D1-Overview) | ✅ D1 + D3 published |
| Screenshots for the deck | `demo_day/screenshots/` | ✅ 3 screenshots |

## 1. Purpose and audience

The dashboard answers the market half of the product story: **"What do employers ask for?"** The AI Interview Coach then answers: "How does *this* CV match *this* job, and how do I prepare?"

| Audience | Question | Where |
|---|---|---|
| Job seeker | Which skills are most demanded for my target role and country? | Dashboard 1, Dashboard 2 |
| Job seeker | Which skills mark senior roles? What do salaries look like? | Dashboard 2 |
| Job seeker | What does the current (2026) market snapshot look like? | Dashboard 3 |
| Instructor / jury | How do the statistics and the ML model support the product? | Dashboard 4 |

## 2. Data sources and the rule that keeps them correct

| File | Grain | Rows |
|---|---|---|
| `ref_overview_2023.csv` | role family × seniority × country group × remote × month | 3,850 |
| `ref_skill_demand_2023.csv` | skill × role family × seniority × country group × remote (dense) | 79,560 |
| `ref_skill_trend_2023.csv` | skill (≥ 1,000 postings) × role family × month (dense) | 10,836 |
| `ref_salary_by_role_2023.csv` | role family × seniority (percentiles computed in SQL) | 10 |
| `live_jobs_2026.csv` | one row per Arbeitnow posting (no description text; `url` = attribution link) | 3,026 |
| `live_skill_demand_2026.csv` | skill × job family × experience level × remote × language (dense) | 21,681 |
| `insights_*.csv` (5 files) | Phase 4 statistics and Phase 6 ML results | 7–71 each |

**Correctness rule:**
- All counts are **additive**, so Tableau may sum them under any filter.
- Ratios are always `SUM(numerator) / SUM(denominator)`, never an average of percentages.
- Skill tables are **dense**: every skill × group combination exists, with zeros included. Each row also carries its group's denominator (`postings_in_group`). The share of postings is therefore correct under any filter on the table's dimensions, without Tableau relationships or blending.
- Verified: AWS share among German Data Engineer postings = 33.34 % both from the extract and from a direct SQL query.

**Source separation:**
- 2023 reference data and 2026 live data are on **different dashboards**, labelled with source and year.
- No view mixes them or shows a "change" between them: the populations differ (data roles worldwide vs all occupations, mostly Germany).

## 3. Dashboards

Dashboard size: fixed 1366 × 900 (laptop projector friendly). Title on every dashboard, with a subtitle naming source, year and row count.

### Dashboard 1: "Data-role job market 2023: what employers ask for"

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Title + subtitle (source: lukebarousse/data_jobs 2023, 784,897 postings)           │
│ Filters: [Role family ▾] [Seniority ▾] [Country ▾] [Remote ▾] [Month range ▭]      │
├──────────┬──────────┬──────────┬────────────────┬──────────────────────────────────┤
│ Postings │ % remote │ % senior │ Avg advertised │ Avg skills per posting          │
│          │          │          │ salary (n=…)   │                                 │
├──────────┴──────────┴──────────┴───┬────────────┴──────────────────────────────────┤
│ Top 15 skills (% of postings)      │ Postings by role family × seniority           │
│ horizontal bars                    │ stacked horizontal bars                        │
├────────────────────────────────────┼───────────────────────────────────────────────┤
│ Postings per month (line)          │ Postings by country group (bars)              │
└────────────────────────────────────┴───────────────────────────────────────────────┘
```

| View | Answers | Encoding |
|---|---|---|
| KPI tiles | Size and profile of the filtered market | Big numbers; salary tile shows its n because only 2.8 % publish a salary |
| Top 15 skills | Which skills to learn for this slice | Bar length = share of postings, single blue |
| Role × seniority | Where the volume is | Stacked bars: Non-senior blue `#2a78d6`, Senior orange `#eb6834` |
| Postings per month | Seasonality within 2023 | Line |
| Country group | Where postings come from | Bars (top 15 countries + Other + Unknown) |

**Filters** (one row above the charts, applied to all views of the 2023 sources):
- Role family, Seniority, Country group, Remote.
- Month: applies to the overview views only, because the skill table has no month (stated in a caption).
- Interactivity: clicking a role bar filters the dashboard (filter action).

### Dashboard 2: "Skills, seniority and salary 2023"

| View | Answers |
|---|---|
| **Skill selector** (single-value dropdown) | Pick any of the 234 skills |
| Selected skill: share of postings by role family × seniority | Is the skill a senior or a role-specific requirement? |
| Selected skill: monthly share by role family (line) | Was demand stable over 2023? |
| Skills over-represented in senior postings (dot plot of odds ratios with CI, from Phase 4) | Which skills mark seniority (statistically tested) |
| Median advertised salary by role × seniority (bars with P25–P75 range) | Salary context (published-salary subset) |

Filters: Skill (single value), Role family, Country group, Remote.

### Dashboard 3: "Live job market snapshot (Arbeitnow API, Oct 2026)"

| View | Answers |
|---|---|
| KPI tiles: postings, % remote, % tech, % English descriptions | Profile of the current snapshot |
| Postings by job family (bars, tech families highlighted) | What kinds of jobs are on the board |
| Top 15 skills (% of postings) | What current postings ask for (coach taxonomy) |
| Experience level distribution | Seniority mix (employer-stated) |
| Postings table: title, company, city, level, link | Drill down to real postings (URL action opens the posting: attribution) |

Filters: Job family, Experience level, Remote, Description language, City (city applies to the KPIs and table only).

### Dashboard 4: "What the models say" (static insights)

- **ML model comparison:** macro-F1 and accuracy vs baselines.
- **Confusion matrix:** heatmap, % of true role.
- **Permutation importance:** the skills that drive the role prediction.
- **Salary model:** coefficient chart with confidence intervals.

No filters; used in the 15–20 min presentation mode.

## 4. Design rules

- **Colours:** one blue `#2a78d6` for single-measure bars; a fixed blue/orange pair for Non-senior/Senior. The pair passed the colour-vision-deficiency validator (ΔE 24.7). No rainbow palettes, no dual axes. Gridlines light grey.
- **Labels and hover:** percentages to 1 decimal, labels on the bars that matter, and hover tooltips with the numerator and denominator (e.g. "145,229 of 667,989 postings" for AWS, unfiltered).
- **Honesty captions:** each dashboard footer names the source, the year and the main caveat:
  - salary: published-salary subset;
  - live data: one week, Germany-centred, English-oriented skill detection.

## 5. Demo use (≈ 20–25 s of the live demo)

1. Open Dashboard 1, set **Role = Data Engineer**: the KPI tiles and top skills update (SQL 67.5 %, Python 64.9 %, AWS 38.6 %).
2. Set **Country = Germany**: AWS 33.3 %, Azure 35.8 %.
3. Switch to Dashboard 2 and pick **AWS**: the share is higher in senior postings, consistent with the odds ratio 1.47 in the dot plot.
4. Hand over to the coach: "the coach tells this candidate whether *their* CV covers what this market asks for".

## 6. Limitations

- **Pre-aggregated extracts.** There is no job-level 2023 table in the dashboard, so arbitrary combinations outside the extract grains (e.g. skill × schedule) are not possible. This keeps the files small enough to share (9.3 MB) and keeps every ratio correct.
- **Static snapshot.** The dashboard does not refresh. Re-running the pipeline and `market.dashboard.export`, then republishing, updates it.
- **Tableau Public** makes the workbook and its data public. Only public, licensed data is included: Apache-2.0 reference data, plus Arbeitnow postings with links back; no description text.
