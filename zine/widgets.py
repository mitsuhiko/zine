# -*- coding: utf-8 -*-
"""
    zine.widgets
    ~~~~~~~~~~~~

    This module provides the core widgets and functionality to build your
    own.  Widgets are, in the context of Zine, classes that have a
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
from zine.api import *
from zine.database import pages as pages_table
from zine.models import Post, Tag, Comment, Page


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

    def render(self):
        """Render the template."""
        return render_template(self.TEMPLATE, widget=self)

    def __unicode__(self):
        return self.render()


class TagCloud(Widget):
    """
    A tag cloud. What else?
    """

    NAME = 'get_tag_cloud'
    TEMPLATE = 'widgets/tagcloud.html'

    def __init__(self, max=None, show_title=False):
        self.tags = Tag.objects.get_cloud(max)
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Tag Cloud')


class PostArchiveSummary(Widget):
    """
    Show the last n months/years/days with posts.
    """

    NAME = 'get_post_archive_summary'
    TEMPLATE = 'widgets/post_archive_summary.html'

    def __init__(self, detail='months', limit=6, show_title=False):
        self.__dict__.update(Post.objects.get_archive_summary(detail, limit))
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Post Archive Summary')


class LatestPosts(Widget):
    """
    Show the latest n posts.
    """

    NAME = 'get_latest_posts'
    TEMPLATE = 'widgets/latest_posts.html'

    def __init__(self, limit=5, show_title=False):
        self.posts = Post.objects.latest(limit).all()
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Latest Posts')



class LatestComments(Widget):
    """
    Show the latest n comments.
    """

    NAME = 'get_latest_comments'
    TEMPLATE = 'widgets/latest_comments.html'

    def __init__(self, limit=5, show_title=False, ignore_blocked=False):
        self.comments = Comment.objects. \
            latest(limit, ignore_blocked=ignore_blocked).all()
        self.show_title = show_title

    @staticmethod
    def get_display_name():
        return _('Latest Comments')


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
