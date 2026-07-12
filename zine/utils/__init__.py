"""
    zine.utils
    ~~~~~~~~~~

    This package implements various functions used all over the code.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from json import dumps as dump_json, loads as load_json
from threading import get_ident

from werkzeug.local import Local, LocalManager as WerkzeugLocalManager
from werkzeug.wsgi import ClosingIterator

from zine._compat import url_quote

# load dynamic constants
from zine._dynamic import *


class LocalManager(WerkzeugLocalManager):
    # Werkzeug's old LocalManager exposed this as a SQLAlchemy scope function.
    get_ident = staticmethod(get_ident)


# our local stuff
local = Local()
local_manager = LocalManager([local])
