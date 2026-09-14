"""Bring the database schema to Alembic 'head' before the app starts.

Handles two cases without any manual intervention:
  - A brand-new database (no tables yet): runs `alembic upgrade head` normally.
  - An existing database created by the old `Base.metadata.create_all()` path
    (has *all* of the `listings`/`plays` tables but no `alembic_version` table,
    since Alembic wasn't wired in yet): stamps it to the baseline revision
    (the migration that models this pre-Alembic schema -- NOT "head") instead
    of re-running `CREATE TABLE` on tables that already exist, then continues
    on to `alembic upgrade head` in the same run so any migrations added after
    the baseline (e.g. an eventual 0002) still get applied immediately rather
    than silently skipped. Stamping straight to "head" would mark a later
    migration as already applied without ever running its DDL.

  A partially-pre-existing DB (only one of `listings`/`plays` present -- which
  in practice would mean a prior create_all() run was interrupted mid-way) is
  deliberately NOT treated as "pre-existing, stamp only": it falls through to
  a normal `alembic upgrade head`, which will attempt to (re)create the
  missing table(s) and fail loudly on the ones that already exist. That's the
  correct behavior here -- this state means the database is already in an
  inconsistent, hand-fixable condition, and failing loudly beats silently
  stamping it as "fully migrated" while a table is still missing.
"""
import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

_HERE = os.path.dirname(os.path.abspath(__file__))

# Tables that must ALL be present for a DB to count as a pre-existing,
# create_all()-created database. A set *intersection* here would treat a
# database with only one of these tables as "fully pre-existing" and stamp it
# without ever creating the missing table -- hence `issubset`, not `&`.
_PRE_ALEMBIC_TABLES = {"listings", "plays"}


def _baseline_revision(cfg: Config) -> str:
    """The root (no down_revision) revision of the migration history.

    This is "the baseline" referenced throughout this module: the migration
    that models the schema produced by the old `Base.metadata.create_all()`
    path. Looked up dynamically (rather than hardcoding "0001") so this stays
    correct if the baseline migration is ever renamed.
    """
    script_dir = ScriptDirectory.from_config(cfg)
    bases = script_dir.get_bases()
    if len(bases) != 1:
        raise RuntimeError(
            f"Expected exactly one baseline Alembic revision, found {bases!r}. "
            "migrate_or_stamp.py assumes a single linear migration history; "
            "if a second branch was intentionally added, this needs a manual "
            "decision about which revision pre-Alembic databases should stamp to."
        )
    return bases[0]


def main():
    db_url = os.environ.get("VINYL_API_DATABASE_URL", "sqlite:///./vinyl_api_dev.db")
    engine = create_engine(db_url)
    try:
        existing_tables = set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            current_rev = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()

    cfg = Config(os.path.join(_HERE, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    # alembic.ini's `script_location` is a relative path resolved against the
    # *current working directory* at run time, not against alembic.ini's own
    # location -- so leaving it as-is would make this script's behavior
    # depend on the caller's cwd. Override it here with an absolute path
    # built from this file's own location so `python migrate_or_stamp.py`
    # (or `python /app/migrate_or_stamp.py` from anywhere) behaves the same
    # regardless of invocation directory.
    cfg.set_main_option("script_location", os.path.join(_HERE, "vinyl_api", "alembic"))

    pre_alembic_db = current_rev is None and _PRE_ALEMBIC_TABLES.issubset(existing_tables)
    if pre_alembic_db:
        baseline = _baseline_revision(cfg)
        print(f"migrate_or_stamp: existing pre-Alembic database detected, stamping to baseline revision {baseline!r}")
        command.stamp(cfg, baseline)

    print("migrate_or_stamp: running alembic upgrade head")
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
