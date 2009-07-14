"""
    zine.upgrades
    ~~~~~~~~~~~~~

    This package implements various classes and functions used to manage the
    database.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

import re
import sys
import types
import logging
from os.path import dirname, expanduser, join
from optparse import OptionParser

from migrate.versioning import api, exceptions
from migrate.versioning.util import construct_engine
from zine import __version__ as VERSION, setup
from zine.upgrades import customisation

REPOSITORY_PATH = dirname(__file__)


class LogFormatter(logging.Formatter):
    def format(self, record):
        """
        Format the specified record as text.

        The record's attribute dictionary is used as the operand to a
        string formatting operation which yields the returned string.
        Before formatting the dictionary, a couple of preparatory steps
        are carried out. The message attribute of the record is computed
        using LogRecord.getMessage(). If the formatting string contains
        "%(asctime)", formatTime() is called to format the event time.
        If there is exception information, it is formatted using
        formatException() and appended to the message.
        """
        record.message = record.getMessage()
#        if string.find(self._fmt,"%(asctime)") >= 0:
#            record.asctime = self.formatTime(record, self.datefmt)
        s = self._fmt % record.__dict__
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
#            if s[-1:] != "\n":
#                s = s + "\n"
            s = s + record.exc_text
        from zine.utils.zeml import parse_html
        trailing_new_line = s and s.endswith('\n') or False
        s = parse_html(s).to_text(simple=True)
        if s and s.endswith('\n') and not trailing_new_line:
            s = s.rstrip('\n')
        return s

class LogHandler(logging.StreamHandler):
    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        The record is then written to the stream with a trailing newline
        [N.B. this may be removed depending on feedback]. If exception
        information is present, it is formatted using
        traceback.print_exception and appended to the stream.
        """
        try:
            msg = self.format(record)
#            fs = "%s\n"
            fs = '%s'
            if not hasattr(types, "UnicodeType"): #if no unicode support...
                self.stream.write(fs % msg)
            else:
                try:
                    self.stream.write(fs % msg)
                except UnicodeError:
                    self.stream.write(fs % msg.encode("UTF-8"))
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


class CommandLineInterface(object):

    usage = '%%prog %s [options] %s'
    cmdline_version = '%%prog %s' % VERSION

    commands = {
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
        self.parser.print_help = self._help
        self.parser.add_option('-I', '--instance', dest='instance',
                               help="zine instance folder")

        options, args = self.parser.parse_args(argv[1:])

        self.instance_folder = options.instance

        if not args:
            self.parser.error('no valid command or option passed. '
                              'Try the -h/--help option for more information.')

        # Setup logging
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        handler = LogHandler(sys.stdout)
        handler.setFormatter(LogFormatter("%(message)s"))
        root_logger.addHandler(handler)

        cmdname = args[0]
        if cmdname not in self.commands:
            self.parser.error('unknown command "%s"' % cmdname)
        return getattr(self, cmdname)(args[1:])

    def get_zine_instance(self):
        if not self.instance_folder:
            self.parser.error('You need to pass the path to your zine\'s '
                              ' instance folder')
        if not hasattr(self, 'zine_instance'):
            self.zine_instance = setup(expanduser(self.instance_folder))
        return self.zine_instance

    def _help(self):
        print self.parser.format_help()
        print "commands:"
        longest = max([len(command) for command in self.commands])
        format = "  %%-%ds %%s" % max(8, longest + 1)
        for name, description in self.commands.items():
            print format % (name, description)

    def cmdlogger(self, messages):
        from zine.utils.zeml import parse_html  # late import
        for message in messages:
            if hasattr(message, '__iter__'):
                self.cmdlogger(message)
            else:
                trailing_new_line = message and message.endswith('\n') or False
                message = parse_html(message).to_text(simple=True)
                if message:
                    if message.endswith('\n') and not trailing_new_line:
                        message = message.rstrip('\n')
                    sys.stdout.write(message.encode('utf-8'))
                    sys.stdout.flush()

    def script(self, argv):
        parser = OptionParser(usage=self.usage % ('script', 'DESCRIPTION'),
                              description=self.commands['script'])
        parser.add_option('-r', '--repository-id', help='the repository id',
                          default='Zine', dest='repo_id')
        parser.add_option(
            '-f', '--filename',
            help="filename name(without spaces and/or version number)")
        options, args = parser.parse_args(argv)
        description = ' '.join(args)
        manage = ManageDatabase(self.get_zine_instance())
        manage.cmd_script(options.repo_id, description, options.filename)
#        self.cmdlogger(manage.cmd_script(options.repo_id, description,
#                                         options.filename))

    def upgrade(self, argv):
        parser = OptionParser(usage=self.usage % ('upgrade', '[VERSION]'),
                              description=self.commands['upgrade'])
        parser.add_option('--echo', default=False, action='store_true',
                          help='echo the SQL statements')
        options, args = parser.parse_args(argv)
        version = args and args.pop(0) or None
        manage = ManageDatabase(self.get_zine_instance())
        manage.cmd_upgrade(version, echo=options.echo)
#        self.cmdlogger(manage.cmd_upgrade(version, echo=options.echo))

    def downgrade(self, argv):
        parser = OptionParser(usage=self.usage % ('downgrade', 'VERSION'),
                              description=self.commands['downgrade'])
        parser.add_option('--echo', default=False, action='store_true',
                          help='echo the SQL statements')
        options, args = parser.parse_args(argv)
        version = args and args.pop(0) or None
        manage = ManageDatabase(self.get_zine_instance())
        try:
            self.cmdlogger(manage.cmd_downgrade(version, echo=options.echo))
        except ValueError:
            self.cmdlogger(['No more downgrades avaialable'])


# Database maintenance class
class ManageDatabase(object):

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
        log.info('Creating script %s\n', new_script_path)
        api.PythonScript.create(new_script_path, description=description)


    def cmd_upgrade(self, version=None, **opts):
        """Upgrade a database to a later version.

        This runs the upgrade() function defined in your change scripts.

        By default, the database is updated to the latest available
        version. You may specify a version instead, if you wish.

        You may preview the Python or SQL code to be executed, rather than
        actually executing it, using the appropriate 'preview' option.
        """
        from zine.models import SchemaVersion
        for sv in SchemaVersion.query.all():
            repository = api.Repository(sv.repository_path, sv.repository_id)
            self._migrate(repository, version, upgrade=True, **opts)


    def cmd_downgrade(self, version=None, **opts):
        """Downgrade a database to an earlier version.

        This is the reverse of upgrade; this runs the downgrade() function
        defined in your change scripts.

        You may preview the Python or SQL code to be executed, rather than
        actually executing it, using the appropriate 'preview' option.
        """
        from zine.models import SchemaVersion
        for sv in SchemaVersion.query.all():
            repository = api.Repository(sv.repository_path, sv.repository_id)
            if version is None:
                version = repository.version -1
            yield self._migrate(repository, version, upgrade=False, **opts)


    def _migrate(self, repository, version, upgrade, **opts):

        log = logging.getLogger(__name__)
        engine = construct_engine(self.url, **opts)
        schema = api.ControlledSchema(engine, repository)
        version = self._migrate_version(schema, version, upgrade)

        changeset = schema.changeset(version)
        if changeset:
            log.info('<h3>Upgrading %s</h3>\n', repository.id)
        for ver, change in changeset:
            nextver = ver + changeset.step
            doc = schema.repository.version(max(ver, nextver)). \
                                                        script().module.__doc__
            log.info('<h2>%s -> %s - %s</h2>\n', ver, nextver, doc)
            schema.runchange(ver, change, changeset.step)
            log.info('done\n\n')


    def _migrate_version(self, schema, version, upgrade):
        if version is None:
            return version
        # Version is specified: ensure we're upgrading in the right direction
        # (current version < target version for upgrading; reverse for down)
        version = api.VerNum(version)
        cur = schema.version
        if upgrade is not None:
            if upgrade:
                direction = cur <= version
            else:
                direction = cur >= version
            if not direction:
                err = "Cannot % a database of version %%s to version %%s. "\
                      "Try '%s' instead.\n"
                if upgrade:
                    err = err % ('upgrade', 'downgrade')
                else:
                    err = err % ('downgrade', 'upgrade')
                raise exceptions.KnownError(err%(cur, version))
        return version
