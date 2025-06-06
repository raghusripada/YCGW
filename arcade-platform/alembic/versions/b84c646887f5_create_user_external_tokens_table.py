"""create_user_external_tokens_table

Revision ID: b84c646887f5
Revises: d9de9580acc1
Create Date: 2025-06-05 17:54:07.876585

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b84c646887f5'
down_revision: Union[str, None] = 'd9de9580acc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
