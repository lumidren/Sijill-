"""evidence requests: private links that collect answers and files from client staff

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18 01:30:00
"""
from alembic import op
import sqlalchemy as sa
import app.db


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'evidence_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('recipient', sa.String(length=128), nullable=False),
        sa.Column('recipient_contact', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('expires_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.Column('first_opened_at', app.db.UTCDateTime(timezone=True), nullable=True),
        sa.Column('submitted_at', app.db.UTCDateTime(timezone=True), nullable=True),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evidence_requests_token_hash', 'evidence_requests', ['token_hash'], unique=True)
    op.create_index('ix_evidence_requests_org_id', 'evidence_requests', ['org_id'])
    op.create_table(
        'evidence_request_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.String(length=32), nullable=False),
        sa.Column('ask', sa.Text(), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('responded_at', app.db.UTCDateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('review_note', sa.Text(), nullable=False),
        sa.Column('reviewed_at', app.db.UTCDateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['request_id'], ['evidence_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evidence_request_items_request_id', 'evidence_request_items', ['request_id'])
    op.create_index('ix_evidence_request_items_org_id', 'evidence_request_items', ['org_id'])
    op.create_table(
        'evidence_request_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_name', sa.String(length=128), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('uploaded_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.Column('evidence_file_id', sa.Integer(), nullable=True),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['evidence_request_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['evidence_file_id'], ['evidence_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evidence_request_files_item_id', 'evidence_request_files', ['item_id'])
    op.create_index('ix_evidence_request_files_org_id', 'evidence_request_files', ['org_id'])


def downgrade() -> None:
    op.drop_table('evidence_request_files')
    op.drop_table('evidence_request_items')
    op.drop_table('evidence_requests')
