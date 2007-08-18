# -*- coding: utf-8 -*-
"""
    textpress._dynamic
    ~~~~~~~~~~~~~~~~~~

    Contains modules that are self executable and contain important
    information such as timezones.

    The module is nonpublic but all the important constants are imported
    into the "textpress.utils" module.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress._dynamic.timezones import TIMEZONES

__all__ = ['TIMEZONES']
