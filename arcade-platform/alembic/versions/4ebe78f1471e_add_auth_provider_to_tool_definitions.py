"""add_auth_provider_to_tool_definitions

Revision ID: 4ebe78f1471e
Revises: b84c646887f5
Create Date: 2025-06-05 18:02:16.994821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ebe78f1471e'
down_revision: Union[str, None] = 'b84c646887f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
