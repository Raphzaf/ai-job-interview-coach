-- =============================================================================
-- Tableau Public extracts (Tableau Public reads files, not PostgreSQL).
-- Run: python -m market.dashboard.export   (read-only role, DATABASE_URL)
-- Each "-- name:" block becomes dashboard/tableau/data/<name>.csv
--
-- Design rule for every *skill* table: it is DENSE (one row per skill x filter
-- combination, zero counts included) and carries its own denominator, so that
--     share = SUM(postings_with_skill) / SUM(postings_in_group)
-- is correct under ANY combination of the table's filter dimensions, without
-- Tableau relationships or blending. The two sources are never mixed in one file.
-- =============================================================================

-- name: ref_overview_2023
-- grain: role family x seniority x country group x remote x month (data_jobs 2023)
WITH top_countries AS (
    SELECT country FROM market.jobs_reference WHERE country IS NOT NULL
    GROUP BY country ORDER BY COUNT(*) DESC LIMIT 15
)
SELECT j.role_family,
       CASE WHEN j.is_senior THEN 'Senior' ELSE 'Non-senior' END                     AS seniority,
       CASE WHEN j.country IS NULL THEN 'Unknown'
            WHEN j.country IN (SELECT country FROM top_countries) THEN j.country
            ELSE 'Other countries' END                                                AS country_group,
       CASE WHEN j.work_from_home THEN 'Remote' ELSE 'On-site / hybrid' END          AS remote,
       j.posted_month                                                                 AS month,
       COUNT(*)                                                                       AS postings,
       COUNT(*) FILTER (WHERE NOT j.skills_missing)                                   AS postings_with_skill_data,
       COALESCE(SUM(j.skill_count), 0)                                                AS total_skills_listed,
       COUNT(j.salary_year_avg)                                                       AS postings_with_salary,
       COALESCE(ROUND(SUM(j.salary_year_avg), 2), 0)                                  AS salary_sum
FROM market.jobs_reference j
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4, 5;

-- name: ref_skill_demand_2023
-- grain: skill x role family x seniority x country group x remote (dense)
WITH top_countries AS (
    SELECT country FROM market.jobs_reference WHERE country IS NOT NULL
    GROUP BY country ORDER BY COUNT(*) DESC LIMIT 15
), j AS (
    SELECT job_id, role_family,
           CASE WHEN is_senior THEN 'Senior' ELSE 'Non-senior' END AS seniority,
           CASE WHEN country IS NULL THEN 'Unknown'
                WHEN country IN (SELECT country FROM top_countries) THEN country
                ELSE 'Other countries' END AS country_group,
           CASE WHEN work_from_home THEN 'Remote' ELSE 'On-site / hybrid' END AS remote
    FROM market.jobs_reference
    WHERE NOT skills_missing                                  -- denominator: postings with skill data
), groups AS (
    SELECT role_family, seniority, country_group, remote, COUNT(*) AS postings_in_group
    FROM j GROUP BY 1, 2, 3, 4
), counts AS (
    SELECT js.skill_id, j.role_family, j.seniority, j.country_group, j.remote, COUNT(*) AS postings_with_skill
    FROM j JOIN market.job_skills_reference js ON js.job_id = j.job_id
    GROUP BY 1, 2, 3, 4, 5
), used_skills AS (
    SELECT DISTINCT skill_id FROM market.job_skills_reference
)
SELECT s.name AS skill, s.category AS skill_category, s.in_coach_taxonomy,
       g.role_family, g.seniority, g.country_group, g.remote,
       COALESCE(c.postings_with_skill, 0) AS postings_with_skill,
       g.postings_in_group
FROM groups g
CROSS JOIN used_skills u
JOIN market.skills s ON s.skill_id = u.skill_id
LEFT JOIN counts c ON c.skill_id = u.skill_id AND c.role_family = g.role_family AND c.seniority = g.seniority
                  AND c.country_group = g.country_group AND c.remote = g.remote
ORDER BY 1, 4, 5, 6, 7;

-- name: ref_skill_trend_2023
-- grain: skill x role family x month (dense), for "skill demand over 2023"
WITH j AS (
    SELECT job_id, role_family, posted_month FROM market.jobs_reference WHERE NOT skills_missing
), groups AS (
    SELECT role_family, posted_month, COUNT(*) AS postings_in_group FROM j GROUP BY 1, 2
), counts AS (
    SELECT js.skill_id, j.role_family, j.posted_month, COUNT(*) AS postings_with_skill
    FROM j JOIN market.job_skills_reference js ON js.job_id = j.job_id
    GROUP BY 1, 2, 3
), used_skills AS (
    SELECT skill_id FROM market.job_skills_reference GROUP BY 1 HAVING COUNT(*) >= 1000   -- stable monthly shares
)
SELECT s.name AS skill, s.category AS skill_category, g.role_family, g.posted_month AS month,
       COALESCE(c.postings_with_skill, 0) AS postings_with_skill, g.postings_in_group
FROM groups g
CROSS JOIN used_skills u
JOIN market.skills s ON s.skill_id = u.skill_id
LEFT JOIN counts c ON c.skill_id = u.skill_id AND c.role_family = g.role_family AND c.posted_month = g.posted_month
ORDER BY 1, 3, 4;

-- name: live_jobs_2026
-- grain: one row per posting of the Arbeitnow API snapshot (no free text; url kept for attribution)
SELECT j.job_id, j.title, c.name AS company, j.city, j.remote, j.job_family, j.is_tech,
       COALESCE(j.experience_level, 'not stated') AS experience_level,
       j.seniority_from_title, COALESCE(j.schedule, 'not stated') AS schedule,
       COALESCE(j.contract_type, 'not stated') AS contract_type, j.description_language,
       j.skill_count, j.tech_skill_count, j.soft_skill_count, j.requires_english, j.requires_german,
       j.posted_at::date AS posted_date, j.url
FROM market.jobs_live j
LEFT JOIN market.companies c ON c.company_id = j.company_id
ORDER BY j.posted_at DESC;

-- name: live_skill_demand_2026
-- grain: skill x job family x experience level x remote x description language (dense)
WITH j AS (
    SELECT job_id, job_family, COALESCE(experience_level, 'not stated') AS experience_level,
           CASE WHEN remote THEN 'Remote' ELSE 'On-site / hybrid' END AS remote, description_language
    FROM market.jobs_live
), groups AS (
    SELECT job_family, experience_level, remote, description_language, COUNT(*) AS postings_in_group
    FROM j GROUP BY 1, 2, 3, 4
), counts AS (
    SELECT js.skill_id, j.job_family, j.experience_level, j.remote, j.description_language, COUNT(*) AS postings_with_skill
    FROM j JOIN market.job_skills_live js ON js.job_id = j.job_id
    GROUP BY 1, 2, 3, 4, 5
), used_skills AS (
    SELECT DISTINCT skill_id FROM market.job_skills_live
)
SELECT s.name AS skill, s.category AS skill_category,
       g.job_family, g.experience_level, g.remote, g.description_language,
       COALESCE(c.postings_with_skill, 0) AS postings_with_skill, g.postings_in_group
FROM groups g
CROSS JOIN used_skills u
JOIN market.skills s ON s.skill_id = u.skill_id
LEFT JOIN counts c ON c.skill_id = u.skill_id AND c.job_family = g.job_family AND c.experience_level = g.experience_level
                  AND c.remote = g.remote AND c.description_language = g.description_language
ORDER BY 1, 3, 4, 5, 6;

-- name: ref_salary_by_role_2023
-- grain: role family x seniority; medians cannot be re-aggregated in Tableau, so they are computed here
SELECT role_family,
       CASE WHEN is_senior THEN 'Senior' ELSE 'Non-senior' END AS seniority,
       COUNT(*)                                                   AS postings_with_salary,
       ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY salary_year_avg)::numeric, 0) AS salary_p25,
       ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY salary_year_avg)::numeric, 0) AS salary_median,
       ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY salary_year_avg)::numeric, 0) AS salary_p75
FROM market.jobs_reference
WHERE salary_year_avg IS NOT NULL
GROUP BY 1, 2
HAVING COUNT(*) >= 30
ORDER BY 1, 2;
