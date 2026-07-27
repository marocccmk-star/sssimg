"""initial tables

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

generation_status = sa.Enum("pending", "processing", "completed", "failed",
                            name="generation_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("username", sa.String(120), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False, unique=True, index=True),
        sa.Column("image_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true(),
                  index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category_id", sa.Integer,
                  sa.ForeignKey("categories.id"), nullable=False, index=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("thumbnail_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("original_image_url", sa.String(500), nullable=False,
                  server_default=""),
        sa.Column("ai_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true(),
                  index=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0",
                  index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("templates.id"),
                  nullable=False, index=True),
        sa.Column("input_image_url", sa.String(500), nullable=False),
        sa.Column("output_image_url", sa.String(500), nullable=True),
        sa.Column("status", generation_status, nullable=False,
                  server_default="pending", index=True),
        sa.Column("provider_job_id", sa.String(200), nullable=True, index=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("generation_jobs")
    op.drop_table("templates")
    op.drop_table("categories")
    op.drop_table("users")
    generation_status.drop(op.get_bind(), checkfirst=True)
