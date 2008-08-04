# -*- coding: utf-8 -*-
"""
    textpress.environment
    ~~~~~~~~~~~~~~~~~~~~~

    This module can figure how TextPress is installed and where it has to look
    for shared information.  Currently it knows about two modes: development
    environment and installation on a posix system.  OS X should be special
    cased later and Windows support is missing by now.

    File Locations
    --------------

    The files are located at different places depending on the environment.

    development
        in development mode all the files are relative to the textpress
        package::

            textpress/                      application code
                plugins/                    builtin plugins
                shared/                     core shared data
                templates/                  core templates

    posix
        On a posix system (including Linux) the files are distributed to
        different locations on the file system below the prefix which is
        /usr in the following example::

            /usr/lib/textpress/textpress    application code
            /usr/lib/textpress/plugins      builtin plugins
            /usr/share/textpress/htdocs     core shared data
            /usr/share/textpress/templates  core templates

    windows
        On windows the files are installed into the program files
        folder alone. % is the path to the program folder::

            %/TextPress/textpress           application code
            %/TextPress/plugins             builtin plugins
            %/TextPress/htdocs              core shared data
            %/TextPress/templates           core templates

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import realpath, dirname, join, pardir, isdir


# the platform name
from os import name as PLATFORM


# the path to the contents of the textpress package
PACKAGE_CONTENTS = realpath(dirname(__file__))

# the path to the folder where the "textpress" package is stored in.
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

# a TextPress installation on a posix system
elif PLATFORM == 'posix':
    MODE = 'posix'
    share = join(PACKAGE_LOCATION, pardir, pardir, 'share')
    BUILTIN_PLUGIN_FOLDER = realpath(join(PACKAGE_LOCATION, 'plugins'))
    BUILTIN_TEMPLATE_PATH = realpath(join(share, 'textpress', 'templates'))
    SHARED_DATA = realpath(join(share, 'textpress', 'htdocs'))
    del share

# a TextPress installation on windows
elif PLATFORM == 'nt':
    raise NotImplementedError('installation in windows not possible')

else:
    raise EnvironmentError('Could not determine TextPress environment')


# get rid of the helpers
del realpath, dirname, join, pardir, isdir
