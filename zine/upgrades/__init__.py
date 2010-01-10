"""
    zine.upgrades
    ~~~~~~~~~~~~~

    This package implements various classes and functions used to manage the
    database.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
import sys
from os.path import dirname, expanduser, join
from optparse import OptionParser

try:
    import migrate
except ImportError:
    from zine._core import MissingDependency
    raise MissingDependency("You need 'sqlalchemy-migrate' installed on your "
                            "system.")

from migrate.versioning import api
from migrate.versioning.util import construct_engine
from migrate.versioning.exceptions import KnownError

from zine import __version__ as VERSION, setup
# imported for side-effects
from zine.upgrades import customisation

REPOSITORY_PATH = dirname(__file__)


class CommandLineInterface(object):

    usage = '%%prog -I instancepath %s [options] %s'
    cmdline_version = '%%prog %s' % VERSION

    commands = {
             'help': 'Show help.',
             'list': 'List all repositories.',
           'script': 'Create an empty upgrade script.',
          'upgrade': 'Upgrade a database to a later version.',
        'downgrade': 'Downgrade a database to the specified version.',
    }

    def run(self, argv=sys.argv):
        """Main entry point of the command-line interface.

        :param argv: list of arguments passed on the command-line
        """
        self.parser = OptionParser(usage=self.usage % ('command', '[args]'),
                                   version=self.cmdline_version)
        self.parser.disable_interspersed_args()
        self.parser.print_help = self._general_help
        self.parser.add_option('-I', '--instance', dest='instance',
                               help="Zine instance path")

        options, args = self.parser.parse_args(argv[1:])

        self.instance_path = options.instance

        if not args:
            self.parser.error('no valid command or option passed. '
                              'Try the -h/--help option for more information.')

        cmdname = args[0]
        if cmdname not in self.commands:
            self.parser.error('unknown command "%s"' % cmdname)
        return getattr(self, cmdname)(args[1:])

    def get_zine_instance(self):
        if not self.instance_path:
            self.parser.error('you need to pass your Zine instance path.')
        if not hasattr(self, 'zine_instance'):
            self.zine_instance = setup(expanduser(self.instance_path))
        return self.zine_instance

    def _general_help(self):
        print self.parser.format_help()
        print "commands:"
        longest = max([len(command) for command in self.commands])
        format = "  %%-%ds %%s" % max(8, longest + 1)
        for name, description in self.commands.items():
            print format % (name, description)

    def help(self, argv):
        self._general_help()

    def cmdlogger(self, messages):
        from zine.utils.zeml import parse_html  # late import
        for message in messages:
            if hasattr(message, '__iter__'):
                self.cmdlogger(message)
            else:
                trailing_new_line = message and message.endswith('\n') or False
                message = parse_html(message).to_text(simple=True)
                if message:
                    # make the textifier output more compact
                    if message.endswith('\n\n') and trailing_new_line:
                        message = message[:-1]
                    elif message.endswith('\n') and not trailing_new_line:
                        message = message.rstrip('\n')
                    sys.stdout.write(message.encode('utf-8'))
                    sys.stdout.flush()

    def list(self, argv):
        self.get_zine_instance()
        def list_them():
            from zine.models import SchemaVersion
            available_svs = SchemaVersion.query.all()
            yield '<h2>Available repositories</h2>\n'
            yield '<ul>'
            for sv in available_svs:
                yield '<li>' + sv.repository_id + '</li>\n'
            yield '</ul>\n'
        self.cmdlogger(list_them())

    def script(self, argv):
        parser = OptionParser(usage=self.usage % ('script', 'DESCRIPTION'),
                              description=self.commands['script'])
        parser.add_option('-r', '--repository-id', help='the repository id',
                          default='Zine', dest='repo_id')
        parser.add_option(
            '-f', '--filename',
            help="file name (without spaces and/or version number)")
        options, args = parser.parse_args(argv)
        description = ' '.join(args)
        manage = ManageDatabase(self.get_zine_instance())
        self.cmdlogger(manage.cmd_script(options.repo_id, description,
                                         options.filename))

    def upgrade(self, argv):
        parser = OptionParser(usage=self.usage % ('upgrade', '[REPO] [VERSION]'),
                              description=self.commands['upgrade'])
        parser.add_option('--echo', default=False, action='store_true',
                          help='echo the SQL statements')
        options, args = parser.parse_args(argv)
        repo = args and args.pop(0) or None
        version = args and args.pop(0) or None
        manage = ManageDatabase(self.get_zine_instance())
        self.cmdlogger(manage.cmd_upgrade(repo, version, echo=options.echo))

    def downgrade(self, argv):
        parser = OptionParser(usage=self.usage % ('downgrade', 'REPO [VERSION]'),
                              description=self.commands['downgrade'])
        parser.add_option('--echo', default=False, action='store_true',
                          help='echo the SQL statements')
        options, args = parser.parse_args(argv)
        try:
            repo = args.pop(0)
        except IndexError:
            parser.error('you need to pass the repository id for downgrades, '
                         'see the list command.')
        version = args and args.pop(0) or None
        manage = ManageDatabase(self.get_zine_instance())
        self.cmdlogger(manage.cmd_downgrade(repo, version, echo=options.echo))


class ManageDatabase(object):
    """Database maintenance class."""

    def __init__(self, instance):
        self.instance = instance
        self.url = str(instance.database_engine.url)

    def cmd_script(self, repo_id, description, filename=None):
        """Create an empty change script using the next unused version number
        appended with the given description.

        For instance, manage.py script "Add initial tables" creates:
        repository/versions/001_Add_initial_tables.py
        """
        from zine.models import SchemaVersion
        sv = SchemaVersion.query.filter_by(repository_id=repo_id).first()
        if not sv:
            print 'Repository by the id %s not known' % repo_id
            sys.exit(1)
        repos = api.Repository(sv.repository_path, sv.repository_id)
        new_script_version = repos.versions.latest + 1
        filename = '%%03d_%s' % (filename and filename or description) % \
                                                            new_script_version
        filename = re.sub(r'[^a-zA-Z0-9_-]+', '_', filename) + '.py'
        new_script_path = join(repos.path, 'versions', filename)
        yield 'Creating script %s\n' % new_script_path
        api.PythonScript.create(new_script_path, description=description)

    def cmd_upgrade(self, repo_id=None, version=None, **opts):
        """Upgrade a database to a later version.

        This runs the upgrade() function defined in your change scripts.

        By default, the database is updated to the latest available
        version. You may specify a version instead, if you wish.

        You may preview the Python or SQL code to be executed, rather than
        actually executing it, using the appropriate 'preview' option.
        """
        from zine.models import SchemaVersion
        if repo_id is None:
            # get all repos, sort those with id "Zine*" first
            available_svs = sorted(
                SchemaVersion.query.order_by(SchemaVersion.repository_id.asc()),
                key=lambda sv: not sv.repository_id.startswith('Zine'))
        else:
            available_svs = [SchemaVersion.query.get(repo_id)]
        # Now, run the available schema version upgrades
        for sv in available_svs:
            try:
                repository = api.Repository(sv.repository_path, sv.repository_id)
                for message in self._migrate(repository, version,
                                             upgrade=True, **opts):
                    yield message
            except Exception, msg:
                yield '<p>error upgrading %s: ' % repo_id
                yield str(msg)
                yield '</p>\n'

    def cmd_downgrade(self, repo_id, version=None, **opts):
        """Downgrade a database to an earlier version.

        This is the reverse of upgrade; this runs the downgrade() function
        defined in your change scripts.

        You may preview the Python or SQL code to be executed, rather than
        actually executing it, using the appropriate 'preview' option.
        """
        from zine.models import SchemaVersion
        sv = SchemaVersion.query.get(repo_id)
        repository = api.Repository(sv.repository_path, sv.repository_id)
        if version is None:
            version = sv.version - 1
        try:
            for message in self._migrate(repository, version,
                                         upgrade=False, **opts):
                yield message
        except Exception, msg:
            yield '<p>error downgrading %s: ' % repo_id
            yield str(msg)
            yield '</p>\n'

    def _migrate(self, repository, version, upgrade, **opts):
        engine = construct_engine(self.url, **opts)
        schema = api.ControlledSchema(engine, repository)
        version = self._migrate_version(schema, version, upgrade)

        changeset = schema.changeset(version)
        if not changeset:
            yield '<p>Repository %s is already up to date.</p>\n' % repository.id
            return

        yield '<h2>Migrating %s</h2>\n' % repository.id
        for ver, change in changeset:
            nextver = ver + changeset.step
            doc = schema.repository.version(max(ver, nextver)). \
                                                        script().module.__doc__
            yield '<h3>%s -> %s - %s</h3>\n' % (ver, nextver, doc)
            for message in schema.runchange(ver, change, changeset.step):
                yield message
            yield '\n<p>Done!</p>\n'

    def _migrate_version(self, schema, version, upgrade):
        if version is None:
            return version
        if version < 0:
            raise KnownError("Already at version 0.")
        # Version is specified: ensure we're upgrading in the right direction
        # (current version < target version for upgrading; reverse for down)
        version = api.VerNum(version)
        cur = schema.version
        if upgrade:
            direction = cur <= version
        else:
            direction = cur >= version
        if not direction:
            msg = ("Cannot %s a database of version %%s to version %%s. "
                   "Try '%s' instead.")
            if upgrade:
                msg = msg % ('upgrade', 'downgrade')
            else:
                msg = msg % ('downgrade', 'upgrade')
            raise KnownError(msg % (cur, version))
        return version
