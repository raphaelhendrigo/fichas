"""templates versioning

Revision ID: 0002_templates_versioning
Revises: 0001_initial
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_templates_versioning"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ficha_templates",
        sa.Column("versao", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "ficha_templates",
        sa.Column("origem_pdf", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ficha_templates",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    try:
        op.drop_constraint("ficha_templates_nome_key", "ficha_templates", type_="unique")
    except Exception:
        pass
    op.create_unique_constraint(
        "uq_ficha_templates_nome_versao",
        "ficha_templates",
        ["nome", "versao"],
    )

    op.add_column(
        "fichas",
        sa.Column("template_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "fichas",
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'ativo'")),
    )
    op.add_column("fichas", sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("fichas", sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_fichas_status", "fichas", ["status"], unique=False)

    op.alter_column("ficha_templates", "versao", server_default=None)
    op.alter_column("ficha_templates", "is_active", server_default=None)
    op.alter_column("fichas", "template_version", server_default=None)
    op.alter_column("fichas", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_fichas_status", table_name="fichas")
    op.drop_column("fichas", "updated_by_id")
    op.drop_column("fichas", "created_by_id")
    op.drop_column("fichas", "status")
    op.drop_column("fichas", "template_version")

    op.drop_constraint("uq_ficha_templates_nome_versao", "ficha_templates", type_="unique")
    op.drop_column("ficha_templates", "is_active")
    op.drop_column("ficha_templates", "origem_pdf")
    op.drop_column("ficha_templates", "versao")
    op.create_unique_constraint("ficha_templates_nome_key", "ficha_templates", ["nome"])
