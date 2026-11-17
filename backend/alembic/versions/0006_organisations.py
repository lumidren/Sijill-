"""organisations: several client organisations in one install

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17 22:40:00

Every organisation-owned table gains org_id (existing rows go to organisation 1, named after the
organisation profile already saved). Users gain an optional list of organisations they may open,
and the audit log records which organisation an event belongs to.
"""
from alembic import op
import sqlalchemy as sa
import app.db


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

SCOPED = [
    "answers", "evidence_files", "check_runs", "check_results", "score_snapshots", "processing_activities",
    "obligations", "reminders", "incidents", "incident_events", "tasks", "risks", "data_requests", "vendors",
    "dpias", "policies",
]


def upgrade() -> None:
    conn = op.get_bind()
    orgs = op.create_table(
        'organisations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    name = "My organisation"
    row = conn.execute(sa.text("SELECT value FROM app_settings WHERE key = 'organization'")).first()
    if row and row[0]:
        import json
        value = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        name = (value.get("name") or name)[:255]
    op.bulk_insert(orgs, [{"id": 1, "name": name, "archived": False, "created_at": app.db.utcnow()}])
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("SELECT setval(pg_get_serial_sequence('organisations', 'id'), 1)"))

    for t in SCOPED:
        op.add_column(t, sa.Column('org_id', sa.Integer(), nullable=False, server_default='1'))
        op.create_index(f'ix_{t}_org_id', t, ['org_id'])

    op.drop_index('ix_answers_requirement_id', table_name='answers')
    op.create_index('ix_answers_requirement_id', 'answers', ['requirement_id'])
    op.create_index('uq_answers_org_requirement', 'answers', ['org_id', 'requirement_id'], unique=True)

    # app_settings: unique per organisation instead of per install.
    if conn.dialect.name == "postgresql":
        op.add_column('app_settings', sa.Column('org_id', sa.Integer(), nullable=False, server_default='1'))
        op.drop_constraint('app_settings_key_key', 'app_settings', type_='unique')
    else:  # SQLite cannot drop an unnamed constraint; rebuild the (small) table.
        op.create_table(
            'app_settings_new',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('key', sa.String(length=64), nullable=False),
            sa.Column('value', sa.JSON(), nullable=False),
            sa.Column('org_id', sa.Integer(), nullable=False, server_default='1'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.execute("INSERT INTO app_settings_new (id, key, value, org_id) SELECT id, key, value, 1 FROM app_settings")
        op.drop_table('app_settings')
        op.rename_table('app_settings_new', 'app_settings')
    if conn.dialect.name == "postgresql":
        op.create_unique_constraint('uq_app_settings_org_key', 'app_settings', ['org_id', 'key'])
    else:
        op.create_index('uq_app_settings_org_key', 'app_settings', ['org_id', 'key'], unique=True)
    op.create_index('ix_app_settings_org_id', 'app_settings', ['org_id'])

    op.add_column('users', sa.Column('org_ids', sa.JSON(), nullable=True))
    op.add_column('audit_log', sa.Column('org_id', sa.Integer(), nullable=True))
    op.create_index('ix_audit_log_org_id', 'audit_log', ['org_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_log_org_id', table_name='audit_log')
    with op.batch_alter_table('audit_log') as b:
        b.drop_column('org_id')
    with op.batch_alter_table('users') as b:
        b.drop_column('org_ids')
    op.drop_index('uq_answers_org_requirement', table_name='answers')
    op.drop_index('ix_answers_requirement_id', table_name='answers')
    op.create_index('ix_answers_requirement_id', 'answers', ['requirement_id'], unique=True)
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint('uq_app_settings_org_key', 'app_settings', type_='unique')
    else:
        op.drop_index('uq_app_settings_org_key', table_name='app_settings')
    for t in SCOPED + ["app_settings"]:
        op.drop_index(f'ix_{t}_org_id', table_name=t)
        with op.batch_alter_table(t) as b:
            b.drop_column('org_id')
    op.drop_table('organisations')
