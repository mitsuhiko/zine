#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Manage TextPress Website
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Simple management script for database updates.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import os
from werkzeug import script


def make_app():
    from tpweb import application
    return application


def shell_init_func():
    return {}


action_runserver = script.make_runserver(make_app, use_reloader=True)
action_shell = script.make_shell(shell_init_func)


if __name__ == '__main__':
    script.run()
