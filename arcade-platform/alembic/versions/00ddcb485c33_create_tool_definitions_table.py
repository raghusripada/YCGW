"""create_tool_definitions_table

Revision ID: 00ddcb485c33
Revises: b39594cebf95
Create Date: 2025-06-05 04:50:42.456826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00ddcb485c33'
down_revision: Union[str, None] = 'b39594cebf95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
