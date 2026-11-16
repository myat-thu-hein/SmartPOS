"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-24 18:00:26.871906
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('restaurants',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=True),
    sa.Column('branch_name', sa.String(length=100), nullable=True),
    sa.Column('tax_id', sa.String(length=32), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='THB', nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='Asia/Bangkok', nullable=False),
    sa.Column('locale', sa.String(length=16), server_default='th-TH', nullable=False),
    sa.Column('tax_rate_bps', sa.Integer(), server_default='700', nullable=False),
    sa.Column('tax_label', sa.String(length=32), server_default='VAT', nullable=False),
    sa.Column('prices_include_tax', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('service_charge_bps', sa.Integer(), server_default='0', nullable=False),
    sa.Column('service_charge_taxable', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('service_charge_dine_in_only', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('max_cashier_discount_bps', sa.Integer(), server_default='1000', nullable=False),
    sa.Column('allow_negative_stock', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('loyalty_enabled', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('loyalty_spend_per_point_minor', sa.Integer(), server_default='2500', nullable=False),
    sa.Column('loyalty_point_value_minor', sa.Integer(), server_default='100', nullable=False),
    sa.Column('receipt_header', sa.Text(), nullable=True),
    sa.Column('receipt_footer', sa.Text(), nullable=True),
    sa.Column('order_number_prefix', sa.String(length=8), server_default='', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('loyalty_point_value_minor >= 0', name=op.f('ck_restaurants_loyalty_value_nonnegative')),
    sa.CheckConstraint('loyalty_spend_per_point_minor > 0', name=op.f('ck_restaurants_loyalty_spend_positive')),
    sa.CheckConstraint('max_cashier_discount_bps >= 0 AND max_cashier_discount_bps <= 10000', name=op.f('ck_restaurants_cashier_discount_range')),
    sa.CheckConstraint('service_charge_bps >= 0 AND service_charge_bps <= 5000', name=op.f('ck_restaurants_service_range')),
    sa.CheckConstraint('tax_rate_bps >= 0 AND tax_rate_bps <= 5000', name=op.f('ck_restaurants_tax_rate_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_restaurants'))
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_platform_admin', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('preferred_language', sa.String(length=8), server_default='en', nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('audit_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=True),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_logs_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_audit_logs_restaurant_id_restaurants'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_created', 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_restaurant_id'), 'audit_logs', ['restaurant_id'], unique=False)
    op.create_table('categories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_categories_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('restaurant_id', 'name', name=op.f('uq_categories_restaurant_id_name'))
    )
    op.create_index(op.f('ix_categories_restaurant_id'), 'categories', ['restaurant_id'], unique=False)
    op.create_table('customers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('loyalty_balance', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('loyalty_balance >= 0', name=op.f('ck_customers_balance_nonnegative')),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_customers_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers')),
    sa.UniqueConstraint('restaurant_id', 'phone', name=op.f('uq_customers_restaurant_id_phone'))
    )
    op.create_index(op.f('ix_customers_restaurant_id'), 'customers', ['restaurant_id'], unique=False)
    op.create_table('dining_tables',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('capacity', sa.Integer(), server_default='4', nullable=False),
    sa.Column('zone', sa.String(length=50), nullable=True),
    sa.Column('status', sa.Enum('AVAILABLE', 'OCCUPIED', 'RESERVED', 'CLEANING', name='tablestatus', native_enum=False, create_constraint=True, length=16), server_default='AVAILABLE', nullable=False),
    sa.Column('current_order_id', sa.UUID(), nullable=True),
    sa.Column('layout_x', sa.Integer(), nullable=True),
    sa.Column('layout_y', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('capacity >= 1 AND capacity <= 100', name=op.f('ck_dining_tables_capacity_range')),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_dining_tables_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dining_tables')),
    sa.UniqueConstraint('restaurant_id', 'name', name=op.f('uq_dining_tables_restaurant_id_name'))
    )
    op.create_index(op.f('ix_dining_tables_restaurant_id'), 'dining_tables', ['restaurant_id'], unique=False)
    op.create_index('ix_dining_tables_status', 'dining_tables', ['restaurant_id', 'status'], unique=False)
    op.create_table('discounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.Enum('PERCENT', 'FIXED', name='discountkind', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('value', sa.BigInteger(), nullable=False),
    sa.Column('requires_manager', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind <> 'PERCENT' OR value <= 10000", name=op.f('ck_discounts_percent_max')),
    sa.CheckConstraint('value > 0', name=op.f('ck_discounts_value_positive')),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_discounts_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_discounts')),
    sa.UniqueConstraint('restaurant_id', 'name', name=op.f('uq_discounts_restaurant_id_name'))
    )
    op.create_index(op.f('ix_discounts_restaurant_id'), 'discounts', ['restaurant_id'], unique=False)
    op.create_table('forecast_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('model_name', sa.String(length=50), nullable=False),
    sa.Column('model_version', sa.String(length=20), nullable=False),
    sa.Column('selection_strategy', sa.String(length=20), nullable=False),
    sa.Column('horizon_days', sa.Integer(), nullable=False),
    sa.Column('history_start', sa.Date(), nullable=True),
    sa.Column('history_end', sa.Date(), nullable=True),
    sa.Column('history_days', sa.Integer(), nullable=False),
    sa.Column('products_forecast', sa.Integer(), nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('uses_demo_data', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('horizon_days >= 1 AND horizon_days <= 28', name=op.f('ck_forecast_runs_horizon_range')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_forecast_runs_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_forecast_runs_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_runs'))
    )
    op.create_index('ix_forecast_runs_time', 'forecast_runs', ['restaurant_id', 'created_at'], unique=False)
    op.create_table('ingredients',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('sku', sa.String(length=64), nullable=True),
    sa.Column('base_unit', sa.Enum('g', 'ml', 'piece', name='baseunit', native_enum=False, create_constraint=True, length=8), nullable=False),
    sa.Column('current_stock', sa.Numeric(precision=14, scale=3), server_default='0', nullable=False),
    sa.Column('reorder_level', sa.Numeric(precision=14, scale=3), server_default='0', nullable=False),
    sa.Column('safety_stock', sa.Numeric(precision=14, scale=3), server_default='0', nullable=False),
    sa.Column('average_cost_minor', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('default_supplier_id', sa.UUID(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('average_cost_minor >= 0', name=op.f('ck_ingredients_cost_nonnegative')),
    sa.CheckConstraint('reorder_level >= 0', name=op.f('ck_ingredients_reorder_nonnegative')),
    sa.CheckConstraint('safety_stock >= 0', name=op.f('ck_ingredients_safety_nonnegative')),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_ingredients_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingredients')),
    sa.UniqueConstraint('restaurant_id', 'name', name=op.f('uq_ingredients_restaurant_id_name')),
    sa.UniqueConstraint('restaurant_id', 'sku', name=op.f('uq_ingredients_restaurant_id_sku'))
    )
    op.create_index(op.f('ix_ingredients_restaurant_id'), 'ingredients', ['restaurant_id'], unique=False)
    op.create_table('modifier_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('selection_type', sa.Enum('SINGLE', 'MULTIPLE', name='selectiontype', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('min_select', sa.Integer(), server_default='0', nullable=False),
    sa.Column('max_select', sa.Integer(), nullable=True),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('max_select IS NULL OR (max_select >= 1 AND max_select >= min_select)', name=op.f('ck_modifier_groups_max_valid')),
    sa.CheckConstraint('min_select >= 0', name=op.f('ck_modifier_groups_min_nonnegative')),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_modifier_groups_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_modifier_groups')),
    sa.UniqueConstraint('restaurant_id', 'name', name=op.f('uq_modifier_groups_restaurant_id_name'))
    )
    op.create_index(op.f('ix_modifier_groups_restaurant_id'), 'modifier_groups', ['restaurant_id'], unique=False)
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_password_reset_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_password_reset_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_password_reset_tokens_token_hash'))
    )
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_table('payment_methods',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.Enum('CASH', 'CARD', 'QR', 'OTHER', name='paymentmethodkind', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('is_simulated', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_payment_methods_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_methods')),
    sa.UniqueConstraint('restaurant_id', 'code', name=op.f('uq_payment_methods_restaurant_id_code'))
    )
    op.create_index(op.f('ix_payment_methods_restaurant_id'), 'payment_methods', ['restaurant_id'], unique=False)
    op.create_table('restaurant_counters',
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('value', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_restaurant_counters_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('restaurant_id', 'name', name=op.f('pk_restaurant_counters'))
    )
    op.create_table('restaurant_memberships',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('MANAGER', 'CASHIER', 'KITCHEN', name='restaurantrole', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_restaurant_memberships_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_restaurant_memberships_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_restaurant_memberships')),
    sa.UniqueConstraint('restaurant_id', 'user_id', name=op.f('uq_restaurant_memberships_restaurant_id_user_id'))
    )
    op.create_index(op.f('ix_restaurant_memberships_restaurant_id'), 'restaurant_memberships', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_restaurant_memberships_user_id'), 'restaurant_memberships', ['user_id'], unique=False)
    op.create_table('suppliers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('contact_name', sa.String(length=150), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('lead_time_days', sa.Integer(), server_default='2', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('lead_time_days >= 0 AND lead_time_days <= 365', name=op.f('ck_suppliers_lead_time_range')),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_suppliers_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suppliers')),
    sa.UniqueConstraint('restaurant_id', 'name', name=op.f('uq_suppliers_restaurant_id_name'))
    )
    op.create_index(op.f('ix_suppliers_restaurant_id'), 'suppliers', ['restaurant_id'], unique=False)
    op.create_table('user_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_sessions_token_hash'))
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table('forecast_model_metrics',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('model_name', sa.String(length=50), nullable=False),
    sa.Column('model_version', sa.String(length=20), nullable=False),
    sa.Column('evaluation_points', sa.Integer(), nullable=False),
    sa.Column('mae', sa.Float(), nullable=True),
    sa.Column('rmse', sa.Float(), nullable=True),
    sa.Column('mape', sa.Float(), nullable=True),
    sa.Column('mape_points', sa.Integer(), nullable=False),
    sa.Column('zero_actual_points', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_selected', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['forecast_runs.id'], name=op.f('fk_forecast_model_metrics_run_id_forecast_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_model_metrics'))
    )
    op.create_index(op.f('ix_forecast_model_metrics_run_id'), 'forecast_model_metrics', ['run_id'], unique=False)
    op.create_table('ingredient_units',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('unit_name', sa.String(length=20), nullable=False),
    sa.Column('factor_to_base', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.CheckConstraint('factor_to_base > 0', name=op.f('ck_ingredient_units_factor_positive')),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_ingredient_units_ingredient_id_ingredients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_ingredient_units_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingredient_units')),
    sa.UniqueConstraint('ingredient_id', 'unit_name', name=op.f('uq_ingredient_units_ingredient_id_unit_name'))
    )
    op.create_index(op.f('ix_ingredient_units_ingredient_id'), 'ingredient_units', ['ingredient_id'], unique=False)
    op.create_index(op.f('ix_ingredient_units_restaurant_id'), 'ingredient_units', ['restaurant_id'], unique=False)
    op.create_table('modifier_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('group_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('price_delta_minor', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=True),
    sa.Column('ingredient_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('ingredient_quantity IS NULL OR ingredient_quantity > 0', name=op.f('ck_modifier_options_ingredient_qty_positive')),
    sa.ForeignKeyConstraint(['group_id'], ['modifier_groups.id'], name=op.f('fk_modifier_options_group_id_modifier_groups'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_modifier_options_ingredient_id_ingredients'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_modifier_options_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_modifier_options')),
    sa.UniqueConstraint('group_id', 'name', name=op.f('uq_modifier_options_group_id_name'))
    )
    op.create_index(op.f('ix_modifier_options_group_id'), 'modifier_options', ['group_id'], unique=False)
    op.create_index(op.f('ix_modifier_options_restaurant_id'), 'modifier_options', ['restaurant_id'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('order_number', sa.Integer(), nullable=False),
    sa.Column('order_type', sa.Enum('DINE_IN', 'TAKEAWAY', name='ordertype', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'CONFIRMED', 'PREPARING', 'READY', 'COMPLETED', 'CANCELLED', name='orderstatus', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('payment_status', sa.Enum('UNPAID', 'PARTIALLY_PAID', 'PAID', 'PARTIALLY_REFUNDED', 'REFUNDED', name='paymentstatus', native_enum=False, create_constraint=True, length=24), nullable=False),
    sa.Column('table_id', sa.UUID(), nullable=True),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('discount_id', sa.UUID(), nullable=True),
    sa.Column('discount_name', sa.String(length=100), nullable=True),
    sa.Column('discount_kind', sa.Enum('PERCENT', 'FIXED', name='discountkind', native_enum=False, create_constraint=True, length=16), nullable=True),
    sa.Column('discount_value', sa.BigInteger(), nullable=True),
    sa.Column('discount_reason', sa.String(length=200), nullable=True),
    sa.Column('discount_applied_by', sa.UUID(), nullable=True),
    sa.Column('loyalty_points_redeemed', sa.Integer(), server_default='0', nullable=False),
    sa.Column('subtotal_minor', sa.BigInteger(), nullable=False),
    sa.Column('discount_minor', sa.BigInteger(), nullable=False),
    sa.Column('loyalty_discount_minor', sa.BigInteger(), nullable=False),
    sa.Column('service_charge_minor', sa.BigInteger(), nullable=False),
    sa.Column('tax_minor', sa.BigInteger(), nullable=False),
    sa.Column('total_minor', sa.BigInteger(), nullable=False),
    sa.Column('amount_paid_minor', sa.BigInteger(), nullable=False),
    sa.Column('amount_refunded_minor', sa.BigInteger(), nullable=False),
    sa.Column('tax_rate_bps', sa.Integer(), nullable=False),
    sa.Column('service_charge_bps', sa.Integer(), nullable=False),
    sa.Column('prices_include_tax', sa.Boolean(), nullable=False),
    sa.Column('stock_committed', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('preparing_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by', sa.UUID(), nullable=True),
    sa.Column('cancel_reason', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount_paid_minor >= 0', name=op.f('ck_orders_paid_nonnegative')),
    sa.CheckConstraint('amount_refunded_minor >= 0 AND amount_refunded_minor <= amount_paid_minor', name=op.f('ck_orders_refund_le_paid')),
    sa.CheckConstraint('total_minor >= 0', name=op.f('ck_orders_total_nonnegative')),
    sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], name=op.f('fk_orders_cancelled_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_orders_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_orders_customer_id_customers'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['discount_applied_by'], ['users.id'], name=op.f('fk_orders_discount_applied_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['discount_id'], ['discounts.id'], name=op.f('fk_orders_discount_id_discounts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_orders_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['table_id'], ['dining_tables.id'], name=op.f('fk_orders_table_id_dining_tables'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('restaurant_id', 'idempotency_key', name=op.f('uq_orders_restaurant_id_idempotency_key')),
    sa.UniqueConstraint('restaurant_id', 'order_number', name=op.f('uq_orders_restaurant_id_order_number'))
    )
    op.create_index('ix_orders_created_at', 'orders', ['restaurant_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_orders_customer_id'), 'orders', ['customer_id'], unique=False)
    op.create_index('ix_orders_paid_at', 'orders', ['restaurant_id', 'paid_at'], unique=False)
    op.create_index('ix_orders_status', 'orders', ['restaurant_id', 'status'], unique=False)
    op.create_index('ix_orders_table', 'orders', ['table_id'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sku', sa.String(length=64), nullable=True),
    sa.Column('image_url', sa.String(length=500), nullable=True),
    sa.Column('price_minor', sa.BigInteger(), nullable=False),
    sa.Column('is_available', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price_minor >= 0', name=op.f('ck_products_price_nonnegative')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_products_category_id_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_products_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
    sa.UniqueConstraint('restaurant_id', 'sku', name=op.f('uq_products_restaurant_id_sku'))
    )
    op.create_index(op.f('ix_products_category_id'), 'products', ['category_id'], unique=False)
    op.create_index(op.f('ix_products_restaurant_id'), 'products', ['restaurant_id'], unique=False)
    op.create_table('purchase_orders',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('po_number', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'SUBMITTED', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CANCELLED', name='purchaseorderstatus', native_enum=False, create_constraint=True, length=24), nullable=False),
    sa.Column('expected_delivery_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('estimated_total_minor', sa.BigInteger(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('submitted_by', sa.UUID(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_purchase_orders_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_purchase_orders_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], name=op.f('fk_purchase_orders_submitted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_purchase_orders_supplier_id_suppliers'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_orders')),
    sa.UniqueConstraint('restaurant_id', 'po_number', name=op.f('uq_purchase_orders_restaurant_id_po_number'))
    )
    op.create_index('ix_purchase_orders_status', 'purchase_orders', ['restaurant_id', 'status'], unique=False)
    op.create_index(op.f('ix_purchase_orders_supplier_id'), 'purchase_orders', ['supplier_id'], unique=False)
    op.create_table('supplier_ingredients',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('supplier_id', sa.UUID(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('supplier_sku', sa.String(length=64), nullable=True),
    sa.Column('unit_cost_minor', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('min_order_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('lead_time_days', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('min_order_quantity IS NULL OR min_order_quantity > 0', name=op.f('ck_supplier_ingredients_moq_positive')),
    sa.CheckConstraint('unit_cost_minor IS NULL OR unit_cost_minor >= 0', name=op.f('ck_supplier_ingredients_cost_nonnegative')),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_supplier_ingredients_ingredient_id_ingredients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_supplier_ingredients_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_supplier_ingredients_supplier_id_suppliers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_supplier_ingredients')),
    sa.UniqueConstraint('supplier_id', 'ingredient_id', name=op.f('uq_supplier_ingredients_supplier_id_ingredient_id'))
    )
    op.create_index(op.f('ix_supplier_ingredients_ingredient_id'), 'supplier_ingredients', ['ingredient_id'], unique=False)
    op.create_index(op.f('ix_supplier_ingredients_restaurant_id'), 'supplier_ingredients', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_supplier_ingredients_supplier_id'), 'supplier_ingredients', ['supplier_id'], unique=False)
    op.create_table('forecasts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('target_type', sa.Enum('PRODUCT', 'INGREDIENT', name='forecasttarget', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('ingredient_id', sa.UUID(), nullable=True),
    sa.Column('forecast_date', sa.Date(), nullable=False),
    sa.Column('horizon_day', sa.Integer(), nullable=False),
    sa.Column('predicted_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('actual_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('model_name', sa.String(length=50), nullable=False),
    sa.Column('model_version', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(product_id IS NOT NULL) <> (ingredient_id IS NOT NULL)', name=op.f('ck_forecasts_one_target')),
    sa.CheckConstraint('predicted_quantity >= 0', name=op.f('ck_forecasts_prediction_nonnegative')),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_forecasts_ingredient_id_ingredients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_forecasts_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_forecasts_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['forecast_runs.id'], name=op.f('fk_forecasts_run_id_forecast_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecasts'))
    )
    op.create_index('ix_forecasts_ingredient', 'forecasts', ['ingredient_id', 'forecast_date'], unique=False)
    op.create_index('ix_forecasts_product', 'forecasts', ['product_id', 'forecast_date'], unique=False)
    op.create_index(op.f('ix_forecasts_run_id'), 'forecasts', ['run_id'], unique=False)
    op.create_index('ix_forecasts_target_date', 'forecasts', ['restaurant_id', 'target_type', 'forecast_date'], unique=False)
    op.create_table('loyalty_transactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('order_id', sa.UUID(), nullable=True),
    sa.Column('transaction_type', sa.Enum('EARN', 'REDEEM', 'ADJUST', 'REVERSAL', name='loyaltytransactiontype', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=True),
    sa.Column('related_transaction_id', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('points <> 0', name=op.f('ck_loyalty_transactions_points_nonzero')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_loyalty_transactions_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_loyalty_transactions_customer_id_customers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_loyalty_transactions_order_id_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['related_transaction_id'], ['loyalty_transactions.id'], name=op.f('fk_loyalty_transactions_related_transaction_id_loyalty_transactions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_loyalty_transactions_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_loyalty_transactions'))
    )
    op.create_index('ix_loyalty_customer_time', 'loyalty_transactions', ['customer_id', 'created_at'], unique=False)
    op.create_index('uq_loyalty_order_earn_redeem', 'loyalty_transactions', ['order_id', 'transaction_type'], unique=True, postgresql_where=sa.text("transaction_type IN ('EARN', 'REDEEM') AND order_id IS NOT NULL"))
    op.create_table('payments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('payment_method_id', sa.UUID(), nullable=True),
    sa.Column('method_code', sa.String(length=32), nullable=False),
    sa.Column('method_name', sa.String(length=100), nullable=False),
    sa.Column('method_kind', sa.Enum('CASH', 'CARD', 'QR', 'OTHER', name='paymentmethodkind', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('is_simulated', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('RECORDED', 'PROVIDER_CONFIRMED', name='paymentrecordstatus', native_enum=False, create_constraint=True, length=24), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('amount_tendered_minor', sa.BigInteger(), nullable=True),
    sa.Column('change_minor', sa.BigInteger(), nullable=False),
    sa.Column('refunded_minor', sa.BigInteger(), nullable=False),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('idempotency_key', sa.String(length=100), nullable=True),
    sa.Column('recorded_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount_minor > 0', name=op.f('ck_payments_amount_positive')),
    sa.CheckConstraint('refunded_minor >= 0 AND refunded_minor <= amount_minor', name=op.f('ck_payments_refund_le_amount')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payments_order_id_orders'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id'], name=op.f('fk_payments_payment_method_id_payment_methods'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], name=op.f('fk_payments_recorded_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_payments_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('restaurant_id', 'idempotency_key', name=op.f('uq_payments_restaurant_id_idempotency_key'))
    )
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=False)
    op.create_index('ix_payments_time', 'payments', ['restaurant_id', 'created_at'], unique=False)
    op.create_table('product_modifier_groups',
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('modifier_group_id', sa.UUID(), nullable=False),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['modifier_group_id'], ['modifier_groups.id'], name=op.f('fk_product_modifier_groups_modifier_group_id_modifier_groups'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_modifier_groups_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('product_id', 'modifier_group_id', name=op.f('pk_product_modifier_groups'))
    )
    op.create_table('purchase_order_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('purchase_order_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('quantity_ordered', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('quantity_received', sa.Numeric(precision=14, scale=3), server_default='0', nullable=False),
    sa.Column('input_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('input_unit', sa.String(length=20), nullable=False),
    sa.Column('unit_cost_minor', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.CheckConstraint('quantity_ordered > 0', name=op.f('ck_purchase_order_items_ordered_positive')),
    sa.CheckConstraint('quantity_received >= 0 AND quantity_received <= quantity_ordered', name=op.f('ck_purchase_order_items_received_range')),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_purchase_order_items_ingredient_id_ingredients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_purchase_order_items_purchase_order_id_purchase_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_order_items')),
    sa.UniqueConstraint('purchase_order_id', 'ingredient_id', name=op.f('uq_purchase_order_items_purchase_order_id_ingredient_id'))
    )
    op.create_index(op.f('ix_purchase_order_items_purchase_order_id'), 'purchase_order_items', ['purchase_order_id'], unique=False)
    op.create_table('purchase_order_receipts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('purchase_order_id', sa.UUID(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('total_cost_minor', sa.BigInteger(), nullable=False),
    sa.Column('received_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_purchase_order_receipts_purchase_order_id_purchase_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['received_by'], ['users.id'], name=op.f('fk_purchase_order_receipts_received_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_purchase_order_receipts_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_order_receipts')),
    sa.UniqueConstraint('restaurant_id', 'idempotency_key', name=op.f('uq_purchase_order_receipts_restaurant_id_idempotency_key'))
    )
    op.create_index(op.f('ix_purchase_order_receipts_purchase_order_id'), 'purchase_order_receipts', ['purchase_order_id'], unique=False)
    op.create_table('recipes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_recipes_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_recipes_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_recipes_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recipes')),
    sa.UniqueConstraint('product_id', 'version', name=op.f('uq_recipes_product_id_version'))
    )
    op.create_index(op.f('ix_recipes_product_id'), 'recipes', ['product_id'], unique=False)
    op.create_index(op.f('ix_recipes_restaurant_id'), 'recipes', ['restaurant_id'], unique=False)
    op.create_index('uq_recipes_one_active_per_product', 'recipes', ['product_id'], unique=True, postgresql_where=sa.text('is_active'))
    op.create_table('reorder_recommendations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('forecast_run_id', sa.UUID(), nullable=True),
    sa.Column('supplier_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'MODIFIED', 'REJECTED', 'COMPLETED', name='recommendationstatus', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('current_stock', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('forecast_demand', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('safety_stock', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('incoming_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('lead_time_days', sa.Integer(), nullable=False),
    sa.Column('coverage_days', sa.Integer(), nullable=False),
    sa.Column('raw_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('suggested_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('approved_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('min_order_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('calculation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_note', sa.String(length=500), nullable=True),
    sa.Column('purchase_order_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('approved_quantity IS NULL OR approved_quantity >= 0', name=op.f('ck_reorder_recommendations_approved_nonnegative')),
    sa.CheckConstraint('suggested_quantity >= 0', name=op.f('ck_reorder_recommendations_suggested_nonnegative')),
    sa.ForeignKeyConstraint(['forecast_run_id'], ['forecast_runs.id'], name=op.f('fk_reorder_recommendations_forecast_run_id_forecast_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_reorder_recommendations_ingredient_id_ingredients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_reorder_recommendations_purchase_order_id_purchase_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_reorder_recommendations_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_reorder_recommendations_reviewed_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_reorder_recommendations_supplier_id_suppliers'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reorder_recommendations'))
    )
    op.create_index('ix_recommendations_status', 'reorder_recommendations', ['restaurant_id', 'status'], unique=False)
    op.create_index(op.f('ix_reorder_recommendations_ingredient_id'), 'reorder_recommendations', ['ingredient_id'], unique=False)
    op.create_table('inventory_movements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('movement_type', sa.Enum('OPENING', 'RECEIPT', 'PURCHASE_RECEIPT', 'ISSUE', 'ADJUSTMENT', 'WASTE', 'SALE', 'SALE_REVERSAL', name='movementtype', native_enum=False, create_constraint=True, length=24), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('balance_after', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('unit_cost_minor', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('input_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.Column('input_unit', sa.String(length=20), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('order_id', sa.UUID(), nullable=True),
    sa.Column('purchase_order_id', sa.UUID(), nullable=True),
    sa.Column('purchase_order_receipt_id', sa.UUID(), nullable=True),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity <> 0', name=op.f('ck_inventory_movements_quantity_nonzero')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_inventory_movements_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_inventory_movements_ingredient_id_ingredients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_inventory_movements_order_id_orders'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_inventory_movements_purchase_order_id_purchase_orders'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_order_receipt_id'], ['purchase_order_receipts.id'], name=op.f('fk_inventory_movements_purchase_order_receipt_id_purchase_order_receipts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_inventory_movements_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_movements'))
    )
    op.create_index('ix_inventory_movements_ingredient_time', 'inventory_movements', ['restaurant_id', 'ingredient_id', 'created_at'], unique=False)
    op.create_index('ix_inventory_movements_order', 'inventory_movements', ['order_id'], unique=False)
    op.create_index('ix_inventory_movements_po', 'inventory_movements', ['purchase_order_id'], unique=False)
    op.create_index('ix_inventory_movements_type_time', 'inventory_movements', ['restaurant_id', 'movement_type', 'created_at'], unique=False)
    op.create_table('order_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('product_name', sa.String(length=150), nullable=False),
    sa.Column('product_sku', sa.String(length=64), nullable=True),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('category_name', sa.String(length=100), nullable=True),
    sa.Column('base_price_minor', sa.BigInteger(), nullable=False),
    sa.Column('unit_price_minor', sa.BigInteger(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('line_total_minor', sa.BigInteger(), nullable=False),
    sa.Column('notes', sa.String(length=300), nullable=True),
    sa.Column('recipe_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity > 0 AND quantity <= 999', name=op.f('ck_order_items_quantity_range')),
    sa.CheckConstraint('unit_price_minor >= 0', name=op.f('ck_order_items_unit_price_nonnegative')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_order_items_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_order_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_order_items_recipe_id_recipes'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_order_items_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_product_id'), 'order_items', ['product_id'], unique=False)
    op.create_table('purchase_order_receipt_lines',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('receipt_id', sa.UUID(), nullable=False),
    sa.Column('purchase_order_item_id', sa.UUID(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('unit_cost_minor', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_purchase_order_receipt_lines_quantity_positive')),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_purchase_order_receipt_lines_ingredient_id_ingredients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_order_item_id'], ['purchase_order_items.id'], name=op.f('fk_purchase_order_receipt_lines_purchase_order_item_id_purchase_order_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['receipt_id'], ['purchase_order_receipts.id'], name=op.f('fk_purchase_order_receipt_lines_receipt_id_purchase_order_receipts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_order_receipt_lines'))
    )
    op.create_index(op.f('ix_purchase_order_receipt_lines_receipt_id'), 'purchase_order_receipt_lines', ['receipt_id'], unique=False)
    op.create_table('recipe_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('recipe_id', sa.UUID(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('input_quantity', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('input_unit', sa.String(length=20), nullable=False),
    sa.Column('waste_factor', sa.Numeric(precision=5, scale=4), server_default='0', nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_recipe_items_quantity_positive')),
    sa.CheckConstraint('waste_factor >= 0 AND waste_factor < 1', name=op.f('ck_recipe_items_waste_range')),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_recipe_items_ingredient_id_ingredients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_recipe_items_recipe_id_recipes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recipe_items')),
    sa.UniqueConstraint('recipe_id', 'ingredient_id', name=op.f('uq_recipe_items_recipe_id_ingredient_id'))
    )
    op.create_index(op.f('ix_recipe_items_ingredient_id'), 'recipe_items', ['ingredient_id'], unique=False)
    op.create_index(op.f('ix_recipe_items_recipe_id'), 'recipe_items', ['recipe_id'], unique=False)
    op.create_table('refunds',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('restaurant_id', sa.UUID(), nullable=False),
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('payment_id', sa.UUID(), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=True),
    sa.Column('recorded_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount_minor > 0', name=op.f('ck_refunds_amount_positive')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_refunds_order_id_orders'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name=op.f('fk_refunds_payment_id_payments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], name=op.f('fk_refunds_recorded_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], name=op.f('fk_refunds_restaurant_id_restaurants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refunds')),
    sa.UniqueConstraint('restaurant_id', 'idempotency_key', name=op.f('uq_refunds_restaurant_id_idempotency_key'))
    )
    op.create_index(op.f('ix_refunds_order_id'), 'refunds', ['order_id'], unique=False)
    op.create_index('ix_refunds_time', 'refunds', ['restaurant_id', 'created_at'], unique=False)
    op.create_table('order_item_modifiers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('order_item_id', sa.UUID(), nullable=False),
    sa.Column('modifier_option_id', sa.UUID(), nullable=True),
    sa.Column('group_name', sa.String(length=100), nullable=False),
    sa.Column('option_name', sa.String(length=100), nullable=False),
    sa.Column('price_delta_minor', sa.BigInteger(), nullable=False),
    sa.Column('ingredient_id', sa.UUID(), nullable=True),
    sa.Column('ingredient_quantity', sa.Numeric(precision=14, scale=3), nullable=True),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_order_item_modifiers_ingredient_id_ingredients'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['modifier_option_id'], ['modifier_options.id'], name=op.f('fk_order_item_modifiers_modifier_option_id_modifier_options'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], name=op.f('fk_order_item_modifiers_order_item_id_order_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_item_modifiers'))
    )
    op.create_index(op.f('ix_order_item_modifiers_order_item_id'), 'order_item_modifiers', ['order_item_id'], unique=False)
    # Circular references are added once both tables exist.
    op.create_foreign_key('fk_dining_tables_current_order', 'dining_tables', 'orders',
                          ['current_order_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_ingredients_default_supplier', 'ingredients', 'suppliers',
                          ['default_supplier_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_ingredients_default_supplier', 'ingredients', type_='foreignkey')
    op.drop_constraint('fk_dining_tables_current_order', 'dining_tables', type_='foreignkey')
    op.drop_index(op.f('ix_order_item_modifiers_order_item_id'), table_name='order_item_modifiers')
    op.drop_table('order_item_modifiers')
    op.drop_index('ix_refunds_time', table_name='refunds')
    op.drop_index(op.f('ix_refunds_order_id'), table_name='refunds')
    op.drop_table('refunds')
    op.drop_index(op.f('ix_recipe_items_recipe_id'), table_name='recipe_items')
    op.drop_index(op.f('ix_recipe_items_ingredient_id'), table_name='recipe_items')
    op.drop_table('recipe_items')
    op.drop_index(op.f('ix_purchase_order_receipt_lines_receipt_id'), table_name='purchase_order_receipt_lines')
    op.drop_table('purchase_order_receipt_lines')
    op.drop_index(op.f('ix_order_items_product_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index('ix_inventory_movements_type_time', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_po', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_order', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_ingredient_time', table_name='inventory_movements')
    op.drop_table('inventory_movements')
    op.drop_index(op.f('ix_reorder_recommendations_ingredient_id'), table_name='reorder_recommendations')
    op.drop_index('ix_recommendations_status', table_name='reorder_recommendations')
    op.drop_table('reorder_recommendations')
    op.drop_index('uq_recipes_one_active_per_product', table_name='recipes', postgresql_where=sa.text('is_active'))
    op.drop_index(op.f('ix_recipes_restaurant_id'), table_name='recipes')
    op.drop_index(op.f('ix_recipes_product_id'), table_name='recipes')
    op.drop_table('recipes')
    op.drop_index(op.f('ix_purchase_order_receipts_purchase_order_id'), table_name='purchase_order_receipts')
    op.drop_table('purchase_order_receipts')
    op.drop_index(op.f('ix_purchase_order_items_purchase_order_id'), table_name='purchase_order_items')
    op.drop_table('purchase_order_items')
    op.drop_table('product_modifier_groups')
    op.drop_index('ix_payments_time', table_name='payments')
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index('uq_loyalty_order_earn_redeem', table_name='loyalty_transactions', postgresql_where=sa.text("transaction_type IN ('EARN', 'REDEEM') AND order_id IS NOT NULL"))
    op.drop_index('ix_loyalty_customer_time', table_name='loyalty_transactions')
    op.drop_table('loyalty_transactions')
    op.drop_index('ix_forecasts_target_date', table_name='forecasts')
    op.drop_index(op.f('ix_forecasts_run_id'), table_name='forecasts')
    op.drop_index('ix_forecasts_product', table_name='forecasts')
    op.drop_index('ix_forecasts_ingredient', table_name='forecasts')
    op.drop_table('forecasts')
    op.drop_index(op.f('ix_supplier_ingredients_supplier_id'), table_name='supplier_ingredients')
    op.drop_index(op.f('ix_supplier_ingredients_restaurant_id'), table_name='supplier_ingredients')
    op.drop_index(op.f('ix_supplier_ingredients_ingredient_id'), table_name='supplier_ingredients')
    op.drop_table('supplier_ingredients')
    op.drop_index(op.f('ix_purchase_orders_supplier_id'), table_name='purchase_orders')
    op.drop_index('ix_purchase_orders_status', table_name='purchase_orders')
    op.drop_table('purchase_orders')
    op.drop_index(op.f('ix_products_restaurant_id'), table_name='products')
    op.drop_index(op.f('ix_products_category_id'), table_name='products')
    op.drop_table('products')
    op.drop_index('ix_orders_table', table_name='orders')
    op.drop_index('ix_orders_status', table_name='orders')
    op.drop_index('ix_orders_paid_at', table_name='orders')
    op.drop_index(op.f('ix_orders_customer_id'), table_name='orders')
    op.drop_index('ix_orders_created_at', table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_modifier_options_restaurant_id'), table_name='modifier_options')
    op.drop_index(op.f('ix_modifier_options_group_id'), table_name='modifier_options')
    op.drop_table('modifier_options')
    op.drop_index(op.f('ix_ingredient_units_restaurant_id'), table_name='ingredient_units')
    op.drop_index(op.f('ix_ingredient_units_ingredient_id'), table_name='ingredient_units')
    op.drop_table('ingredient_units')
    op.drop_index(op.f('ix_forecast_model_metrics_run_id'), table_name='forecast_model_metrics')
    op.drop_table('forecast_model_metrics')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index(op.f('ix_suppliers_restaurant_id'), table_name='suppliers')
    op.drop_table('suppliers')
    op.drop_index(op.f('ix_restaurant_memberships_user_id'), table_name='restaurant_memberships')
    op.drop_index(op.f('ix_restaurant_memberships_restaurant_id'), table_name='restaurant_memberships')
    op.drop_table('restaurant_memberships')
    op.drop_table('restaurant_counters')
    op.drop_index(op.f('ix_payment_methods_restaurant_id'), table_name='payment_methods')
    op.drop_table('payment_methods')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_index(op.f('ix_modifier_groups_restaurant_id'), table_name='modifier_groups')
    op.drop_table('modifier_groups')
    op.drop_index(op.f('ix_ingredients_restaurant_id'), table_name='ingredients')
    op.drop_table('ingredients')
    op.drop_index('ix_forecast_runs_time', table_name='forecast_runs')
    op.drop_table('forecast_runs')
    op.drop_index(op.f('ix_discounts_restaurant_id'), table_name='discounts')
    op.drop_table('discounts')
    op.drop_index('ix_dining_tables_status', table_name='dining_tables')
    op.drop_index(op.f('ix_dining_tables_restaurant_id'), table_name='dining_tables')
    op.drop_table('dining_tables')
    op.drop_index(op.f('ix_customers_restaurant_id'), table_name='customers')
    op.drop_table('customers')
    op.drop_index(op.f('ix_categories_restaurant_id'), table_name='categories')
    op.drop_table('categories')
    op.drop_index(op.f('ix_audit_logs_restaurant_id'), table_name='audit_logs')
    op.drop_index('ix_audit_logs_created', table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('restaurants')
