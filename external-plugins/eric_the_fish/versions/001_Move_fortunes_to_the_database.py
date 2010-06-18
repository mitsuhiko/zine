"""Move fortunes to the database"""
from zine.upgrades.versions import *

metadata = db.MetaData()

# Define tables here
fortunes = db.Table('eric_the_fish_fortunes', metadata,
    db.Column('id', db.Integer, primary_key=True),
    db.Column('text', db.Text, nullable=False)
)


# Define the objects here
class Fortune(object):
    query = db.query_property(db.Query)
    def __init__(self, text):
        self.text = text


def map_tables(mapper):
    clear_mappers()
    # Map tables to the python objects here
    mapper(Fortune, fortunes)


def upgrade(migrate_engine):
    # Upgrade operations go here. Don't create your own engine
    # bind migrate_engine to your metadata
    session = scoped_session(lambda: create_session(migrate_engine,
                                                    autoflush=True,
                                                    autocommit=False))
    map_tables(db.basic_mapper)
    metadata.bind = migrate_engine
    if not fortunes.exists():
        fortunes.create(migrate_engine)

    from zine.plugins.eric_the_fish.fortunes import FORTUNES

    yield '<p>Adding fortunes to the database:</p>\n'
    yield '<ul>'
    for fortune in FORTUNES:
        yield '  <li>%s</li>\n' % fortune
        session.add(Fortune(fortune))
    session.commit()
    yield '</ul>\n'


def downgrade(migrate_engine):
    # Operations to reverse the above upgrade go here.
    session = scoped_session(lambda: create_session(migrate_engine,
                                                    autoflush=True,
                                                    autocommit=False))
    map_tables(db.basic_mapper)
    yield '<p>Removing the fortunes from the database</p>\n'

    metadata.bind = migrate_engine

    if fortunes.exists():
        fortunes.drop(migrate_engine)
