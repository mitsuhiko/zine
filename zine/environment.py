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

            zine/                      application code
                plugins/                    builtin plugins
                shared/                     core shared data
                templates/                  core templates

    posix
        On a posix system (including Linux) the files are distributed to
        different locations on the file system below the prefix which is
        /usr in the following example::

            /usr/lib/zine/zine    application code
            /usr/lib/zine/plugins      builtin plugins
            /usr/share/zine/htdocs     core shared data
            /usr/share/zine/templates  core templates

    windows
        On windows the files are installed into the program files
        folder alone. % is the path to the program folder::

            %/Zine/zine           application code
            %/Zine/plugins             builtin plugins
            %/Zine/htdocs              core shared data
            %/Zine/templates           core templates

    :copyright: 2008 by Armin Ronacher.
    :license: BSD
"""
from os.path import realpath, dirname, join, pardir, isdir


# the platform name
from os import name as PLATFORM


# the path to the contents of the zine package
PACKAGE_CONTENTS = realpath(dirname(__file__))

# the path to the folder where the "zine" package is stored in.
PACKAGE_LOCATION = realpath(join(PACKAGE_CONTENTS, pardir))

# These are currently the same on all platforms because we run our
# own gettext inspired system
LOCALE_PATH = join(PACKAGE_CONTENTS, 'i18n')

# check development mode first.  If there is a shared folder we must be
# in development mode.
SHARED_DATA = join(PACKAGE_CONTENTS, 'shared')
if isdir(SHARED_DATA):
    MODE = 'development'
    BUILTIN_PLUGIN_FOLDER = join(PACKAGE_CONTENTS, 'plugins')
    BUILTIN_TEMPLATE_PATH = join(PACKAGE_CONTENTS, 'templates')

# a Zine installation on a posix system
elif PLATFORM == 'posix':
    MODE = 'posix'
    share = join(PACKAGE_LOCATION, pardir, pardir, 'share', 'zine')
    BUILTIN_PLUGIN_FOLDER = realpath(join(PACKAGE_LOCATION, 'plugins'))
    BUILTIN_TEMPLATE_PATH = realpath(join(share, 'templates'))
    SHARED_DATA = realpath(join(share, 'htdocs'))
    del share

# a Zine installation on windows
elif PLATFORM == 'nt':
    raise NotImplementedError('installation on windows not possible')

else:
    raise EnvironmentError('Could not determine Zine environment')


# get rid of the helpers
del realpath, dirname, join, pardir, isdir
