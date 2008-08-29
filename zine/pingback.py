# -*- coding: utf-8 -*-
"""
    zine.pingback
    ~~~~~~~~~~~~~

    This module implements the pingback API and a function to emit pingbacks
    to different blogs.  The implementation here is a `Pingback 1.0`_
    implementation, compatible to the Pingback specification by Ian Hickson.

    .. _Pingback 1.0: http://www.hixie.ch/specs/pingback/pingback-1.0

    Note that pingback support is implemented in the `Zine` core and
    can't be removed.  You can however disable it in the configuration if
    you want.  Plugins can hook into the pingback system by registering
    a callback for an URL endpoint using `app.add_pingback_endpoint` during
    the application setup.

    Important
    =========

    Due to a broken design for trackback we will *never* support trackbacks
    in the `Zine` core.  Neither do we handle incoming trackbacks, nor
    do we emit trackbacks.


    :copyright: Copyright 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import re
import urllib2
import socket
from urlparse import urljoin
from xmlrpclib import ServerProxy, Fault
from werkzeug.routing import RequestRedirect, NotFound
from werkzeug import escape, unescape
from zine.api import get_request, get_application, url_for, db, _
from zine.models import Post, Comment
from zine.utils.xml import XMLRPC, strip_tags


_title_re = re.compile(r'<title>(.*?)</title>(?i)')
_pingback_re = re.compile(r'<link rel="pingback" href="([^"]+)" ?/?>(?i)')
_chunk_re = re.compile(r'\n\n|<(?:p|div|h\d)[^>]*>')


class PingbackError(Exception):
    """Raised if the remote server caused an exception while pingbacking.
    This is not raised if the pingback function is unable to locate a
    remote server.
    """

    def __init__(self, fault_code):
        self.fault_code = fault_code
        Exception.__init__(self, fault_code)

    @property
    def ignore_silently(self):
        return self.fault_code in (17, 33, 48, 49)

    @property
    def description(self):
        return {
            16: _('source URL does not exist'),
            17: _('The source URL does not contain a link to the target URL'),
            32: _('The specified target URL does not exist'),
            33: _('The specified target URL cannot be used as a target'),
            48: _('The pingback has already been registered'),
            49: _('Access Denied')
        }.get(self.fault_code, _('An unknown server error (%s) occoured') %
              self.fault_code)


def pingback(source_uri, target_uri):
    """Try to notify the server behind `target_uri` that `source_uri`
    points to `target_uri`.  If that fails an `PingbackError` is raised.
    """
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(2)
    try:
        try:
            url = urllib2.urlopen(target_uri)
        except:
            return False
    finally:
        socket.setdefaulttimeout(old_timeout)

    try:
        pingback_uri = url.info()['X-Pingback']
    except KeyError:
        match = _pingback_re.search(url.read())
        if match is None:
            raise PingbackError(33)
        pingback_uri = unescape(match.group(1))
    rpc = ServerProxy(pingback_uri)
    try:
        return rpc.pingback.ping(source_uri, target_uri)
    except Fault, e:
        raise PingbackError(e.faultCode)
    except:
        raise PingbackError(32)


def handle_pingback_request(source_uri, target_uri):
    """This method is exported via XMLRPC as `pingback.ping` by the
    pingback API.
    """
    app = get_application()

    # we only accept pingbacks for links below our blog URL
    blog_url = app.cfg['blog_url']
    if not blog_url.endswith('/'):
        blog_url += '/'
    if not target_uri.startswith(blog_url):
        raise Fault(32, 'The specified target URL does not exist.')
    path_info = target_uri[len(blog_url):]

    # next we check if the source URL does indeed exist
    try:
        url = urllib2.urlopen(source_uri)
    except urllib2.HTTPError:
        raise Fault(16, 'The source URL does not exist.')

    # now it's time to look up our url endpoint for the target uri.
    # if we have one we check if that endpoint is listening for pingbacks.
    while 1:
        try:
            endpoint, values = app.url_adapter.match(path_info)
        except RequestRedirect, e:
            path_info = e.new_url
        except NotFound, e:
            raise Fault(33, 'The specified target URL does not exist.')
        else:
            break

    if endpoint not in app.pingback_endpoints:
        raise Fault(33, 'The specified target URL does not accept pingbacks.')

    # now we have the endpoint and the values and can dispatch our pingback
    # request to the endpoint handler
    handler = app.pingback_endpoints[endpoint]

    # the handler can still decide not to support pingbacks and return a
    # fault code and fault message as tuple.  otherwise none.
    rv = handler(url, target_uri, **values)
    if rv is not None:
        raise Fault(*rv)

    # return some debug info
    return u'\n'.join((
        'endpoint: %r',
        'values: %r',
        'path_info: %r',
        'source_uri: %s',
        'target_uri: %s',
        'handler: %r'
    )) % (endpoint, values, path_info, source_uri, target_uri, handler)


def get_excerpt(url_info, url_hint, body_limit=1024 * 512):
    """Get an excerpt from the given `url_info` (the object returned by
    `urllib2.urlopen` or a string for a URL).  `url_hint` is the URL which
    will be used as anchor for the excerpt.  The return value is a tuple
    in the form ``(title, body)``.  If one of the two items could not be
    calculated it will be `None`.
    """
    if isinstance(url_info, basestring):
        url_info = urllib2.urlopen(url_info)
    contents = url_info.read(body_limit)
    title_match = _title_re.search(contents)
    title = title_match and strip_tags(title_match.group(1)) or None

    link_re = re.compile(r'<a[^>]+?"\s*%s\s*"[^>]*>(.*?)</a>(?is)' %
                         re.escape(url_hint))
    for chunk in _chunk_re.split(contents):
        match = link_re.search(chunk)
        if not match:
            continue
        before = chunk[:match.start()]
        after = chunk[match.end():]
        raw_body = '%s\0%s' % (strip_tags(before).replace('\0', ''),
                               strip_tags(after).replace('\0', ''))
        body_match = re.compile(r'(?:^|\b)(.{0,120})\0(.{0,120})\b') \
                       .search(raw_body)
        if body_match:
            break
    else:
        return (title, None)

    before, after = body_match.groups()
    link_text = strip_tags(match.group(1))
    if len(link_text) > 60:
        link_text = link_text[:60] + u'…'

    bits = before.split()
    bits.append(link_text)
    bits.extend(after.split())
    return title, u'[…] %s […]' % u' '.join(bits)


def inject_header(f):
    """Decorate a view function with this function to automatically set the
    `X-Pingback` header if the status code is 200.
    """
    def oncall(*args, **kwargs):
        rv = f(*args, **kwargs)
        if rv.status_code == 200:
            rv.headers['X-Pingback'] = url_for('services/pingback',
                                               _external=True)
        return rv
    oncall.__name__ = f.__name__
    oncall.__module__ = f.__module__
    oncall.__doc__ = f.__doc__
    return oncall


def pingback_post(url_info, target_uri, year, month, day, slug):
    """This is the pingback handler for `zine.views.blog.show_post`."""
    post = Post.objects.get_by_timestamp_and_slug(year, month, day, slug)
    if post is None or not post.pings_enabled:
        return 33, 'no such post'
    elif not post.can_access():
        return 49, 'access denied'
    title, excerpt = get_excerpt(url_info, target_uri)
    if not title:
        return 17, 'no title provided'
    elif not excerpt:
        return 17, 'no useable link to target'
    old_pingback = Comment.objects.filter(
        (Comment.is_pingback == True) &
        (Comment.www == url_info.url)
    ).first()
    if old_pingback:
        return 48, 'pingback has already been registered'
    excerpt = escape(excerpt)
    Comment(post, title, '', url_info.url, u'<p>%s</p>' % escape(excerpt),
            is_pingback=True, submitter_ip=get_request().remote_addr,
            parser='plain')
    db.commit()


# the pingback service the application registers on creation
service = XMLRPC()
service.register_function(handle_pingback_request, 'pingback.ping')

# a dict of default pingback endpoints (non plugin endpoints)
# these are used as defaults for pingback endpoints on startup
endpoints = {
    'blog/show_post':       pingback_post
}
