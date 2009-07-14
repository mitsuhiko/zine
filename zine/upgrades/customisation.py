"""
    zine.upgrades.customisation
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This package customises several sqlalchemy-migrate classes in order for us
    to do our job.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

import logging
import warnings
from os import listdir
from os.path import dirname, join

from migrate.versioning import api, base, exceptions
from migrate.versioning.repository import Repository as MigrateRepository
from migrate.versioning.script.py import PythonScript as MigratePythonScript
from migrate.versioning.schema import (ControlledSchema as
                                       MigrateControlledSchema)
from migrate.versioning.version import Version as MigrateVersion
from migrate.versioning.version import Collection as MigrateCollection


MIGRATE_SCRIPTS_PATH = join(dirname(__file__), 'versions')

log = logging.getLogger(__name__)

class PythonScript(MigratePythonScript):

    @classmethod
    def create(cls, path, **opts):
        """Create an empty migration script at specified path

        :returns: :class:`PythonScript instance <migrate.versioning.script.py.PythonScript>`"""
        cls.require_notfound(path)

        NEW_SCRIPT_TEMPLATE = """\"\"\"%s\"\"\"
# Keep __doc__ to a single line
from zine.upgrades.versions import *

# Define tables here


# Define the objects here


def map_tables(mapper):
    clear_mappers()
    # Map tables to the python objects here


def upgrade(migrate_engine):
    # Upgrade operations go here. Don't create your own engine
    # bind migrate_engine to your metadata
    session = scoped_session(lambda: create_session(migrate_engine,
                                                    autoflush=True,
                                                    autocommit=False))
    map_tables(session.mapper)


def downgrade(migrate_engine):
    # Operations to reverse the above upgrade go here.
    session = scoped_session(lambda: create_session(migrate_engine,
                                                    autoflush=True,
                                                    autocommit=False))
    map_tables(session.mapper)

"""
        open(path, 'w').write(NEW_SCRIPT_TEMPLATE % opts.get('description', ''))
        return cls(path)

    def run(self, engine, step):
        """Core method of Script file.
        Exectues :func:`update` or :func:`downgrade` functions

        :param engine: SQLAlchemy Engine
        :param step: Operation to run
        :type engine: string
        :type step: int
        """
        if step > 0:
            op = 'upgrade'
        elif step < 0:
            op = 'downgrade'
        else:
            raise exceptions.ScriptError("%d is not a valid step" % step)
        funcname = base.operations[op]
        script_func = self._func(funcname)
        try:
            script_func(engine)
        except TypeError:
            warnings.warn("upgrade/downgrade functions must accept engine"
                          " parameter (since version > 0.5.4)")
            raise

class Version(MigrateVersion):
    def _add_script_py(self, path):
        if self.python is not None:
            raise Exception('You can only have one Python script per version,'
                ' but you have: %s and %s' % (self.python, path))
        self.python = PythonScript(path)


class Collection(MigrateCollection):
    def __init__(self, path):
        # __init__ from pathed.Pathed
        self.path = path
        if self.__class__.parent is not None:
            self._init_parent(path)

        # Create temporary list of files, allowing skipped version numbers.
        files = listdir(path)
        tempVersions = dict()
        if '1' in files:
            raise Exception('It looks like you have a repository in the old '
                'format (with directories for each version). '
                'Please convert repository before proceeding.')
        for filename in files:
            match = self.FILENAME_WITH_VERSION.match(filename)
            if match:
                num = int(match.group(1))
                tempVersions.setdefault(num, []).append(filename)
            else:
                pass  # Must be a helper file or something, let's ignore it.

        # Create the versions member where the keys
        # are VerNum's and the values are Version's.
        self.versions = dict()
        for num, files in tempVersions.items():
            self.versions[api.VerNum(num)] = Version(num, path, files)

class ControlledSchema(MigrateControlledSchema):
    def runchange(self, ver, change, step):
        startver = ver
        endver = ver + step
        # Current database version must be correct! Don't run if corrupt!
        if self.version != startver:
            raise exceptions.InvalidVersionError(
                "%s is not %s" % (self.version, startver)
            )
        # Run the change
        change.run(self.engine, step)
        # Yield messages out
#        for message in change.run(self.engine, step):
#            yield message

        # Update/refresh database version
        try:
            # Update/refresh database version
            self.update_repository_table(startver, endver)
            self.load()
        except AttributeError:
            # SQLAlchemy-migrate 0.5.4
            from sqlalchemy.sql import and_
            update = self.table.update(
                and_(self.table.c.version == int(startver),
                     self.table.c.repository_id == str(self.repository.id)))
            self.engine.execute(update, version=int(endver))
            self._load()

class Changeset(dict):
    """A collection of changes to be applied to a database.

    Changesets are bound to a repository and manage a set of
    scripts from that repository.

    Behaves like a dict, for the most part. Keys are ordered based on step value.
    """

    def __init__(self, start, *changes, **k):
        """
        Give a start version; step must be explicitly stated.
        """
        self.step = k.pop('step', 1)
        self.start = api.VerNum(start)
        self.end = self.start
        for change in changes:
            self.add(change)

    def __iter__(self):
        return iter(self.items())

    def keys(self):
        """
        In a series of upgrades x -> y, keys are version x. Sorted.
        """
        ret = super(Changeset, self).keys()
        # Reverse order if downgrading
        ret.sort(reverse=(self.step < 1))
        return ret

    def values(self):
        return [self[k] for k in self.keys()]

    def items(self):
        return zip(self.keys(), self.values())

    def add(self, change):
        """Add new change to changeset"""
        key = self.end
        self.end += self.step
        self[key] = change

    def run(self, *p, **k):
        """Run the changeset scripts"""
        for version, script in self:
            #script.run(*p, **k)
            # Yield messages out
            for message in script.run(*p, **k):
                yield message

class Repository(MigrateRepository):
    # Overridden configuration since we won't use configuration files

    config = {
        'repository_id': 'Zine',
        'required_dbs': [] # We don't use specific database engines, we use all
    }

    version_table = 'schema_versions'

    def __init__(self, repository_path, repository_id):
        # __init__ from pathed.Pathed
        self.path = repository_path
        if self.__class__.parent is not None:
            self._init_parent(repository_path)
        # __init__ from Repository
        self.versions=Collection(join(repository_path, 'versions'))
        self.config['repository_id'] = repository_id

    @classmethod
    def _key(self, *p, **k):
        return str(p) + ':' + str(k)

    def changeset(self, database, start, end=None):
        """Create a changeset to migrate this database from ver. start to end/latest.

        :param database: name of database to generate changeset
        :param start: version to start at
        :param end: version to end at (latest if None given)
        :type database: string
        :type start: int
        :type end: int
        :returns: :class:`Changeset instance <migration.versioning.repository.Changeset>`
        """
        start = api.VerNum(start)

        if end is None:
            end = self.latest
        else:
            end = api.VerNum(end)

        if start <= end:
            step = 1
            range_mod = 1
            op = 'upgrade'
        else:
            step = -1
            range_mod = 0
            op = 'downgrade'

        versions = range(start + range_mod, end + range_mod, step)
        changes = []
        for version in range(start + range_mod, end + range_mod, step):
            try:
                changes.append(self.version(version).script(database, op))
            except KeyError:
                # trying to upgrade to version later than the latest?
                pass
        ret = Changeset(start, step=step, *changes)
        return ret

    id=property(lambda self: self.config.get('repository_id'))

# Customise sqlalchemy-migrate
api.ControlledSchema = ControlledSchema
api.PythonScript = PythonScript
api.Repository = Repository
