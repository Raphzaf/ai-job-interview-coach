-- =============================================================================
-- AI Job Market & Interview Coach: PostgreSQL schema (schema "market")
--
-- Run as the owner role (coach_owner) inside database job_market:
--   python -m market.db.setup   (roles, database, this file, views.sql)
--
-- Design (see docs/DATABASE.md):
--   * one fact table per source (jobs_live = Arbeitnow API snapshot,
--     jobs_reference = lukebarousse/data_jobs 2023) so the two populations can
--     never be pooled by accident;
--   * shared dimensions: sources, companies, skills;
--   * many-to-many link tables job_skills_live / job_skills_reference;
--   * free-text descriptions isolated in job_descriptions (not readable by the
--     read-only role, because some contain recruiters' phone numbers).
-- The file is idempotent: it drops and recreates the schema's tables.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS market;
SET search_path = market;

DROP TABLE IF EXISTS job_skills_reference, job_skills_live, job_descriptions,
                     jobs_reference, jobs_live, skills, companies, sources CASCADE;

CREATE TABLE sources (
    source_id     text PRIMARY KEY,                 -- 'arbeitnow', 'data_jobs_2023'
    name          text NOT NULL,
    url           text NOT NULL,
    license       text NOT NULL,
    version       text NOT NULL,                    -- snapshot id / dataset commit
    collected_at  timestamptz NOT NULL,
    raw_rows      integer NOT NULL CHECK (raw_rows >= 0),
    clean_rows    integer NOT NULL CHECK (clean_rows >= 0 AND clean_rows <= raw_rows)
);

CREATE TABLE companies (
    company_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL UNIQUE
);

CREATE TABLE skills (
    skill_id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               text NOT NULL UNIQUE,
    category           text NOT NULL,
    in_coach_taxonomy  boolean NOT NULL
);

CREATE TABLE jobs_live (
    job_id                      text PRIMARY KEY CHECK (job_id LIKE 'arbeitnow:%'),
    source_id                   text NOT NULL REFERENCES sources,
    company_id                  integer REFERENCES companies,
    slug                        text NOT NULL UNIQUE,
    url                         text NOT NULL,          -- kept for attribution / link back
    title                       text NOT NULL,
    location                    text,
    city                        text,
    remote                      boolean NOT NULL,
    posted_at                   timestamptz NOT NULL,
    job_family                  text NOT NULL,
    is_tech                     boolean NOT NULL,
    experience_level            text CHECK (experience_level IN
                                    ('student_intern', 'entry', 'mid', 'experienced', 'lead_manager')),
    experience_level_ambiguous  boolean NOT NULL,
    seniority_from_title        text NOT NULL CHECK (seniority_from_title IN ('junior', 'senior', 'unspecified')),
    schedule                    text CHECK (schedule IN ('full_time', 'part_time', 'full_or_part_time')),
    contract_type               text CHECK (contract_type IN ('permanent', 'fixed_term', 'freelance')),
    probable_repost             boolean NOT NULL,
    description_language        text NOT NULL CHECK (description_language IN ('en', 'de', 'unknown')),
    description_chars           integer NOT NULL CHECK (description_chars > 0),
    description_words           integer NOT NULL CHECK (description_words > 0),
    skill_count                 smallint NOT NULL CHECK (skill_count >= 0),
    tech_skill_count            smallint NOT NULL CHECK (tech_skill_count >= 0),
    soft_skill_count            smallint NOT NULL CHECK (soft_skill_count >= 0),
    programming_language_count  smallint NOT NULL CHECK (programming_language_count >= 0),
    cloud_devops_skill_count    smallint NOT NULL CHECK (cloud_devops_skill_count >= 0),
    ai_ml_skill_count           smallint NOT NULL CHECK (ai_ml_skill_count >= 0),
    data_skill_count            smallint NOT NULL CHECK (data_skill_count >= 0),
    requires_english            boolean NOT NULL,
    requires_german             boolean NOT NULL,
    tags                        text[] NOT NULL,
    job_types_raw               text[] NOT NULL
);

CREATE TABLE job_descriptions (
    job_id    text PRIMARY KEY REFERENCES jobs_live ON DELETE CASCADE,
    language  text NOT NULL,
    body      text NOT NULL
);

CREATE TABLE jobs_reference (
    job_id                     text PRIMARY KEY CHECK (job_id LIKE 'data_jobs:%'),
    source_id                  text NOT NULL REFERENCES sources,
    company_id                 integer REFERENCES companies,
    job_title                  text,
    job_title_short            text NOT NULL,
    role_family                text NOT NULL,
    is_senior                  boolean NOT NULL,
    title_seniority            text NOT NULL CHECK (title_seniority IN ('junior', 'senior', 'unspecified')),
    job_location               text,
    country                    text,
    country_repaired           boolean NOT NULL,
    search_location            text NOT NULL,
    job_via                    text,
    schedule                   text NOT NULL,
    work_from_home             boolean NOT NULL,
    no_degree_mention          boolean NOT NULL,
    health_insurance           boolean NOT NULL,
    posted_at                  timestamp NOT NULL,
    posted_month               date NOT NULL,
    salary_rate                text,
    salary_year_avg            numeric(10, 2) CHECK (salary_year_avg > 0),
    salary_hour_avg            numeric(10, 2) CHECK (salary_hour_avg > 0),
    skills_missing             boolean NOT NULL,
    skill_count                smallint CHECK (skill_count >= 0),   -- NULL = skills not extracted
    programming_skill_count    smallint,
    cloud_skill_count          smallint,
    libraries_skill_count      smallint,
    databases_skill_count      smallint,
    analyst_tools_skill_count  smallint,
    other_skill_count          smallint,
    os_skill_count             smallint,
    webframeworks_skill_count  smallint,
    async_skill_count          smallint,
    sync_skill_count           smallint,
    -- skill counts are unknown exactly when the skill list was not extracted
    CHECK (skills_missing = (skill_count IS NULL))
);

CREATE TABLE job_skills_live (
    job_id    text    NOT NULL REFERENCES jobs_live ON DELETE CASCADE,
    skill_id  integer NOT NULL REFERENCES skills,
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE job_skills_reference (
    job_id      text    NOT NULL REFERENCES jobs_reference ON DELETE CASCADE,
    skill_id    integer NOT NULL REFERENCES skills,
    skill_type  text    NOT NULL,
    skill_raw   text    NOT NULL,
    PRIMARY KEY (job_id, skill_id)
);

-- Indexes for the access paths used by the analyses, the coach and the exports
-- (the primary keys already index job_id lookups).
CREATE INDEX job_skills_live_skill_idx      ON job_skills_live (skill_id);
CREATE INDEX job_skills_reference_skill_idx ON job_skills_reference (skill_id);
CREATE INDEX jobs_reference_role_idx        ON jobs_reference (role_family, is_senior);
CREATE INDEX jobs_reference_country_idx     ON jobs_reference (country);
CREATE INDEX jobs_live_family_idx           ON jobs_live (job_family, experience_level);

COMMENT ON TABLE jobs_live IS 'Arbeitnow public API snapshot (one row per unique posting, no free text).';
COMMENT ON TABLE jobs_reference IS 'lukebarousse/data_jobs 2023 (Apache-2.0), cleaned. Separate population: never pool with jobs_live.';
COMMENT ON TABLE job_descriptions IS 'Cleaned description text. Restricted: not granted to coach_reader.';
COMMENT ON COLUMN jobs_reference.is_senior IS 'Derived from the author''s title classifier: never use title text as an ML feature with this label.';
