# -*- coding: utf-8 -*-
"""
    zine.importers.feed
    ~~~~~~~~~~~~~~~~~~~

    This importer can import web feeds.  Currently it is limited to ATOM
    plus optional Zine extensions.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from zine.i18n import _, lazy_gettext
from zine.importers import Importer, Blog, Tag, Category, Author, Post, Comment
from zine.forms import FeedImportForm


class FeedImporter(Importer):
    name = 'feed'
    title = lazy_gettext(u'Feed Importer')

    def configure(self, request):
        form = FeedImportForm()
        return self.render_admin_page('admin/import_feed.html',
                                      form=form.as_widget())
