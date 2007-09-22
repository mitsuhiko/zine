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

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from textpress.application import render_template, render_response
from textpress.api import _
from textpress.models import Post, Tag, Comment
from textpress.utils import CSRFProtector


def render_widget_response(template, widget, **context):
    """
    Like render response but especially for widgets.
    """
    return render_response(template, widget=widget, **context)


class Widget(object):
    """
    Baseclass for all the widgets out there!
    """

    #: the name of the widget when called from a template.  This is also used
    #: if widgets are configured from the admin panel to have a unique
    #: identifier.
    NAME = None

    #: name of the template for this widget. Please prefix those template
    #: names with an underscore to mark it as partial. The widget is available
    #: in the template as `widget`.
    TEMPLATE = None

    #: True if the widget is configurable
    HAS_CONFIGURATION = False

    def configure_widget(self, req):
        """
        If the widget has a configuration and 
        """

    def __unicode__(self):
        return render_template(self.TEMPLATE, widget=self)


class TagCloud(Widget):
    """
    A tag cloud. What else?
    """

    NAME = 'get_tag_cloud'
    TEMPLATE = '_tagcloud.html'
    HAS_CONFIGURAION = True

    def __init__(self, max=None):
        self.tags = Tag.objects.get_cloud(max)

    def configure_widget(self, req):
        form = {'max': u''}
        csrf_protector = CSRFProtector()
        if req.method == 'POST':
            form['max'] = max = req.form.get('max')
            if not max or max.isdigit():
                return (max,), {}
            flash(_('Maximum number of tags must be numeric.'), 'error')
        return render_widget_response('admin/widgets/tagcloud.html', self,
            form=form,
            csrf_protector=csrf_protector
        )


class PostArchiveSummary(Widget):
    """
    Show the last n months/years/days with posts.
    """

    NAME = 'get_post_archive_summary'
    TEMPLATE = '_post_archive_summary.html'

    def __init__(self, detail='months', limit=6):
        self.__dict__.update(Post.objects.get_archive_summary(detail, limit))


class LatestPosts(Widget):
    """
    Show the latest n posts.
    """

    NAME = 'get_latest_posts'
    TEMPLATE = '_latest_posts.html'

    def __init__(self, limit=5):
        self.posts = Post.objects.get_latest(limit)


class LatestComments(Widget):
    """
    Show the latest n comments.
    """

    NAME = 'get_latest_comments'
    TEMPLATE = '_latest_comments.html'

    def __init__(self, limit=5):
        self.comments = Comment.objects.get_latest(limit)


all_widgets = [TagCloud, PostArchiveSummary, LatestPosts, LatestComments]
