-- Privileges (run by the owner after schema.sql/views.sql; re-run after every rebuild).
-- coach_reader: read-only access to tables and views, EXCEPT the free-text
-- descriptions (they may contain recruiters' contact details).
SET search_path = market;
GRANT USAGE ON SCHEMA market TO coach_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA market TO coach_reader;   -- includes views
REVOKE ALL ON market.job_descriptions FROM coach_reader;
