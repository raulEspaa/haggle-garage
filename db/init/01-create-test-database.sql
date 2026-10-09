-- Runs once, the first time the Postgres container starts with an empty volume.
-- Tests use their own database so they can wipe it freely (see packages/core/tests/conftest.py).
CREATE DATABASE haggle_test;
