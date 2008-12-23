# -*- coding: utf-8 -*-
"""
    zine.utils.http
    ~~~~~~~~~~~~~~~

    Various HTTP related helpers.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from urlparse import urlparse, urljoin

from werkzeug import redirect as _redirect
from werkzeug.exceptions import BadRequest

from zine.application import get_application, get_request, url_for
from zine.utils import local


def check_external_url(app, url):
    """Check if a URL is on the application server and return the canonical
    URL (eg: it externalizes a passed in path)
    """
    blog_url = app.cfg['blog_url']
    check_url = urljoin(blog_url)
    if urlparse(blog_url)[:2] != urlparse(check_url)[:2]:
        raise ValueError('The URL %s is not on the same server' % check_url)
    return check_url


def get_redirect_target(invalid_targets=(), request=None):
    """Check the request and get the redirect target if possible.
    If not this function returns just `None`.
    """
    if request is None:
        request = get_request()
    check_target = request.values.get('_redirect_target') or \
                   request.args.get('next') or \
                   request.environ.get('HTTP_REFERER')

    # if there is no information in either the form data
    # or the wsgi environment about a jump target we have
    # to use the target url
    if not check_target:
        return

    blog_url = request.app.cfg['blog_url']
    blog_parts = urlparse(blog_url)
    check_parts = urlparse(urljoin(blog_url, check_target))

    # if the jump target is on a different server we probably have
    # a security problem and better try to use the target url.
    if blog_parts[:2] != check_parts[:2]:
        return

    # if the jump url is the same url as the current url we've had
    # a bad redirect before and use the target url to not create a
    # infinite redirect.
    current_parts = urlparse(urljoin(blog_url, request.path))
    if check_parts[:5] == current_parts[:5]:
        return

    # if the `check_target` is one of the invalid targets we also
    # fall back.
    for invalid in invalid_targets:
        if check_parts[:5] == urlparse(urljoin(blog_url, invalid))[:5]:
            return

    return check_target


def make_external_url(path):
    """Return an external url for the given path."""
    return urljoin(get_application().cfg['blog_url'], path.lstrip('/'))


def redirect(url, code=302, allow_external_redirect=False):
    """Return a redirect response.  Like Werkzeug's redirect but this
    one checks for external redirects too.  If a redirect to an external
    target was requested `BadRequest` is raised unless
    `allow_external_redirect` was explicitly set to `True`.
    """
    # leading slashes are ignored, if we redirect to "/foo" or "foo"
    # does not matter, in both cases we want to be below our blog root.
    url = url.lstrip('/')

    if not allow_external_redirect:
        #: check if the url is on the same server
        #: and make it an external one
        try:
            url = check_external_url(get_application(), url)
        except ValueError:
            raise BadRequest()
    return _redirect(url, code)


def redirect_to(*args, **kwargs):
    """Temporarily redirect to an URL rule."""
    # call werkzeug's redirect directly and not the redirect() function
    # from this module because it will strip leading slashes this function
    # returns and thus generate wrong redirects.
    return _redirect(url_for(*args, **kwargs))


def redirect_back(*args, **kwargs):
    """Redirect back to the page we are comming from or the URL
    rule given.
    """
    target = get_redirect_target()
    if target is None:
        target = url_for(*args, **kwargs)
    # call werkzeug's redirect directly and not the redirect() function
    # from this module because it will strip leading slashes this function
    # returns and thus generate wrong redirects.
    return _redirect(target)


class RequestLocal(object):
    """All attributes on this object are request local and deleted after the
    request finished. The request local object itself must be stored somewhere
    in a global context and never deleted.
    """

    def __init__(self, **vars):
        self.__dict__.update(_vars=vars)
        for key, value in vars.iteritems():
            if value is None:
                value = lambda: None
            vars[key] = value

    @property
    def _storage(self):
        return local.request_locals.setdefault(id(self), {})

    def __getattr__(self, name):
        if name not in self._vars:
            raise AttributeError(name)
        if name not in self._storage:
            self._storage[name] = self._vars[name]()
        return self._storage[name]

    def __setattr__(self, name, value):
        if name not in self._vars:
            raise AttributeError(name)
        self._storage[name] = value
