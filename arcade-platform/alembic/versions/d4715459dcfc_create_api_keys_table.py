"""create_api_keys_table

Revision ID: d4715459dcfc
Revises: 9d000b314aab
Create Date: 2025-06-07 10:31:16.964223

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4715459dcfc'
down_revision: Union[str, None] = '9d000b314aab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
