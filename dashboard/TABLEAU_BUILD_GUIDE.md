# Tableau Public: Build Guide (manual step)

This is about 1.5–2 hours of clicking: Dashboards 1–3 are the core, and Dashboard 4 is optional. Every number you should see is listed in [`tableau/EXPECTED_VALUES.md`](tableau/EXPECTED_VALUES.md). The design rationale is in [`../docs/DASHBOARD.md`](../docs/DASHBOARD.md).

> **Field names.** Recent Tableau versions display CSV headers in a cleaned form: `postings_with_skill` appears as **Postings With Skill**. The formulas below use that form. If your version shows the raw names, use the raw names instead; the logic is identical.

## 0. Prerequisites

1. Create a free account at <https://public.tableau.com> and install **Tableau Public (desktop app)** for Windows or macOS. The browser editor ("Create a Viz") also works, but dashboard actions are more limited there.
2. Download the folder `dashboard/tableau/data/` from the GitHub repository: clone it, or use *Code → Download ZIP*.

## 1. Connect the data (one data source per file)

For each file: **Connect → To a File → Text file** → choose the CSV → in the data source tab check the types → rename the data source (right-click its name, top-left) as below.

| CSV | Rename data source to | Type checks |
|---|---|---|
| `ref_overview_2023.csv` | **2023 Overview** | `month` = Date |
| `ref_skill_demand_2023.csv` | **2023 Skill demand** | counts = Number (whole) |
| `ref_skill_trend_2023.csv` | **2023 Skill trend** | `month` = Date |
| `ref_salary_by_role_2023.csv` | **2023 Salary** | n/a |
| `live_jobs_2026.csv` | **2026 Live jobs** | `remote`, `is_tech` = Boolean; `url` = String |
| `live_skill_demand_2026.csv` | **2026 Live skill demand** | n/a |
| `insights_senior_skill_odds_ratios.csv` | **Insights: senior odds ratios** | n/a |
| `insights_ml_model_comparison.csv`, `insights_ml_confusion_matrix.csv`, `insights_ml_feature_importance.csv`, `insights_salary_model.csv` | **Insights: …** (Dashboard 4 only) | n/a |

**Do not join or relate the files.** Each data source is self-contained by design: dense skill tables with their own denominators.

## 2. Calculated fields

Create these with *Analysis → Create Calculated Field*, in the data source named in the left column.

| Data source | Name | Formula | Format |
|---|---|---|---|
| 2023 Overview | `Remote share` | `SUM(IF [Remote] = "Remote" THEN [Postings] END) / SUM([Postings])` | Percentage, 1 decimal |
| 2023 Overview | `Senior share` | `SUM(IF [Seniority] = "Senior" THEN [Postings] END) / SUM([Postings])` | Percentage, 1 decimal |
| 2023 Overview | `Avg advertised salary` | `SUM([Salary Sum]) / SUM([Postings With Salary])` | Number, 0 decimals, prefix `$` |
| 2023 Overview | `Avg skills per posting` | `SUM([Total Skills Listed]) / SUM([Postings With Skill Data])` | Number, 2 decimals |
| 2023 Skill demand | `Share of postings` | `SUM([Postings With Skill]) / SUM([Postings In Group])` | Percentage, 1 decimal |
| 2023 Skill trend | `Share of postings` | `SUM([Postings With Skill]) / SUM([Postings In Group])` | Percentage, 1 decimal |
| 2026 Live jobs | `Remote share` | `AVG(INT([Remote]))` | Percentage, 1 decimal |
| 2026 Live jobs | `Tech share` | `AVG(INT([Is Tech]))` | Percentage, 1 decimal |
| 2026 Live jobs | `English share` | `AVG(IF [Description Language] = "en" THEN 1 ELSE 0 END)` | Percentage, 1 decimal |
| 2026 Live skill demand | `Share of postings` | `SUM([Postings With Skill]) / SUM([Postings In Group])` | Percentage, 1 decimal |

⚠ A `Share of postings` value is only meaningful when **Skill** is on the view or filtered to one value. Every skill sheet below has Skill on Rows.

## 3. Worksheets

Create each sheet (*Worksheet → New Worksheet*), name the tab as shown, and use the indicated data source.

### Dashboard 1 sheets (2023 Overview / 2023 Skill demand)

| Sheet | Source | Build |
|---|---|---|
| **KPI Postings** | 2023 Overview | `SUM(Postings)` on *Text*; Marks = Text; font 28 pt |
| **KPI Remote** | 2023 Overview | `Remote share` on Text |
| **KPI Senior** | 2023 Overview | `Senior share` on Text |
| **KPI Salary** | 2023 Overview | `Avg advertised salary` and `SUM(Postings With Salary)` on Text → edit text: `<AGG(Avg advertised salary)>` new line `n = <SUM(Postings With Salary)> published salaries` |
| **KPI Skills** | 2023 Overview | `Avg skills per posting` on Text |
| **Top skills** | 2023 Skill demand | Rows: `Skill`; Columns: `Share of postings`; sort descending. Drag `Skill` to Filters → *Top* tab → *By field: Top 15 by Share of postings*. Colour `#2a78d6`; show mark labels. Tooltip: add `SUM(Postings With Skill)` and `SUM(Postings In Group)` |
| **Roles by seniority** | 2023 Overview | Rows: `Role Family` (sorted by SUM(Postings) desc); Columns: `SUM(Postings)`; Colour: `Seniority` → Non-senior `#2a78d6`, Senior `#eb6834` |
| **Postings per month** | 2023 Overview | Columns: `MONTH(Month)` (continuous, green pill); Rows: `SUM(Postings)`; Marks = Line, colour `#2a78d6` |
| **Countries** | 2023 Overview | Rows: `Country Group` sorted desc; Columns: `SUM(Postings)`; colour `#2a78d6` |

### Dashboard 2 sheets

| Sheet | Source | Build |
|---|---|---|
| **Skill by role** | 2023 Skill demand | Rows: `Role Family`; Columns: `Share of postings`; Colour: `Seniority` (same two colours). Filter `Skill` → *Show Filter* → single value (dropdown); default value **AWS** |
| **Skill trend** | 2023 Skill trend | Columns: `MONTH(Month)`; Rows: `Share of postings`; Colour: `Role Family`; Filter `Skill` → single value (dropdown), default **AWS** |
| **Senior skills (odds ratio)** | Insights: senior odds ratios | Rows: `Skill` sorted by `Odds Ratio`; Columns: `AVG(Odds Ratio)`, Marks = Circle. Add *Reference line* at constant 1. Filter `Significant Fdr 5Pct` = True. Use `Or Low`/`Or High` as a *Reference band* per cell if you want CIs (optional). Colour: `Odds Ratio > 1` → orange, else blue |
| **Salary by role** | 2023 Salary | Rows: `Role Family`; Columns: `SUM(Salary Median)`; Colour: `Seniority`; Tooltip: P25, P75, `Postings With Salary` |

### Dashboard 3 sheets (2026)

| Sheet | Source | Build |
|---|---|---|
| **Live KPIs** | 2026 Live jobs | `CNT(Job Id)` (or `COUNT(job_id)`), `Remote share`, `Tech share`, `English share` → use *Measure Names* on Columns and *Measure Values* on Text |
| **Live families** | 2026 Live jobs | Rows: `Job Family` sorted desc; Columns: `CNT(Job Id)`; Colour: `Is Tech` (True `#2a78d6`, False light grey `#c3c2b7`) |
| **Live top skills** | 2026 Live skill demand | Same as *Top skills* (Top 15 by Share of postings) |
| **Live levels** | 2026 Live jobs | Rows: `Experience Level` (sort manually: student_intern, entry, mid, experienced, lead_manager, not stated); Columns: `CNT(Job Id)` |
| **Live postings** | 2026 Live jobs | Rows: `Title`, `Company`, `City`, `Experience Level`; Marks = Text with `CNT(Job Id)` hidden. Used for the URL action |

### Dashboard 4 sheets (optional, static)

One sheet per insights file:
- **Model comparison:** `Model` × `Macro F1` and `Accuracy` side by side.
- **Confusion matrix:** `True Role` on Rows, `Predicted Role` on Columns, Marks = Square, colour and label `Pct Of True Role`.
- **Feature importance:** top 15 by `Mean`.
- **Salary model:** `Term` × `Pct Difference`, with `Ci Low`/`Ci High` as a reference band.

## 4. Dashboards

For each: *Dashboard → New Dashboard*, Size = **Fixed 1366 × 900**.

1. Add a **Text** object at the top with the title and subtitle:
   - D1: *"Data-role job market 2023: what employers ask for"*, subtitle *"Source: lukebarousse/data_jobs (Apache-2.0), 784,897 postings, 2023"*
   - D2: *"Skills, seniority and salary (2023)"*, subtitle *"Odds ratios: Cochran-Mantel-Haenszel within role; salary: 21,997 postings publishing a salary"*
   - D3: *"Live job market snapshot (Arbeitnow API, 1–8 Oct 2026)"*, subtitle *"3,026 postings, all occupations, mostly Germany. Not comparable with the 2023 data"*
   - D4: *"What the models say"*
2. Drag the sheets into the layout drawn in `docs/DASHBOARD.md` §3 (a horizontal container for the KPI tiles, two rows of charts below).
3. **Filters (one row under the title):** on a chart of the dashboard, open the dropdown menu of a filter card → *Filters* → choose the field → then on the card *Apply to Worksheets → All Using Related Data Sources*. This makes, for example, `Role Family` filter both 2023 data sources, because the field names match.

   | Dashboard | Filters (control type) |
   |---|---|
   | D1 | Role Family (multi-value dropdown), Seniority (single value list), Country Group (multi-value dropdown), Remote (single value list), Month (range of dates: **apply to *2023 Overview* only** and add the caption "Month applies to volume charts") |
   | D2 | Skill (single value dropdown, **apply to Skill by role + Skill trend**), Role Family, Country Group, Remote |
   | D3 | Job Family, Experience Level, Remote, Description Language (all *All Using Related Data Sources*), City (apply to Live KPIs + Live postings only) |

4. **Actions:**
   - D1: *Dashboard → Actions → Add Action → Filter*. Source sheet *Roles by seniority*, run on **Select**, target all sheets, clearing the selection shows all values.
   - D3: *Add Action → Go to URL*. Source *Live postings*, run on **Menu**, URL = `<Url>` (the field). This is the "link back" to the original posting.
5. **Footer** text on each dashboard: *"Built by Raphael Zafran, AI Job Market & Interview Coach, data prepared with Python/pandas + PostgreSQL. Shares = postings mentioning the skill ÷ postings in the filtered group."*

## 5. Check your build

Compare with [`tableau/EXPECTED_VALUES.md`](tableau/EXPECTED_VALUES.md). For example:

- **D1, no filters:** Postings 784,897 · Remote 8.9 % · Senior 14.1 % · Avg salary 123,292 (n = 21,997) · top skill SQL 57.7 %.
- **D1, Role = Data Engineer, Country = Germany:** top skills Python 66.1 %, SQL 57.6 %, Azure 35.8 %, AWS 33.3 %, Spark 30.4 %.
- **D3, no filters:** 3,026 postings · remote 9.6 % · tech 27.4 %.

If a number differs:
- check that the ratio is `SUM(...)/SUM(...)`, not `AVG` of a percentage;
- check that Skill is on the view;
- check the filter's *Apply to Worksheets* setting.

## 6. Publish and share

1. *File → Save to Tableau Public As…* → name **"AI Job Market & Interview Coach: Market Dashboards"**. Sign in when asked; the workbook is published publicly.
2. On public.tableau.com: open the viz → *Settings* → turn on **"Show Viz on Profile"** and **"Allow access"** (download) if you want reviewers to open the workbook.
3. Copy the link and send it to me. I will add it to the README, the deck and the portfolio entry.
4. Take screenshots: D1 unfiltered; D1 with Data Engineer + Germany; D2 with AWS; D3. Save them as PNG in `demo_day/screenshots/` with these names:
   - `dashboard_overview.png`
   - `dashboard_filtered_de_germany.png`
   - `dashboard_skill_aws.png`
   - `dashboard_live.png`

   Only these real screenshots will be used in the presentation.

## 7. Regenerate the data later

```bash
python -m market.pipeline && python -m market.db.load     # refresh data (new API snapshot optional)
python -m market.dashboard.export                         # new CSVs + validation + expected values
```

Then in Tableau: *Data → Refresh All Extracts* (or replace the files), and save to Tableau Public again.
