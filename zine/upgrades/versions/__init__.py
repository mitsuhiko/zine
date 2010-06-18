"""
    zine.upgrades.versions
    ~~~~~~~~~~~~~~~~~~~~~~

    This package contains the necessary upgrade/downgrade scripts to maintain
    the database schema changes.

    This __init__ contains often used helpers for the individual upgrade
    scripts.  Do not import it outside of upgrade scripts as it replaces
    some SQLAlchemy APIs with migrate's.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from sqlalchemy.exceptions import InternalError
from sqlalchemy.orm import scoped_session, create_session, clear_mappers
from sqlalchemy.sql import text, and_, or_

import migrate
from migrate import *
from migrate import changeset, versioning

from zine.database import db


for mod in versioning, changeset:
    for key, value in mod.__dict__.iteritems():
        # Override SQLA stuff with migrate's stuff
        if key in dir(mod):
            setattr(db, key, value)
del key, mod, value

db.and_ = and_
db.or_ = or_

def drop_table(table, migrate_engine):
    if migrate_engine.url.drivername == 'postgres':
        # PSQL prefers/requires a cascade at the end
        migrate_engine.execute(text("DROP TABLE %s CASCADE" % table.name))
    else:
        table.drop(migrate_engine)

