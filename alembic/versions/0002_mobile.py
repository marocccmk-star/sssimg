"""mobile app tables (sssimg): app_users, media_assets, feed_posts, gen_jobs

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(300), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("app_users.id"),
                  nullable=False, index=True),
        sa.Column("media_type", sa.String(10), nullable=False),
        sa.Column("media_url", sa.String(500), nullable=False),
        sa.Column("thumb_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "feed_posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("media_type", sa.String(10), nullable=False, server_default="image"),
        sa.Column("media_url", sa.String(500), nullable=False),
        sa.Column("thumb_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("author", sa.String(120), nullable=False, server_default="sssimg"),
        sa.Column("model_name", sa.String(60), nullable=False, server_default="gemini-omni"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true(), index=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "gen_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("app_users.id"),
                  nullable=False, index=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("model_id", sa.String(60), nullable=False, index=True),
        sa.Column("provider", sa.String(20), nullable=False, server_default="fal"),
        sa.Column("media_type", sa.String(10), nullable=False, server_default="image"),
        sa.Column("reference_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued", index=True),
        sa.Column("result_url", sa.String(500), nullable=True),
        sa.Column("provider_job_id", sa.String(300), nullable=True, index=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gen_jobs")
    op.drop_table("feed_posts")
    op.drop_table("media_assets")
    op.drop_table("app_users")
