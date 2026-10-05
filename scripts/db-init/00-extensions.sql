-- Executed once, on an empty data directory, by the postgres entrypoint.
--
-- The application migrations own the schema; this script only prepares the
-- database that Alembic will migrate: the pg_trgm/pgcrypto extensions the
-- search features rely on, and the C collation that keeps `similarity()`
-- consistent with the application (see docs/DECISIONS.md).
--
-- Running it again is harmless.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- The connection collation stays C on purpose; Arabic matching is done in
-- Python (app.utils.arabic) so that folding rules live in one place.