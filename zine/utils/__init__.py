"""
    zine.utils
    ~~~~~~~~~~

    This package implements various functions used all over the code.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import os

try:
    from simplejson import dumps as dump_json, loads as load_json
except ImportError:
    from json import dumps as dump_json, loads as load_json

from werkzeug import url_quote, Local, LocalManager, ClosingIterator

# load dynamic constants
from zine._dynamic import *


# our local stuff
local = Local()
local_manager = LocalManager([local])
