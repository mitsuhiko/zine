# -*- coding: utf-8 -*-
"""
    zine.utils.pagination
    ~~~~~~~~~~~~~~~~~~~~~

    Pagination helpers.

    :copyright: Copyright 2008 by Armin Ronacher
    :license: GNU GPL.
"""
import math


class Pagination(object):
    """Pagination helper."""

    _skip_theme_defaults = False

    def __init__(self, endpoint, page, per_page, total, url_args=None):
        self.endpoint = endpoint
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = int(math.ceil(self.total / float(self.per_page)))
        self.url_args = url_args or {}
        self.necessary = self.pages > 1

    def generate(self, **options):
        from zine.application import url_for, get_application, \
             DEFAULT_THEME_SETTINGS

        if self._skip_theme_defaults:
            settings = DEFAULT_THEME_SETTINGS
        else:
            settings = get_application().theme.settings

        def _getopt(name):
            if name in options:
                value = options.pop(name)
                if value is not None:
                    return value
            return settings['pagination.' + name]
        normal = _getopt('normal')
        active = _getopt('active')
        commata = _getopt('commata')
        ellipsis = _getopt('ellipsis')
        threshold = _getopt('threshold')
        left_threshold = _getopt('left_threshold')
        right_threshold = _getopt('right_threshold')
        prev_link = _getopt('prev_link')
        next_link = _getopt('next_link')
        gray_prev_link = _getopt('gray_prev_link')
        gray_next_link = _getopt('gray_next_link')
        if options:
            raise TypeError('generate() got an unexpected keyword '
                            'argument %r' % iter(options).next())

        was_ellipsis = False
        result = []
        prev = None
        next = None
        get_link = lambda x: url_for(self.endpoint, page=x, **self.url_args)

        for num in xrange(1, self.pages + 1):
            if num == self.page:
                was_ellipsis = False
            if num - 1 == self.page:
                next = num
            if num + 1 == self.page:
                prev = num
            if num <= left_threshold or \
               num > self.pages - right_threshold or \
               abs(self.page - num) < threshold:
                if result and result[-1] != ellipsis:
                    result.append(commata)
                link = get_link(num)
                template = num == self.page and active or normal
                result.append(template % {
                    'url':      link,
                    'page':     num
                })
            elif not was_ellipsis:
                was_ellipsis = True
                result.append(ellipsis)

        if next_link:
            if next is not None:
                result.append(u' <a href="%s">%s</a>' %
                              (get_link(next), _(u'Next »')))
            elif gray_next_link:
                result.append(u' <span class="disabled">%s</span>' %
                              _(u'Next »'))
        if prev_link:
            if prev is not None:
                result.insert(0, u'<a href="%s">%s</a> ' %
                              (get_link(prev), _(u'« Previous')))
            elif gray_prev_link:
                result.insert(0, u'<span class="disabled">%s</span> ' %
                              _(u'« Previous'))

        return u''.join(result)


class AdminPagination(Pagination):
    """Admin pagination.  Works like the normal pagination with the difference
    that the settings from the theme do not affect the display.
    """
    _skip_theme_defaults = True
