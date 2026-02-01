"""ocr jobs and uploaded documents

Revision ID: 0003_ocr_jobs
Revises: 0002_templates_versioning
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_ocr_jobs"
down_revision = "0002_templates_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_uploaded_documents_user_id", "uploaded_documents", ["user_id"], unique=False)

    op.create_table(
        "ocr_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("ocr_raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("field_suggestions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["ficha_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["uploaded_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ocr_jobs_user_id", "ocr_jobs", ["user_id"], unique=False)
    op.create_index("ix_ocr_jobs_status", "ocr_jobs", ["status"], unique=False)
    op.create_index("ix_ocr_jobs_created_at", "ocr_jobs", ["created_at"], unique=False)

    op.alter_column("ocr_jobs", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_ocr_jobs_created_at", table_name="ocr_jobs")
    op.drop_index("ix_ocr_jobs_status", table_name="ocr_jobs")
    op.drop_index("ix_ocr_jobs_user_id", table_name="ocr_jobs")
    op.drop_table("ocr_jobs")

    op.drop_index("ix_uploaded_documents_user_id", table_name="uploaded_documents")
    op.drop_table("uploaded_documents")
