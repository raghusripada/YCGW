"""add_required_external_scopes_to_tool_definitions

Revision ID: 9d000b314aab
Revises: 4ebe78f1471e
Create Date: 2025-06-07 04:52:35.068031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d000b314aab'
down_revision: Union[str, None] = '4ebe78f1471e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
