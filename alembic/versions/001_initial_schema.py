"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-18 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. applicants
    op.create_table(
        'applicants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('age', sa.Integer(), nullable=False),
        sa.Column('employment_years', sa.Float(), nullable=False),
        sa.Column('monthly_income', sa.Float(), nullable=False),
        sa.Column('existing_monthly_debt', sa.Float(), nullable=False),
        sa.Column('credit_utilization_pct', sa.Float(), nullable=False),
        sa.Column('past_defaults', sa.Integer(), nullable=False),
        sa.Column('requested_loan_amount', sa.Float(), nullable=False),
        sa.Column('txn_volatility_score', sa.Float(), nullable=False),
        sa.Column('kyc_verified', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_applicants_created_at'), 'applicants', ['created_at'], unique=False)

    # 2. applications
    op.create_table(
        'applications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('applicant_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['applicant_id'], ['applicants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_applications_applicant_id'), 'applications', ['applicant_id'], unique=False)
    op.create_index(op.f('ix_applications_status'), 'applications', ['status'], unique=False)
    op.create_index(op.f('ix_applications_created_at'), 'applications', ['created_at'], unique=False)
    op.create_index('ix_applications_status_created_at', 'applications', ['status', 'created_at'], unique=False)

    # 3. documents
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=False),
        sa.Column('validation_status', sa.String(length=20), nullable=False),
        sa.Column('dti_ratio', sa.Float(), nullable=True),
        sa.Column('validation_errors_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_application_id'), 'documents', ['application_id'], unique=True)

    # 4. risk_assessments
    op.create_table(
        'risk_assessments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=False),
        sa.Column('default_probability', sa.Float(), nullable=False),
        sa.Column('risk_tier', sa.String(length=20), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_risk_assessments_application_id'), 'risk_assessments', ['application_id'], unique=True)
    op.create_index(op.f('ix_risk_assessments_risk_tier'), 'risk_assessments', ['risk_tier'], unique=False)

    # 5. compliance_checks
    op.create_table(
        'compliance_checks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=False),
        sa.Column('compliance_verdict', sa.String(length=20), nullable=False),
        sa.Column('has_blocking_flag', sa.Boolean(), nullable=False),
        sa.Column('flags_json', sa.Text(), nullable=True),
        sa.Column('blocking_flags_json', sa.Text(), nullable=True),
        sa.Column('retrieved_clauses_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_compliance_checks_application_id'), 'compliance_checks', ['application_id'], unique=True)
    op.create_index(op.f('ix_compliance_checks_compliance_verdict'), 'compliance_checks', ['compliance_verdict'], unique=False)
    op.create_index(op.f('ix_compliance_checks_has_blocking_flag'), 'compliance_checks', ['has_blocking_flag'], unique=False)

    # 6. decisions
    op.create_table(
        'decisions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('interest_rate_pct', sa.Float(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('explanation_source', sa.String(length=50), nullable=False),
        sa.Column('applied_clause_ids_json', sa.Text(), nullable=True),
        sa.Column('pipeline_trace_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_decisions_application_id'), 'decisions', ['application_id'], unique=True)
    op.create_index(op.f('ix_decisions_decision'), 'decisions', ['decision'], unique=False)

    # 7. audit_events
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('actor', sa.String(length=50), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_application_id'), 'audit_events', ['application_id'], unique=False)
    op.create_index(op.f('ix_audit_events_event_type'), 'audit_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_audit_events_created_at'), 'audit_events', ['created_at'], unique=False)
    op.create_index('ix_audit_events_app_created', 'audit_events', ['application_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_events')
    op.drop_table('decisions')
    op.drop_table('compliance_checks')
    op.drop_table('risk_assessments')
    op.drop_table('documents')
    op.drop_table('applications')
    op.drop_table('applicants')
