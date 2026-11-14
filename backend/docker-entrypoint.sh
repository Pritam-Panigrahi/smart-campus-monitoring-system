#!/bin/sh
set -eu

# Alembic upgrades an existing database in place; it never recreates or seeds
# the mounted SQLite file. This must complete before the application opens it.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
