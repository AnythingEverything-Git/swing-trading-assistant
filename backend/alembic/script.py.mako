"""Generic script template for Alembic."""
from alembic import op
import sqlalchemy as sa

{% for rev in revisions -%}
# revision identifiers, used by Alembic.
revision = {{ repr(revision) }}
down_revision = {{ repr(down_revision) }}
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
{% endfor %}
