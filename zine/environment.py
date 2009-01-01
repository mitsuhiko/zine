# -*- coding: utf-8 -*-
"""
    zine.environment
    ~~~~~~~~~~~~~~~~

    This module can figure how Zine is installed and where it has to look
    for shared information.  Currently it knows about two modes: development
    environment and installation on a posix system.  OS X should be special
    cased later and Windows support is missing by now.

    File Locations
    --------------

    The files are located at different places depending on the environment.

    development
        in development mode all the files are relative to the zine
        package::

            zine/                           application code
                plugins/                    builtin plugins
                shared/                     core shared data
                templates/                  core templates
                i18n/                       translations

    posix
        On a posix system (including Linux) the files are distributed to
        different locations on the file system below the prefix which is
        /usr in the following example::

            /usr/lib/zine/
                zine/                       application code
                plugins/                    builtin plugins with symlinks
                                            to stuff in /usr/share/zine
            /usr/share/zine/
                htdocs/core                 core shared data
                templates/core              core templates
                i18n/                       translations

    :copyright: 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from os.path import realpath, dirname, join, pardir, isdir


# the platform name
from os import name as PLATFORM


# the path to the contents of the zine package
PACKAGE_CONTENTS = realpath(dirname(__file__))

# the path to the folder where the "zine" package is stored in.
PACKAGE_LOCATION = realpath(join(PACKAGE_CONTENTS, pardir))

# name of the domain for the builtin translations
LOCALE_DOMAIN = 'messages'

# true if the LC_MESSAGES folder is in use for the core domains
# (gettext based lookup is used then).  This does not affect
# translations from non-core plugins
USE_GETTEXT_LOOKUP = False

# check development mode first.  If there is a shared folder we must be
# in development mode.
SHARED_DATA = join(PACKAGE_CONTENTS, 'shared')
if isdir(SHARED_DATA):
    MODE = 'development'
    BUILTIN_PLUGIN_FOLDER = join(PACKAGE_CONTENTS, 'plugins')
    BUILTIN_TEMPLATE_PATH = join(PACKAGE_CONTENTS, 'templates')
    LOCALE_PATH = join(PACKAGE_CONTENTS, 'i18n')

# a Zine installation on a posix system
elif PLATFORM == 'posix':
    MODE = 'posix'
    share = join(PACKAGE_LOCATION, pardir, pardir, 'share')
    BUILTIN_PLUGIN_FOLDER = realpath(join(PACKAGE_LOCATION, 'plugins'))
    BUILTIN_TEMPLATE_PATH = realpath(join(share, 'zine', 'templates', 'core'))
    SHARED_DATA = realpath(join(share, 'zine', 'htdocs', 'core'))
    LOCALE_PATH = realpath(join(share, 'locale'))
    LOCALE_DOMAIN = 'zine'
    USE_GETTEXT_LOOKUP = True
    del share

# a Zine installation on windows
elif PLATFORM == 'nt':
    raise NotImplementedError('Installation on windows is currently not '
                              'possible.  Consider using Zine in development '
                              'mode.')

else:
    raise EnvironmentError('Could not determine Zine environment')


# get rid of the helpers
del realpath, dirname, join, pardir, isdir
