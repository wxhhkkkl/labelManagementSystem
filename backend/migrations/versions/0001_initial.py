"""初始结构：14 张表与 data-model.md 索引设计表中的全部索引。

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 建表顺序受外键约束驱动：company/user -> template -> product -> ...
# 删除时逆序。


def upgrade() -> None:
    op.create_table(
        "company",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("contact", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("status", sa.Enum("active", "disabled", name="company_status"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("hq_admin", "sub_admin", "operator", name="user_role"),
            nullable=False,
        ),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Enum("active", "disabled", name="user_status"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "template",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "status", sa.Enum("active", "disabled", name="template_status"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "template_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("paper_width_mm", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("paper_height_mm", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("elements_json", sa.JSON(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["template.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version_no", name="uq_template_version_no"),
    )
    op.create_index("ix_template_version_template_id", "template_version", ["template_id"])

    op.create_table(
        "product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("spec", sa.String(length=255), nullable=True),
        sa.Column("default_template_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Enum("active", "disabled", name="product_status"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["default_template_id"],
            ["template.id"],
            name="fk_product_default_template",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "workstation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("printer_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="workstation_status"),
            nullable=False,
        ),
        sa.Column("bound_at", sa.DateTime(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "code", name="uq_workstation_company_code"),
    )
    op.create_index("ix_workstation_last_heartbeat_at", "workstation", ["last_heartbeat_at"])

    op.create_table(
        "workstation_operator",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workstation_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["workstation_id"], ["workstation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workstation_id", "user_id", name="uq_workstation_operator"),
    )
    op.create_index(
        "ix_workstation_operator_workstation_id", "workstation_operator", ["workstation_id"]
    )
    op.create_index("ix_workstation_operator_user_id", "workstation_operator", ["user_id"])

    op.create_table(
        "import_batch",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_no", sa.String(length=32), nullable=False),
        sa.Column("code_list_filename", sa.String(length=255), nullable=False),
        sa.Column("mapping_filename", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "succeeded",
                "failed",
                "interrupted",
                name="import_batch_status",
            ),
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("error_detail_path", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_no"),
    )

    op.create_table(
        "allocation_order",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("code_count", sa.Integer(), nullable=False),
        sa.Column("code_range_from", sa.String(length=100), nullable=True),
        sa.Column("code_range_to", sa.String(length=100), nullable=True),
        sa.Column("template_version_id", sa.BigInteger(), nullable=False),
        sa.Column("allocated_by", sa.BigInteger(), nullable=False),
        sa.Column("allocated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "reclaimed", name="allocation_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["template_version.id"]),
        sa.ForeignKeyConstraint(["allocated_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
    )

    op.create_table(
        "code",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code_value", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "unallocated",
                "allocated",
                "printing",
                "printed",
                "voided",
                name="code_status",
            ),
            nullable=False,
        ),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("import_batch_id", sa.BigInteger(), nullable=False),
        sa.Column("current_allocation_order_id", sa.BigInteger(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_workstation_id", sa.BigInteger(), nullable=True),
        sa.Column("last_printed_workstation_id", sa.BigInteger(), nullable=True),
        sa.Column("print_count", sa.Integer(), nullable=False),
        sa.Column("reprint_count", sa.Integer(), nullable=False),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batch.id"]),
        sa.ForeignKeyConstraint(["current_allocation_order_id"], ["allocation_order.id"]),
        sa.ForeignKeyConstraint(["locked_workstation_id"], ["workstation.id"]),
        sa.ForeignKeyConstraint(["last_printed_workstation_id"], ["workstation.id"]),
        sa.ForeignKeyConstraint(["voided_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_value"),
    )
    op.create_index(
        "ix_code_company_product_status", "code", ["company_id", "product_id", "status"]
    )
    op.create_index("ix_code_status_batch", "code", ["status", "import_batch_id"])
    op.create_index(
        "ix_code_current_allocation_order_id", "code", ["current_allocation_order_id"]
    )

    op.create_table(
        "print_task",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "task_type", sa.Enum("reprint", name="print_task_type"), nullable=False
        ),
        sa.Column("code_id", sa.BigInteger(), nullable=False),
        sa.Column("target_workstation_id", sa.BigInteger(), nullable=False),
        sa.Column("template_version_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "claimed",
                "succeeded",
                "failed",
                "expired",
                name="print_task_status",
            ),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["code_id"], ["code.id"]),
        sa.ForeignKeyConstraint(["target_workstation_id"], ["workstation.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["template_version.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_print_task_ws_status", "print_task", ["target_workstation_id", "status"]
    )

    op.create_table(
        "print_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code_id", sa.BigInteger(), nullable=False),
        sa.Column("code_value", sa.String(length=100), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("workstation_id", sa.BigInteger(), nullable=False),
        sa.Column("operator_id", sa.BigInteger(), nullable=False),
        sa.Column("printer_name", sa.String(length=255), nullable=False),
        sa.Column("template_version_id", sa.BigInteger(), nullable=False),
        sa.Column("print_type", sa.Enum("first", "reprint", name="print_type"), nullable=False),
        sa.Column(
            "result",
            sa.Enum("succeeded", "failed", "timeout_reverted", name="print_result"),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("printed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["code_id"], ["code.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["workstation_id"], ["workstation.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["template_version.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_print_log_company_time", "print_log", ["company_id", "printed_at"])
    op.create_index("ix_print_log_ws_time", "print_log", ["workstation_id", "printed_at"])
    op.create_index(
        "ix_print_log_operator_time", "print_log", ["operator_id", "printed_at"]
    )

    op.create_table(
        "code_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "imported",
                "bound",
                "allocated",
                "reclaimed",
                "print_started",
                "printed",
                "print_failed",
                "reprint",
                "voided",
                "timeout_reverted",
                name="code_event_type",
            ),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column("workstation_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["code_id"], ["code.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["workstation_id"], ["workstation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_event_code_time", "code_event", ["code_id", "occurred_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("operator_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("workstation_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column(
            "result",
            sa.Enum("success", "denied", "failed", name="audit_result"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["operator_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["workstation_id"], ["workstation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])


def downgrade() -> None:
    for table in [
        "audit_log",
        "code_event",
        "print_log",
        "print_task",
        "code",
        "allocation_order",
        "import_batch",
        "workstation_operator",
        "workstation",
        "product",
        "template_version",
        "template",
        "user",
        "company",
    ]:
        op.drop_table(table)
