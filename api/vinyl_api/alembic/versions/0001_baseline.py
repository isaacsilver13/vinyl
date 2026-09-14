"""baseline: create listings and plays tables

Matches api/vinyl_api/models.py as of commit b980e2b. This is the first real
Alembic migration for this service; production's existing database was
created via Base.metadata.create_all() before Alembic was wired in, so
migrate_or_stamp.py stamps existing databases to this revision instead of
re-running it.

Revision ID: 0001
Revises:
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.String(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float()),
        sa.Column("currency", sa.String(length=8)),
        sa.Column("condition", sa.String(length=64)),
        sa.Column("sleeve_condition", sa.String(length=64)),
        sa.Column("ships_from", sa.String(length=128)),
        sa.Column("seller", sa.String(length=256)),
        sa.Column("listing_url", sa.String(length=1024)),
        sa.Column("last_fetched", sa.DateTime()),
        sa.Column("price_usd", sa.Float()),
        sa.Column("ships_to_us", sa.String(length=64)),
        sa.Column("shipping_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_listings_id", "listings", ["id"])
    op.create_index("ix_listings_listing_id", "listings", ["listing_id"], unique=True)
    op.create_index("ix_listings_release_id", "listings", ["release_id"])

    op.create_table(
        "plays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("played_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=128)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_plays_id", "plays", ["id"])
    op.create_index("ix_plays_user_id", "plays", ["user_id"])
    op.create_index("ix_plays_release_id", "plays", ["release_id"])


def downgrade():
    op.drop_table("plays")
    op.drop_table("listings")
