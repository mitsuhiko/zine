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
import re
import inspect
from os import path
from textpress.api import *
from textpress.models import Post, Tag, Comment
from textpress.utils import CSRFProtector

from jinja import nodes


_format_re = re.compile(r'(?<!%)%s')
_instruction_re = re.compile(r'\{\{|\}\}|\{%|%\}')


def jinja_repr(obj):
    if obj is None:
        return 'none'
    elif obj in (True, False):
        return obj and 'true' or 'false'
    elif isinstance(obj, basestring):
        return repr(unicode(obj))[1:]
    else:
        return repr(obj)


class WidgetManager(object):
    """
    Interface to the '_widgets.html' overlay.
    """

    def __init__(self, app, filename='_widgets.html'):
        self.widgets = []
        self.manageable = True
        self.default = False
        self.filename = filename
        self.app = app
        if not app.theme.overlay_exists(filename):
            self.default = True
            return
        tree = app.theme.parse_overlay(filename)
        if not tree.body:
            return

        def consume_html():
            data = data_pieces.pop()
            if data.strip():
                data = data.replace('%%', '%').strip('\n')
                if self.widgets and self.widgets[-1][0] == 'HTML':
                    self.widgets[-1][1]['html'] += '\n' + data
                else:
                    self.widgets.append(('HTML', {'html': data}))

        for node in tree.body:
            # with jinja 1.2 onwards all expressions are children
            # of text nodes. In the worst case the text is just "%"
            # and the only expression a child. but always a text node.
            if not isinstance(node, nodes.Text):
                self.manageable = False
                return
            data_pieces = _format_re.split(node.text)
            data_pieces.reverse()
            consume_html()
            for expr in node.variables:
                if not isinstance(expr, nodes.CallExpression) or \
                   not isinstance(expr.node, nodes.NameExpression) or \
                   expr.dyn_args or expr.dyn_kwargs:
                    self.manageable = False
                    return

                widget_name = expr.node.name
                if widget_name not in app.widgets:
                    continue
                argnames = app.widgets[widget_name].list_arguments()
                if len(argnames) < len(expr.args):
                    continue

                args = []
                kwargs = {}
                for name, arg in zip(argnames, expr.args):
                    if not isinstance(arg, nodes.ConstantExpression):
                        self.manageable = False
                        return
                    kwargs[name] = arg.value
                for name, arg in expr.kwargs:
                    if not isinstance(arg, nodes.ConstantExpression):
                        self.manageable = False
                        return
                    kwargs[name] = arg.value
                self.widgets.append((expr.node.name, kwargs))
                consume_html()


    def revert_to_default(self):
        """
        Revert to the theme defaults (removes overlay)
        """
        self.app.theme.remove_overlay(self.filename)

    def save(self):
        """
        Save the data as overlay.
        """
        buffer = []
        for name, args in self.widgets:
            if name == 'HTML':
                if not args or not args['html'].strip():
                    continue
                data = args['html']
                if _instruction_re.search(data) is not None:
                    data = u'{%% raw %%}%s{%% endraw %%}' % data
                buffer.append(data)
            else:
                buffer.append(u'{{ %s(%s) }}' % (
                    name,
                    u', '.join(u'%s=%s' % (
                        name,
                        jinja_repr(arg)
                    ) for name, arg in sorted(args.items()))
                ))
        self.app.theme.set_overlay(self.filename, u'\n'.join(buffer))


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
    def configure_widget(initial_args, req):
        return None, None

    def __unicode__(self):
        return render_template(self.TEMPLATE, widget=self)


class HTMLWidget(Widget):
    """
    Special widget for normal HTML data.
    """

    NAME = 'HTML'

    @staticmethod
    def get_display_name():
        return _('HTML')

    @staticmethod
    def configure_widget(initial_args, req):
        error = None
        args = initial_args.copy()
        if req.method == 'POST':
            args['html'] = req.form.get('html', '')
        return args, render_template('/admin/widgets/html.html', form=args)

    def __init__(self, html=u''):
        self.html = html

    def __unicode__(self):
        return self.html


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

    @staticmethod
    def configure_widget(initial_args, req):
        args = form = initial_args.copy()
        error = None
        if req.method == 'POST':
            args['max'] = max = req.form.get('max', '')
            if not max:
                args['max'] = None
            elif not max.isdigit():
                error = _('Maximum number of tags must be empty '
                          'or a number.')
            else:
                args['max'] = int(max)
            args['show_title'] = req.form.get('show_title') == 'yes'
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

    NAME = 'get_post_archive_summary'
    TEMPLATE = 'widgets/post_archive_summary.html'

    @staticmethod
    def get_display_name():
        return _('Post Archive Summary')

    @staticmethod
    def configure_widget(initial_args, req):
        args = form = initial_args.copy()
        errors = []
        if req.method == 'POST':
            args['detail'] = detail = req.form.get('detail')
            if detail not in ('years', 'months', 'days'):
                errors.append(_('Detail must be years, months or days.'))
            args['limit'] = limit = req.form.get('limit')
            if not limit:
                args['limit'] = None
            elif not limit.isdigit():
                errors.append(_('Limit must be omited or a valid number.'))
            else:
                args['limit'] = int(limit)
            args['show_title'] = req.form.get('show_title') == 'yes'
        if errors:
            args = None
        return args, render_template('admin/widgets/post_archive_summary.html',
            errors=errors,
            form=form
        )

    def __init__(self, detail='months', limit=6, show_title=False):
        self.__dict__.update(Post.objects.get_archive_summary(detail, limit))
        self.show_title = show_title


class LatestPosts(Widget):
    """
    Show the latest n posts.
    """

    NAME = 'get_latest_posts'
    TEMPLATE = 'widgets/latest_posts.html'

    @staticmethod
    def get_display_name():
        return _('Latest Posts')

    def __init__(self, limit=5, show_title=False):
        self.posts = Post.objects.get_latest(limit)
        self.show_title = show_title


class LatestComments(Widget):
    """
    Show the latest n comments.
    """

    NAME = 'get_latest_comments'
    TEMPLATE = 'widgets/latest_comments.html'

    @staticmethod
    def get_display_name():
        return _('Latest Comments')

    def __init__(self, limit=5, show_title=False):
        self.comments = Comment.objects.get_latest(limit)
        self.show_title = show_title


all_widgets = [HTMLWidget, TagCloud, PostArchiveSummary, LatestPosts,
               LatestComments]
