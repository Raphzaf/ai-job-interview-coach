-- Reusable analytical views (read by the coach, notebooks and Tableau exports).
-- Shares are always computed WITHIN one source.
SET search_path = market;

-- Postings with skill information in the reference source (denominator for skill shares).
CREATE OR REPLACE VIEW v_reference_jobs_with_skills AS
SELECT * FROM jobs_reference WHERE NOT skills_missing;

-- Skill demand per role family and seniority in the 2023 reference data.
CREATE OR REPLACE VIEW v_reference_skill_demand AS
WITH groups AS (
    SELECT role_family, is_senior, COUNT(*) AS postings
    FROM v_reference_jobs_with_skills
    GROUP BY role_family, is_senior
)
SELECT j.role_family,
       j.is_senior,
       s.name                       AS skill,
       s.category,
       COUNT(*)                     AS postings_with_skill,
       g.postings                   AS postings_in_group,
       ROUND(100.0 * COUNT(*) / g.postings, 2) AS share_pct
FROM v_reference_jobs_with_skills j
JOIN job_skills_reference js ON js.job_id = j.job_id
JOIN skills s                ON s.skill_id = js.skill_id
JOIN groups g                ON g.role_family = j.role_family AND g.is_senior = j.is_senior
GROUP BY j.role_family, j.is_senior, s.name, s.category, g.postings;

-- Skill demand in the live snapshot, per job family.
CREATE OR REPLACE VIEW v_live_skill_demand AS
WITH families AS (
    SELECT job_family, COUNT(*) AS postings FROM jobs_live GROUP BY job_family
)
SELECT j.job_family,
       s.name                       AS skill,
       s.category,
       COUNT(*)                     AS postings_with_skill,
       f.postings                   AS postings_in_family,
       ROUND(100.0 * COUNT(*) / f.postings, 2) AS share_pct
FROM jobs_live j
JOIN job_skills_live js ON js.job_id = j.job_id
JOIN skills s           ON s.skill_id = js.skill_id
JOIN families f         ON f.job_family = j.job_family
GROUP BY j.job_family, s.name, s.category, f.postings;

-- One row per role family / seniority with volume, remote share and salary.
CREATE OR REPLACE VIEW v_reference_role_summary AS
SELECT role_family,
       is_senior,
       COUNT(*)                                                    AS postings,
       ROUND(100.0 * AVG(work_from_home::int), 2)                  AS remote_pct,
       ROUND(AVG(skill_count), 2)                                  AS avg_skill_count,
       COUNT(salary_year_avg)                                      AS postings_with_salary,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_year_avg) AS median_salary_year
FROM jobs_reference
GROUP BY role_family, is_senior;

-- Live snapshot overview per job family (no free text).
CREATE OR REPLACE VIEW v_live_family_summary AS
SELECT job_family,
       COUNT(*)                                          AS postings,
       ROUND(100.0 * AVG(remote::int), 2)                AS remote_pct,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY skill_count) AS median_skill_count,
       COUNT(experience_level)                           AS postings_with_level,
       ROUND(100.0 * AVG((description_language = 'en')::int), 2) AS english_description_pct
FROM jobs_live
GROUP BY job_family;
