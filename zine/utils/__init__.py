"""
    zine.utils
    ~~~~~~~~~~

    This package implements various functions used all over the code.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from json import dumps as dump_json, loads as load_json

from werkzeug.local import Local, LocalManager
from werkzeug.wsgi import ClosingIterator

from zine._compat import url_quote

# load dynamic constants
from zine._dynamic import *


# our local stuff
local = Local()
local_manager = LocalManager([local])
