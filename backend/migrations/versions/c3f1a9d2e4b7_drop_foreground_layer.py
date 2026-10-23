"""drop foreground layer

Revision ID: c3f1a9d2e4b7
Revises: 689f31012583
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3f1a9d2e4b7'
down_revision: Union[str, Sequence[str], None] = '689f31012583'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The foreground layer is gone: its objects go back to the tokens' layer."""
    op.execute("UPDATE map_objects SET layer = 'objects' WHERE layer = 'foreground'")


def downgrade() -> None:
    """Nothing to restore: which objects were in the foreground is not kept."""
