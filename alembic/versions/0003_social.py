"""social layer: user_posts, post_likes, post_saves, post_comments

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("app_users.id"),
                  nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("category", sa.String(40), nullable=False, index=True),
        sa.Column("media_type", sa.String(10), nullable=False),
        sa.Column("media_url", sa.String(500), nullable=False),
        sa.Column("thumb_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("likes_count", sa.Integer, nullable=False, server_default="0",
                  index=True),
        sa.Column("saves_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("shares_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    for t in ("post_likes", "post_saves"):
        op.create_table(
            t,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("post_id", sa.Integer, sa.ForeignKey("user_posts.id"),
                      nullable=False, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("app_users.id"),
                      nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.UniqueConstraint("post_id", "user_id", name=f"uq_{t}_post_user"),
        )
    op.create_table(
        "post_comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("user_posts.id"),
                  nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("app_users.id"),
                  nullable=False, index=True),
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("post_comments")
    op.drop_table("post_saves")
    op.drop_table("post_likes")
    op.drop_table("user_posts")
