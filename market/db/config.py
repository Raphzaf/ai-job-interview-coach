"""Database connection settings, read from environment variables only.

DATABASE_ADMIN_URL   superuser connection, used ONLY by `market.db.setup`
DATABASE_OWNER_URL   coach_owner: DDL + loading (`market.db.load`)
DATABASE_URL         coach_reader: read-only, used by analyses, exports and the app
COACH_OWNER_PASSWORD / COACH_READER_PASSWORD   passwords given to the roles by setup
"""

from __future__ import annotations

import os

import psycopg

DB_NAME = "job_market"
SCHEMA = "market"
OWNER_ROLE = "coach_owner"
READER_ROLE = "coach_reader"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set (see .env.example).")
    return value


def connect(env_var: str = "DATABASE_URL", **kwargs) -> psycopg.Connection:
    return psycopg.connect(require_env(env_var), **kwargs)
