-- =============================================================================
-- Analytical SQL: AI Job Market & Interview Coach
--
-- Each query starts with "-- name: <id>" and a "-- question:" line; it is run
-- by `python -m market.db.run_queries` (as the read-only role) and its result
-- saved to data/processed/sql_results/<id>.csv, so every number quoted in the
-- documentation is reproducible.
--
-- Population rule: jobs_live (Arbeitnow API snapshot, Oct 2026, all
-- occupations) and jobs_reference (data_jobs 2023, data roles) are analysed
-- SEPARATELY. No query pools or time-compares the two sources.
-- =============================================================================

-- name: 01_table_row_counts
-- question: How many rows does each table hold after loading? (sanity check vs. Phase 2 reports)
-- demonstrates: UNION ALL, aggregate COUNT
SELECT 'sources' AS table_name, COUNT(*) AS row_count FROM market.sources
UNION ALL SELECT 'companies', COUNT(*) FROM market.companies
UNION ALL SELECT 'skills', COUNT(*) FROM market.skills
UNION ALL SELECT 'jobs_live', COUNT(*) FROM market.jobs_live
UNION ALL SELECT 'job_skills_live', COUNT(*) FROM market.job_skills_live
UNION ALL SELECT 'jobs_reference', COUNT(*) FROM market.jobs_reference
UNION ALL SELECT 'job_skills_reference', COUNT(*) FROM market.job_skills_reference
ORDER BY table_name;

-- name: 02_reference_top_skills
-- question: Which skills are most demanded in 2023 data-role postings?
-- demonstrates: JOIN, GROUP BY, ORDER BY, LIMIT, scalar subquery as denominator
SELECT s.name                                   AS skill,
       s.category,
       COUNT(*)                                 AS postings,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM market.jobs_reference WHERE NOT skills_missing), 2)
                                                AS share_of_postings_pct
FROM market.job_skills_reference js
JOIN market.skills s ON s.skill_id = js.skill_id
GROUP BY s.name, s.category
ORDER BY postings DESC
LIMIT 15;

-- name: 03_reference_top5_skills_per_role
-- question: What are the five most demanded skills for each data role family?
-- demonstrates: CTE, JOIN, window function RANK() OVER (PARTITION BY ...)
WITH role_skill AS (
    SELECT j.role_family, s.name AS skill, COUNT(*) AS postings
    FROM market.jobs_reference j
    JOIN market.job_skills_reference js ON js.job_id = j.job_id
    JOIN market.skills s                ON s.skill_id = js.skill_id
    GROUP BY j.role_family, s.name
), role_size AS (
    SELECT role_family, COUNT(*) AS postings_with_skills
    FROM market.jobs_reference WHERE NOT skills_missing GROUP BY role_family
), ranked AS (
    SELECT rs.role_family, rs.skill, rs.postings,
           ROUND(100.0 * rs.postings / z.postings_with_skills, 1) AS share_pct,
           RANK() OVER (PARTITION BY rs.role_family ORDER BY rs.postings DESC) AS skill_rank
    FROM role_skill rs JOIN role_size z USING (role_family)
)
SELECT role_family, skill_rank, skill, postings, share_pct
FROM ranked
WHERE skill_rank <= 5
ORDER BY role_family, skill_rank;

-- name: 04_reference_senior_skill_lift
-- question: Which skills are relatively more frequent in senior than in non-senior data postings?
-- demonstrates: CTE, conditional aggregation (FILTER), JOIN, HAVING (minimum support), derived ratio
-- note: descriptive association only; significance testing is done in the statistics phase.
WITH base AS (
    SELECT job_id, is_senior FROM market.jobs_reference WHERE NOT skills_missing
), totals AS (
    SELECT COUNT(*) FILTER (WHERE is_senior) AS senior_n,
           COUNT(*) FILTER (WHERE NOT is_senior) AS other_n
    FROM base
), per_skill AS (
    SELECT s.name AS skill,
           COUNT(*) FILTER (WHERE b.is_senior)     AS senior_postings,
           COUNT(*) FILTER (WHERE NOT b.is_senior) AS other_postings
    FROM base b
    JOIN market.job_skills_reference js ON js.job_id = b.job_id
    JOIN market.skills s                ON s.skill_id = js.skill_id
    GROUP BY s.name
    HAVING COUNT(*) >= 5000                       -- ignore rare skills (unstable ratios)
)
SELECT p.skill,
       ROUND(100.0 * p.senior_postings / t.senior_n, 2) AS senior_share_pct,
       ROUND(100.0 * p.other_postings / t.other_n, 2)   AS non_senior_share_pct,
       ROUND((p.senior_postings::numeric / t.senior_n) / NULLIF(p.other_postings::numeric / t.other_n, 0), 2)
                                                        AS senior_lift
FROM per_skill p CROSS JOIN totals t
ORDER BY senior_lift DESC
LIMIT 15;

-- name: 05_reference_salary_by_role_seniority
-- question: What is the median advertised annual salary by role family and seniority?
-- demonstrates: WHERE on NULLs, GROUP BY two keys, ordered-set aggregate PERCENTILE_CONT, HAVING
-- note: only 2.8% of postings publish a salary; groups with fewer than 30 salaries are hidden.
SELECT role_family,
       CASE WHEN is_senior THEN 'Senior' ELSE 'Non-senior' END AS seniority,
       COUNT(*)                                                   AS postings_with_salary,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_year_avg)::numeric, 0)  AS median_salary_year,
       ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY salary_year_avg)::numeric, 0) AS p25,
       ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY salary_year_avg)::numeric, 0) AS p75
FROM market.jobs_reference
WHERE salary_year_avg IS NOT NULL
GROUP BY role_family, is_senior
HAVING COUNT(*) >= 30
ORDER BY role_family, seniority;

-- name: 06_reference_remote_by_role
-- question: How common is remote work in each data role family (2023)?
-- demonstrates: aggregate on a boolean cast, GROUP BY, ORDER BY
SELECT role_family,
       COUNT(*)                                      AS postings,
       SUM(work_from_home::int)                      AS remote_postings,
       ROUND(100.0 * AVG(work_from_home::int), 2)    AS remote_pct
FROM market.jobs_reference
GROUP BY role_family
ORDER BY remote_pct DESC;

-- name: 07_reference_skill_count_by_seniority
-- question: Do senior data postings list more skills than non-senior ones (descriptive)?
-- demonstrates: GROUP BY, AVG/STDDEV/PERCENTILE_CONT, WHERE excluding unknown skill lists
SELECT role_family,
       CASE WHEN is_senior THEN 'Senior' ELSE 'Non-senior' END AS seniority,
       COUNT(*)                                                 AS postings,
       ROUND(AVG(skill_count), 2)                               AS mean_skills,
       ROUND(STDDEV_SAMP(skill_count), 2)                       AS sd_skills,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY skill_count) AS median_skills
FROM market.jobs_reference
WHERE NOT skills_missing
  AND role_family IN ('Data Analyst', 'Data Engineer', 'Data Scientist')   -- the roles with a Senior variant
GROUP BY role_family, is_senior
ORDER BY role_family, seniority;

-- name: 08_reference_monthly_postings
-- question: How are 2023 postings distributed over the months (within the reference source only)?
-- demonstrates: date bucketing, GROUP BY, ORDER BY
SELECT to_char(posted_month, 'YYYY-MM') AS month,
       COUNT(*)                          AS postings,
       ROUND(100.0 * AVG(work_from_home::int), 2) AS remote_pct
FROM market.jobs_reference
GROUP BY posted_month
ORDER BY posted_month;

-- name: 09_live_family_overview
-- question: What does the current (Oct 2026) Arbeitnow snapshot look like per job family?
-- demonstrates: view usage, ORDER BY
SELECT job_family, postings, remote_pct, median_skill_count, postings_with_level, english_description_pct
FROM market.v_live_family_summary
ORDER BY postings DESC;

-- name: 10_live_top_skills_tech_vs_non_tech
-- question: Which skills are most frequent in tech vs non-tech postings of the live snapshot?
-- demonstrates: JOIN, conditional aggregation with FILTER, scalar subqueries, ORDER BY
SELECT s.name AS skill,
       s.category,
       COUNT(*) FILTER (WHERE j.is_tech)     AS tech_postings,
       ROUND(100.0 * COUNT(*) FILTER (WHERE j.is_tech)
             / (SELECT COUNT(*) FROM market.jobs_live WHERE is_tech), 2)     AS tech_share_pct,
       COUNT(*) FILTER (WHERE NOT j.is_tech) AS non_tech_postings,
       ROUND(100.0 * COUNT(*) FILTER (WHERE NOT j.is_tech)
             / (SELECT COUNT(*) FROM market.jobs_live WHERE NOT is_tech), 2) AS non_tech_share_pct
FROM market.jobs_live j
JOIN market.job_skills_live js ON js.job_id = j.job_id
JOIN market.skills s           ON s.skill_id = js.skill_id
GROUP BY s.name, s.category
ORDER BY tech_postings DESC
LIMIT 20;

-- name: 11_live_experience_level_profile
-- question: How do skill counts, remote work and English descriptions vary with the employer-stated experience level?
-- demonstrates: WHERE, GROUP BY with CASE ordering, AVG/PERCENTILE_CONT
SELECT experience_level,
       COUNT(*)                                                  AS postings,
       ROUND(AVG(skill_count), 2)                                AS mean_skills,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY skill_count)  AS median_skills,
       ROUND(100.0 * AVG(remote::int), 2)                        AS remote_pct,
       ROUND(100.0 * AVG((description_language = 'en')::int), 2) AS english_pct
FROM market.jobs_live
WHERE experience_level IS NOT NULL
GROUP BY experience_level
ORDER BY CASE experience_level WHEN 'student_intern' THEN 1 WHEN 'entry' THEN 2 WHEN 'mid' THEN 3
                               WHEN 'experienced' THEN 4 ELSE 5 END;

-- name: 12_live_cities
-- question: Where are the live postings located, and how remote-friendly is each city?
-- demonstrates: WHERE IS NOT NULL, GROUP BY, HAVING, ORDER BY
SELECT city,
       COUNT(*)                                  AS postings,
       SUM(is_tech::int)                         AS tech_postings,
       ROUND(100.0 * AVG(remote::int), 2)        AS remote_pct
FROM market.jobs_live
WHERE city IS NOT NULL
GROUP BY city
HAVING COUNT(*) >= 20
ORDER BY postings DESC;

-- name: 13_live_companies_above_average
-- question: Which employers post more jobs than the average employer in the live snapshot?
-- demonstrates: JOIN, GROUP BY, HAVING with a subquery (nested aggregate)
SELECT c.name AS company,
       COUNT(*) AS postings,
       SUM(j.is_tech::int) AS tech_postings
FROM market.jobs_live j
JOIN market.companies c ON c.company_id = j.company_id
GROUP BY c.name
HAVING COUNT(*) > (
    SELECT AVG(n) FROM (SELECT COUNT(*) AS n FROM market.jobs_live GROUP BY company_id) per_company
)
ORDER BY postings DESC
LIMIT 15;

-- name: 14_live_tech_jobs_with_cloud_and_ai
-- question: Among live tech postings, how many ask for both cloud/DevOps and AI/ML skills?
-- demonstrates: EXISTS-style filtering with IN subqueries, boolean logic, aggregates
SELECT COUNT(*)                                                           AS tech_postings,
       COUNT(*) FILTER (WHERE cloud_devops_skill_count > 0)               AS with_cloud_devops,
       COUNT(*) FILTER (WHERE ai_ml_skill_count > 0)                      AS with_ai_ml,
       COUNT(*) FILTER (WHERE cloud_devops_skill_count > 0 AND ai_ml_skill_count > 0) AS with_both,
       COUNT(*) FILTER (WHERE job_id IN (
           SELECT js.job_id FROM market.job_skills_live js
           JOIN market.skills s ON s.skill_id = js.skill_id
           WHERE s.name IN ('LLMs', 'RAG', 'Generative AI')))             AS mentioning_genai
FROM market.jobs_live
WHERE is_tech;

-- name: 15_data_quality_checks
-- question: Are the cleaning decisions visible and consistent in the database?
-- demonstrates: aggregate checks, FILTER, cross-table consistency via NOT EXISTS
SELECT 'reference rows with repaired country' AS check_name,
       COUNT(*) FILTER (WHERE country_repaired)::text AS value FROM market.jobs_reference
UNION ALL
SELECT 'reference rows with unknown skills',
       COUNT(*) FILTER (WHERE skills_missing)::text FROM market.jobs_reference
UNION ALL
SELECT 'reference postings without any job_skills row but skills_missing = false',
       COUNT(*)::text FROM market.jobs_reference j
       WHERE NOT j.skills_missing
         AND NOT EXISTS (SELECT 1 FROM market.job_skills_reference js WHERE js.job_id = j.job_id)
UNION ALL
SELECT 'live postings flagged as probable re-posts',
       COUNT(*) FILTER (WHERE probable_repost)::text FROM market.jobs_live
UNION ALL
SELECT 'live postings whose skill_count differs from job_skills rows',
       COUNT(*)::text FROM market.jobs_live j
       WHERE j.skill_count <> (SELECT COUNT(*) FROM market.job_skills_live js WHERE js.job_id = j.job_id);
