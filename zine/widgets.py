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
from zine.application import render_template
from zine.database import pages as pages_table
from zine.models import Post, Tag, Comment, Page


class Widget(object):
    """Baseclass for all the widgets out there!"""

    #: the name of the widget when called from a template.  This is also used
    #: if widgets are configured from the admin panel to have a unique
    #: identifier.
    name = None

    #: name of the template for this widget. Please prefix those template
    #: names with an underscore to mark it as partial. The widget is available
    #: in the template as `widget`.
    template = None

    def __unicode__(self):
        """Render the template."""
        return render_template(self.template, widget=self)

    def __str__(self):
        return unicode(self).encode('utf-8')


class TagCloud(Widget):
    """A tag cloud. What else?"""

    name = 'tagcloud'
    template = 'widgets/tagcloud.html'

    def __init__(self, max=None, show_title=False):
        self.tags = Tag.objects.get_cloud(max)
        self.show_title = show_title


class PostArchiveSummary(Widget):
    """Show the last n months/years/days with posts."""

    name = 'post_archive_summary'
    template = 'widgets/post_archive_summary.html'

    def __init__(self, detail='months', limit=6, show_title=False):
        self.__dict__.update(Post.objects.get_archive_summary(detail, limit))
        self.show_title = show_title


class LatestPosts(Widget):
    """Show the latest n posts."""

    name = 'latest_posts'
    template = 'widgets/latest_posts.html'

    def __init__(self, limit=5, show_title=False):
        self.posts = Post.objects.latest(limit).all()
        self.show_title = show_title


class LatestComments(Widget):
    """Show the latest n comments."""

    name = 'latest_comments'
    template = 'widgets/latest_comments.html'

    def __init__(self, limit=5, show_title=False, ignore_blocked=False):
        self.comments = Comment.objects. \
            latest(limit, ignore_blocked=ignore_blocked).all()
        self.show_title = show_title


class PagesNavigation(Widget):
    """A little navigation widget."""

    name = 'pages_navigation'
    template = 'widgets/pages_navigation.html'

    def __init__(self):
        pages = Page.objects.query
        to_append = pages.filter_by(navigation_pos=None)
        self.pages = pages.filter(pages_table.c.navigation_pos!=None) \
            .order_by(pages_table.c.navigation_pos.asc()).all()
        self.pages.extend(to_append.all())


#: list of all core widgets
all_widgets = [TagCloud, PostArchiveSummary, LatestPosts, LatestComments,
               PagesNavigation]
