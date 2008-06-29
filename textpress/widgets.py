# -*- coding: utf-8 -*-
"""
    textpress.widgets
    ~~~~~~~~~~~~~~~~~

    This module provides the core widgets and functionality to build your
    own.  Widgets are, in the context of TextPress, classes that have a
    unicode conversion function that renders a template into a string but
    have all their attributes attached to themselves.  This gives template
    designers the ability to change the general widget template but also
    render one widget differently.

    Additionally widgets could be moved around from the admin panel in the
    future.

    :copyright: Copyright 2007-2008 by Armin Ronacher, Pedro Algarvio,
                                       Christopher Grebs, Ali Afshar.
    :license: GNU GPL.
"""
import re
import inspect
from os import path
from textpress.api import *
from textpress.models import Post, Tag, Comment
from textpress.utils import CSRFProtector

from jinja2 import nodes


_format_re = re.compile(r'(?<!%)%s')
_instruction_re = re.compile(r'\{\{|\}\}|\{%|%\}')


class Widget(object):
    """Baseclass for all the widgets out there!"""

    #: the name of the widget when called from a template.  This is also used
    #: if widgets are configured from the admin panel to have a unique
    #: identifier.
    NAME = None

    #: Set this to true if you don't want the widget to appear in the template
    #: context.  This is always a bad idea and only used in the special HTML
    #: widget or similar widgets in the future.
    INVISIBLE = False

    #: name of the template for this widget. Please prefix those template
    #: names with an underscore to mark it as partial. The widget is available
    #: in the template as `widget`.
    TEMPLATE = None

    @classmethod
    def get_display_name(cls):
        return cls.__name__

    @classmethod
    def list_arguments(cls, extended=False):
        """Get a tuple of the arguments this widget uses."""
        try:
            init = cls.__init__.im_func
        except AttributeError:
            return ()
        rv = inspect.getargspec(init)
        args = rv[0][1:]
        if not extended:
            return args
        return dict(zip(args, (None,) * (len(rv[3]) - len(args) - 1) + rv[3]))

    @staticmethod
    def configure_widget(initial_args, request):
        """Display the configuration page."""
        return None, None

    def render(self):
        """Render the template."""
        return render_template(self.TEMPLATE, widget=self)

    def __unicode__(self):
        return self.render()


class TagCloud(Widget):
    """
    A tag cloud. What else?
    """

    __metaclass__ = cache.make_metaclass(vary=('user',))
    NAME = 'get_tag_cloud'
    TEMPLATE = 'widgets/tagcloud.html'

    def __init__(self, max=None, show_title=False):
        self.tags = Tag.objects.get_cloud(max)
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Tag Cloud')

    @staticmethod
    def configure_widget(initial_args, request):
        args = form = initial_args.copy()
        error = None
        if request.method == 'POST':
            args['max'] = max = request.form.get('max', '')
            if not max:
                args['max'] = None
            elif not max.isdigit():
                error = _('Maximum number of tags must be empty '
                          'or a number.')
            else:
                args['max'] = int(max)
            args['show_title'] = request.form.get('show_title') == 'yes'
        if error is not None:
            args = None
        return args, render_template('admin/widgets/tagcloud.html',
            error=error,
            form=form
        )


class PostArchiveSummary(Widget):
    """
    Show the last n months/years/days with posts.
    """

    __metaclass__ = cache.make_metaclass(vary=('user',))
    NAME = 'get_post_archive_summary'
    TEMPLATE = 'widgets/post_archive_summary.html'

    def __init__(self, detail='months', limit=6, show_title=False):
        self.__dict__.update(Post.objects.get_archive_summary(detail, limit))
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Post Archive Summary')

    @staticmethod
    def configure_widget(initial_args, request):
        args = form = initial_args.copy()
        errors = []
        if request.method == 'POST':
            args['detail'] = detail = request.form.get('detail')
            if detail not in ('years', 'months', 'days'):
                errors.append(_('Detail must be years, months or days.'))
            args['limit'] = limit = request.form.get('limit')
            if not limit:
                args['limit'] = None
            elif not limit.isdigit():
                errors.append(_('Limit must be omited or a valid number.'))
            else:
                args['limit'] = int(limit)
            args['show_title'] = request.form.get('show_title') == 'yes'
        if errors:
            args = None
        return args, render_template('admin/widgets/post_archive_summary.html',
            errors=errors,
            form=form
        )


class LatestPosts(Widget):
    """
    Show the latest n posts.
    """

    __metaclass__ = cache.make_metaclass(vary=('user',))
    NAME = 'get_latest_posts'
    TEMPLATE = 'widgets/latest_posts.html'

    def __init__(self, limit=5, show_title=False):
        self.posts = Post.objects.latest(limit).all()
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Latest Posts')

    @staticmethod
    def configure_widget(initial_args, request):
        args = form = initial_args.copy()
        errors = []
        if request.method == 'POST':
            args['limit'] = limit = request.form.get('limit')
            if not limit:
                args['limit'] = None
            elif not limit.isdigit():
                errors.append(_('Limit must be omited or a valid number.'))
            else:
                args['limit'] = int(limit)
            args['show_title'] = request.form.get('show_title') == 'yes'
        if errors:
            args = None
        return args, render_template('admin/widgets/latest_posts.html',
                                     errors=errors, form=form)



class LatestComments(Widget):
    """
    Show the latest n comments.
    """

    __metaclass__ = cache.make_metaclass(vary=('user',))
    NAME = 'get_latest_comments'
    TEMPLATE = 'widgets/latest_comments.html'

    def __init__(self, limit=5, show_title=False, ignore_blocked=False):
        self.comments = Comment.objects. \
            latest(limit, ignore_blocked=ignore_blocked).all()
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Latest Comments')

    @staticmethod
    def configure_widget(initial_args, request):
        args = form = initial_args.copy()
        errors = []
        if request.method == 'POST':
            args['limit'] = limit = request.form.get('limit')
            if not limit:
                args['limit'] = None
            elif not limit.isdigit():
                errors.append(_('Limit must be omited or a valid number.'))
            else:
                args['limit'] = int(limit)
            args['show_title'] = request.form.get('show_title') == 'yes'
            args['ignore_blocked'] = request.form.get('ignore_blocked') == 'yes'
        if errors:
            args = None
        return args, render_template('admin/widgets/latest_comments.html',
                                     errors=errors, form=form)


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


#: list of all core widgets
all_widgets = [TagCloud, PostArchiveSummary, LatestPosts, LatestComments,
               PagesNavigation]
