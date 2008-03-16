# -*- coding: utf-8 -*-
"""
    textpress.plugins.pages
    ~~~~~~~~~~~~~~~~~~~~~~~

    Just a little plugin that supports static pages.

    It implements also a little widget that renders a navigation
    bar (for now just a list of links of all pages).
    They are ordered by the `navigation_pos` attribute of every page.

    It's possible to use all parsers known from the post-interface
    so you can use the comment-parser, plain-html and others.


    :copyright: Copyright 2007-2008 by Christopher Grebs and Ali Afshar.
    :license: GNU GPL.
"""
from os.path import dirname, join
from random import choice
from werkzeug.exceptions import NotFound
from textpress.api import *
from textpress.widgets import Widget
from textpress.views.admin import render_admin_response, flash
from textpress.models import ROLE_ADMIN
from textpress.utils import CSRFProtector, gen_slug, escape
from textpress import cache
from textpress.plugins.pages.database import Page, pages_table


TEMPLATES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')


class PagesNavigation(Widget):
    """
    A little navigation widget.
    """

    NAME = 'get_pages_navigation'
    TEMPLATE = 'widgets/pages_navigation.html'

    def __init__(self):
        pages = Page.objects.query
        to_append = pages.filter_by(navigation_pos=None)
        self.pages = pages.filter(pages_table.c.navigation_pos!=None) \
            .order_by(pages_table.c.navigation_pos.asc()).all()
        self.pages.extend(to_append.all())

    @staticmethod
    def get_display_name():
        return _(u'Pages Navigation')


def add_admin_link(request, navigation_bar):
    """Inject the links for the admin navigation bar"""
    if request.user.role >= ROLE_ADMIN:
        navigation_bar.insert(2,
            ('pages', url_for('pages/show_pages'), _('Pages'), [
                ('overview', url_for('pages/show_pages'), _('Overview')),
                ('write', url_for('pages/write_page'), _('Write Page')),
                ('config', url_for('pages/configure'), _('Configuration')),
        ]))


@require_role(ROLE_ADMIN)
def show_pages_config(request):
    """Show the configuration page for the pages plugin"""
    cfg = get_application().cfg
    csrf_protector = CSRFProtector()
    form = {
        'show_title': cfg['pages/show_title'],
        'show_children': cfg['pages/show_children'],
    }
    if request.method == 'POST':
        csrf_protector.assert_safe()
        rform = request.form
        form['show_title'] = show_title = 'show_title' in request.form
        form['show_children'] = show_children = 'show_children' in request.form

        # update the configuration
        if show_title != cfg['pages/show_title']:
            cfg['pages/show_title'] = show_title
        if show_children != cfg['pages/show_children']:
            cfg['pages/show_children'] = show_children
        flash(u'Pages configuration updated successfull.')

    return render_admin_response(
        'admin/pages_config.html',
        'pages.config',
        form=form,
        csrf_protector=csrf_protector,
    )


@require_role(ROLE_ADMIN)
def show_pages_overview(request):
    """Shows all saved pages"""
    return render_admin_response(
        'admin/pages.html',
        'pages.overview',
        pages=Page.objects.all()
    )


@require_role(ROLE_ADMIN)
def show_pages_write(request, page_id=None):
    """
    Show the "write page" dialog.

    If `page_id` is given the form is updated with
    already saved data so that you can edit a page.
    """
    csrf_protector = CSRFProtector()
    form = {}
    errors = []

    if page_id is None:
        # new page
        new_page = True
        form.update(
            key=u'', title=u'',
            raw_body=u'',
            navigation_pos=u'',
            parser=request.app.cfg['default_parser'],
        )
    else:
        # edit a page
        new_page = False
        page = Page.objects.get(page_id)
        if page is None:
            raise NotFound()
        form.update(
            key=page.key,
            title=page.title,
            raw_body=page.raw_body,
            navigation_pos=page.navigation_pos,
            parser=page.extra['parser'],
            parent_id=page.parent_id or 0,
        )

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect(url_for('pages/show_pages'))
        if request.form.get('delete') and not new_page:
            return redirect(url_for('pages/delete_page', page_id=page_id))

        form['title'] = title = request.form.get('title')
        if not title:
            errors.append(_('You have to provide a title'))

        form['key'] = key = request.form.get('key') or None
        if key is None:
            key = gen_slug(title)
        elif key:
            key = gen_slug(key)
        if u'/' in key:
            errors.append(_("A key can't contain a slash"))

        form['navigation_pos'] = navigation_pos = \
            request.form.get('navigation_pos') or None

        form['raw_body'] = raw_body = request.form.get('raw_body')
        if not raw_body:
            errors.append(_('You have to provide a content'))

        form['parser'] = parser = request.form.get('parser')
        if not parser:
            parser = request.app.cfg['default_parser']

        form['parent_id'] = parent_id = request.form.get('parent_id')

        try:
            parent_id = int(parent_id)
        except (ValueError, TypeError):
            parent_id = None
        if parent_id == 0:
            parent_id = None

        if not errors:
            if new_page:
                page = Page(key, title, raw_body, parser, navigation_pos,
                            parent_id)
            else:
                page.key = key
                page.title = title
                page.parser = parser
                page.raw_body = raw_body
                page.navigation_pos = navigation_pos
                page.parent_id = parent_id

            db.commit()
            html_detail = '<a href="%s">%s</a>' % (
                escape(url_for(page)),
                escape(title)
            )
            if new_page:
                flash('The page %s was created successfully.' % html_detail)
            else:
                flash('The page %s was updated successfully.' % html_detail)
            return redirect(url_for('pages/show_pages'))
        else:
            for error in errors:
                flash(error, 'error')

    all_pages = [(0, 'No Parent')] + [(p.page_id, p.title) for p in
                                      Page.objects.all()]

    return render_admin_response(
        'admin/write_page.html',
        'pages.write',
        parsers=request.app.list_parsers(),
        form=form,
        csrf_protector=csrf_protector,
        all_pages=all_pages,
    )


@require_role(ROLE_ADMIN)
def show_pages_delete(request, page_id):
    """Shows the confirm dialog if the user deletes a page"""
    page = Page.objects.get(page_id)
    if page is None:
        raise NotFound()
    csrf_protector = CSRFProtector()

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect(url_for('pages/write_page', page_id=page.page_id))
        elif request.form.get('confirm'):
            db.delete(page)
            flash(_('The page %s was deleted successfully.') %
                  escape(page.title), 'remove')
            db.commit()
            return redirect(url_for('pages/show_pages'))

    return render_admin_response('admin/delete_page.html', 'page.write',
        page=page,
        csrf_protector=csrf_protector,
    )


@cache.response(vary=('user',))
def show_page(self, key):
    """Shot a page found via `key`"""
    page = Page.objects.query.filter_by(key=key).first()
    if page is None:
        raise NotFound()
    cfg = get_application().cfg
    return render_response(
        'page_base.html',
        page=page,
        blog_title=get_application().cfg['blog_title'],
        show_title=cfg['pages/show_title'],
        show_children=cfg['pages/show_children']
    )


def setup(app, plugin):
    """setup the plugin"""
    # add database integrity check
    from textpress.plugins.pages.database import upgrade_database
    app.add_database_integrity_check(upgrade_database)

    # config vars
    app.add_config_var('pages/show_title', bool, True)
    app.add_config_var('pages/show_children', bool, True)

    # inject to admin navigation and shared folder
    app.connect_event('modify-admin-navigation-bar', add_admin_link)
    app.add_shared_exports('pages', SHARED_FILES)

    # add url rules
    app.add_url_rule('/show_pages/', endpoint='pages/show_pages',
                     prefix='admin', view=show_pages_overview)
    app.add_url_rule('/write_page/', endpoint='pages/write_page',
                     prefix='admin', view=show_pages_write)
    app.add_url_rule('/write_page/<int:page_id>/',
                     endpoint='pages/write_page', prefix='admin')
    app.add_url_rule('/page/<key>/', endpoint='pages/show_page',
                     view=show_page, prefix='blog')
    app.add_url_rule('/delete_page/<int:page_id>/',
                     endpoint='pages/delete_page',
                     view=show_pages_delete, prefix='admin')
    app.add_url_rule('/options/pages/', endpoint='pages/configure',
                     prefix='admin', view=show_pages_config)

    # templage searchpath and widget
    app.add_template_searchpath(TEMPLATES)
    app.add_widget(PagesNavigation)
