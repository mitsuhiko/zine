# -*- coding: utf-8 -*-
"""
    zine.utils.debug
    ~~~~~~~~~~~~~~~~

    This module provides various debugging helpers.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
import sys

from werkzeug import escape

from zine.application import url_for


_body_end_re = re.compile(r'</\s*(body|html)(?i)')


def find_calling_context(skip=2):
    """Finds the calling context."""
    frame = sys._getframe(skip)
    while frame.f_back is not None:
        name = frame.f_globals.get('__name__')
        if name and name.startswith('zine.'):
            funcname = frame.f_code.co_name
            if 'self' in frame.f_locals:
                funcname = '%s.%s of %s' % (
                    frame.f_locals['self'].__class__.__name__,
                    funcname,
                    hex(id(frame.f_locals['self']))
                )
            return '%s:%s (%s)' % (
                frame.f_code.co_filename,
                frame.f_lineno,
                funcname
            )
        frame = frame.f_back
    return '<unknown>'


def render_query_table(queries):
    """Renders a nice table of all queries in the page."""
    total = 0
    stylesheet = url_for('core/shared', filename='debug.css')
    result = [u'<style type="text/css">@import url(%s)</style>' % stylesheet,
              u'<div class="_database_debug_table"><ul>']
    for statement, parameters, start, end, calling_context in queries:
        total += (end - start)
        result.append(u'<li><pre>%s</pre><div class="detail"><em>%s</em> | '
                      u'<strong>took %.3f ms</strong></div></li>' % (
            statement,
            escape(calling_context),
            (end - start) * 1000
        ))
    result.append(u'<li><strong>%d queries in %.2f ms</strong></ul></div>' % (
        len(queries),
        total * 1000
    ))
    return u'\n'.join(result)


def inject_query_info(request, response):
    """Injects the collected queries into the response."""
    if not request.queries:
        return
    debug_info = render_query_table(request.queries).encode(response.charset)

    body = response.data
    match = _body_end_re.search(body)
    if match is not None:
        pos = match.start()
        response.data = body[:pos] + debug_info + body[pos:]
    else:
        response.data = body + debug_info
    if 'content-length' in response.headers:
        response.headers['content-length'] = len(response.data)
