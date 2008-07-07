# -*- coding: utf-8 -*-
"""
    TextPress Documentation Extensions
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Support for automatically documenting filters and tests.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD.
"""
import os
import re
import inspect
import pickle
from sphinx.application import TemplateBridge
from sphinx.builder import SerializingHTMLBuilder
from jinja2 import Environment, FileSystemLoader


class Jinja2Bridge(TemplateBridge):

    def init(self, builder):
        path = builder.config.templates_path
        self.env = Environment(loader=FileSystemLoader(path))

    def render(self, template, context):
        return self.env.get_template(template).render(context)


class AdminHTMLBuilder(SerializingHTMLBuilder):
    implementation = pickle
    name = 'adminhtml'
    out_suffix = '.page'
    globalcontext_filename = 'globalcontext.dump'
    searchindex_filename = 'searchindex.dump'
    add_header_links = False
    add_definition_links = False

    def get_target_uri(self, docname, typ=None):
        if docname == 'index':
            return ''
        if docname.endswith('/index'):
            return docname[:-5]
        return docname


def cut_module_lines(app, what, name, obj, options, lines):
    if what != 'module':
        return

    # cut the header
    if lines and not lines[0].strip():
        del lines[0]
    del lines[:2]

    # now get rid of the copyright footer
    in_copyright = False
    while lines:
        # delete empty lines
        if not lines[-1]:
            del lines[-1]
            # if we are in a copyright, abort now
            if in_copyright:
                break
        if not in_copyright:
            if not lines[-1].startswith(':'):
                break
            in_copyright = True
        del lines[-1]

def setup(app):
    app.connect('autodoc-process-docstring', cut_module_lines)
    app.add_builder(AdminHTMLBuilder)
