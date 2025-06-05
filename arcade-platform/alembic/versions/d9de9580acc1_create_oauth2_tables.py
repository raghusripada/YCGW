"""create_oauth2_tables

Revision ID: d9de9580acc1
Revises: 00ddcb485c33
Create Date: 2025-06-05 12:49:07.939392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9de9580acc1'
down_revision: Union[str, None] = '00ddcb485c33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
