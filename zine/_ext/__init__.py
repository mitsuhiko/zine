# -*- coding: utf-8 -*-
"""
    zine._ext
    ~~~~~~~~~

    This module contains external dependencies that are not installable via
    the cheeseshop, are patched or whatever.

    Why these libraries are here:

    -   beautiful soup: will go away for a custom HTML inspired parser with
        one of the first releases.

    -   feedparser: it's a solid library but very inflexible and limited in
        many ways (eg: enforced sanitizing).  Will go away as soon as we have
        created a fork of it that is more modular.

    :copyright: Copyright 2007-2008 by Armin Ronacher
    :license: BSD
"""
