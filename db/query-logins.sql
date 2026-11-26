-- Two logins for querying the planner database by hand. Safe to run again.
--   planner_reader  SELECT only
--   planner_writer  SELECT, INSERT, UPDATE, DELETE (no DROP, ALTER or TRUNCATE)
-- No passwords here: set them afterwards (see db/README.md). Until then
-- neither login can connect over the network.
-- Run as the hermes user, which owns the tables.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'planner_reader') THEN
        CREATE ROLE planner_reader LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'planner_writer') THEN
        CREATE ROLE planner_writer LOGIN;
    END IF;
END
$$;

-- A second guard for the reader, on top of having no write privileges.
ALTER ROLE planner_reader SET default_transaction_read_only = on;
-- A forgotten open transaction would hold locks the app is waiting on.
ALTER ROLE planner_writer SET idle_in_transaction_session_timeout = '5min';

GRANT CONNECT ON DATABASE planner TO planner_reader, planner_writer;
GRANT USAGE ON SCHEMA public TO planner_reader, planner_writer;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO planner_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO planner_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO planner_writer;

-- Tables Hermes creates later get the same access.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO planner_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO planner_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO planner_writer;
