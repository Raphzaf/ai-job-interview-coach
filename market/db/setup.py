"""Create roles, the database, the schema, views and privileges.

    python -m market.db.setup

Requires DATABASE_ADMIN_URL, COACH_OWNER_PASSWORD, COACH_READER_PASSWORD.
Idempotent: roles/database are created if missing (passwords updated), the
schema is rebuilt (tables dropped and recreated, so run `market.db.load` after).
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from market.db.config import DB_NAME, OWNER_ROLE, READER_ROLE, require_env

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def run_sql_file(conn: psycopg.Connection, name: str) -> None:
    conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def ensure_role(conn: psycopg.Connection, role: str, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    verb = sql.SQL("ALTER ROLE") if exists else sql.SQL("CREATE ROLE")
    # Passwords cannot be bind parameters in DDL: sql.Literal escapes them safely.
    conn.execute(sql.SQL("{} {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
        verb, sql.Identifier(role), sql.Literal(password)))


def setup() -> None:
    admin_url = require_env("DATABASE_ADMIN_URL")
    with psycopg.connect(admin_url, autocommit=True) as admin:
        ensure_role(admin, OWNER_ROLE, require_env("COACH_OWNER_PASSWORD"))
        ensure_role(admin, READER_ROLE, require_env("COACH_READER_PASSWORD"))
        # The reader can never write, even by mistake, and cannot run away with the server.
        admin.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(READER_ROLE)))
        admin.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '60s'").format(sql.Identifier(READER_ROLE)))
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)).fetchone():
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(DB_NAME), sql.Identifier(OWNER_ROLE)))

    db_admin_url = make_conninfo(admin_url, dbname=DB_NAME)
    with psycopg.connect(db_admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DB_NAME)))
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(DB_NAME), sql.Identifier(OWNER_ROLE), sql.Identifier(READER_ROLE)))
        admin.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        admin.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS market AUTHORIZATION {}").format(sql.Identifier(OWNER_ROLE)))

    params = conninfo_to_dict(admin_url)
    owner_url = make_conninfo(admin_url, dbname=DB_NAME, user=OWNER_ROLE, password=require_env("COACH_OWNER_PASSWORD"))
    with psycopg.connect(owner_url) as owner:
        for name in ("schema.sql", "views.sql", "security.sql"):
            run_sql_file(owner, name)
    print(f"Database {DB_NAME} ready on {params.get('host')}:{params.get('port')} "
          f"(roles {OWNER_ROLE}, {READER_ROLE}); now run: python -m market.db.load")


if __name__ == "__main__":
    setup()
