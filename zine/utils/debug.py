# -*- coding: utf-8 -*-
"""
    zine.utils.debug
    ~~~~~~~~~~~~~~~~

    This module provides various debugging helpers.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
from zine.application import url_for


_body_end_re = re.compile(r'</\s*(body|html)(?i)')


def render_query_table(queries):
    """Renders a nice table of all queries in the page."""
    stylesheet = url_for('core/shared', filename='debug.css')
    result = [u'<style type="text/css">@import url(%s)</style>' % stylesheet,
              u'<div class="_database_debug_table"><ul>']
    for statement, parameters, start, end in queries:
        result.append(u'<li><pre>%s</pre><strong>took %.3f ms</strong></li>' % (
            statement,
            (end - start) * 1000
        ))
    result.append(u'</ul></div>')
    return u'\n'.join(result)


def inject_query_info(request, response):
    """Injects the collected queries into the response."""
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
