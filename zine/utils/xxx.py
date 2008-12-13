"""
    zine.utils.xxx
    ~~~~~~~~~~~~~~

    We don't know how to properly name this module, but that stuff in here
    should be replaced with something saner anyway. It currently uses hidden
    HTML form fields to implement e.g. redirects.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import md5
import sha
import os
from random import random
from urlparse import urlparse, urljoin
from tempfile import NamedTemporaryFile, gettempdir
from time import time, sleep

from werkzeug import escape, url_quote
from werkzeug.exceptions import Forbidden
from werkzeug.contrib.reporterstream import BaseReporterStream

from zine.application import get_request, get_application
from zine.utils.http import get_redirect_target


class HiddenFormField(object):
    """Baseclass for special hidden fields."""

    def get_hidden_field(self):
        pass

    def __unicode__(self):
        return make_hidden_fields(self)


class IntelligentRedirect(HiddenFormField):
    """An intelligent redirect tries to go back to the page the user
    is comming from or redirects to the url rule provided when called.

    Like the `CSRFProtector` it uses hidden form information.

    Example usage::

        redirect = IntelligentRedirect()
        if request.method == 'POST':
            ...
            return redirect('admin/index') # go back to the admin index or the
                                           # page we're comming from.
        return render_response(..., hidden_data=make_hidden_fields(redirect))

    If you don't want to combine it with other hidden fields you can ignore
    the `make_hidden_fields` call and pass the intelligent redirect instance
    directly to the template.  Rendering it results in a hidden form field.

    The intelligent redirect is much slower than a normal redirect because
    it tests for quite a few things. Don't use it if you don't have to.
    """

    def __init__(self):
        self.request = get_request()
        self.invalid_targets = []

    def add_invalid(self, *args, **kwargs):
        """Add an invalid target. Invalid targets are URLs we don't want to
        visit again. For example if a post is deleted from the post edit page
        it's a bad idea to redirect back to the edit page because in that
        situation the edit page would return a page not found.
        """
        from zine.application import url_for
        self.invalid_targets.append(url_for(*args, **kwargs))

    def get_redirect_target(self):
        """Check the request and get the redirect target if possible.
        If not this function returns just `None`.
        """
        check_target = self.request.values.get('_redirect_target') or \
                       self.request.args.get('next') or \
                       self.request.environ.get('HTTP_REFERER')

        # if there is no information in either the form data
        # or the wsgi environment about a jump target we have
        # to use the target url
        if not check_target:
            return

        blog_url = self.request.app.cfg['blog_url']
        blog_parts = urlparse(blog_url)
        check_parts = urlparse(urljoin(blog_url, check_target))

        # if the jump target is on a different server we probably have
        # a security problem and better try to use the target url.
        if blog_parts[:2] != check_parts[:2]:
            return

        # if the jump url is the same url as the current url we've had
        # a bad redirect before and use the target url to not create a
        # infinite redirect.
        current_parts = urlparse(urljoin(blog_url, self.request.path))
        if check_parts[:5] == current_parts[:5]:
            return

        # if the `check_target` is one of the invalid targets we also
        # fall back.
        for invalid in self.invalid_targets:
            if check_parts[:5] == urlparse(urljoin(blog_url, invalid))[:5]:
                return

        return check_target

    def get_redirect_target(self):
        return get_redirect_target(self.invalid_targets, self.request)

    def __call__(self, *args, **kwargs):
        """Trigger the redirect."""
        from zine.application import url_for
        from zine.utils.http import redirect
        target = self.get_redirect_target()
        if target is None:
            target = url_for(*args, **kwargs)
        return redirect(target)

    def get_hidden_field(self):
        target = self.get_redirect_target()
        if target is None:
            return
        return '_redirect_target', target


class CSRFProtector(HiddenFormField):
    """This class is used in the admin panel to avoid CSRF attacks.

    In the controller code just create a new instance of the CSRFProtector
    and pass it the request object.  The instance then provides a method
    called `assert_safe` that must be called before the action takes place.

    Example::

        protector = CSRFProtector()
        if request.method == 'POST':
            protector.assert_safe()
            ...

        return render_response(..., hidden_data=make_hidden_fields(protector))

    Additionally you have to add some small code to the templates.  If you
    want to protect POST requests it's enough to do ``{{ protector }}``
    (assuming protector is the CSRFProtector object from the controller
    function) or ``<a href="...?{{ protector.url_value|e }}">`` if you want
    to protect a GET request.

    If you don't want or have to combine it with other hidden fields
    such as the intelligent redirect stuff you can also pass the protector
    instance to the template directly, rendering it prints out the hidden
    field automatically. This also allows you to access the `url_value`
    attribute that allows CSRF protection for GET requests.
    """

    def __init__(self):
        self.request = request = get_request()
        self.token = sha.new('%s|%s|%s|%s' % (
            request.path,
            get_application().cfg['secret_key'],
            request.user.user_id,
            request.user.is_somebody
        )).hexdigest()

    @property
    def url_value(self):
        return '_csrf_check_token=%s' % url_quote(self.token)

    def assert_safe(self):
        if self.request.values.get('_csrf_check_token') != self.token:
            raise Forbidden()

    def get_hidden_field(self):
        return '_csrf_check_token', self.token


class StreamReporter(HiddenFormField, BaseReporterStream):
    """This class can wrap `wsgi.input` so that we get upload notifications
    during uploading.

    Zine also provides a service called `get_upload_info` that returns
    the information for AJAX scripts.

    This class doesn't work with wsgiref because it can only handle one
    request at the time.  If you want to test this with the standalone server
    you have to use paste or others.

    The stream reporter uses a file in the instance folder to map all uploads
    from the ids to their temporary files with the stream status.  For
    performance reasons we do not use the database.

    Note that you have to instanciate this reporter before any component
    read anything from the request object regarding post data (.files, .post,
    .values) or the instanciation won't have an effect.  This is especially
    problematic if you emit an event before instanciating the reporter and
    plugins might access form data.

    XXX: no locking and no cleanup in some situations.
    XXX: validation for transport id that came from a URL variable
    XXX: get rid of this class and use some sort of flash-uploader.
    """

    def __init__(self, transport_id=None):
        self.request = request = get_request()

        if transport_id is None:
            transport_id = request.args.get('_transport_id')
        if transport_id is None:
            transport_id = StreamReporter.generate_id()
        self.transport_id = transport_id
        self.start_time = int(time())

        self._fp = NamedTemporaryFile(prefix='_zine_upload_')
        BaseReporterStream.__init__(self, request.environ, 1024 * 50)
        request.environ['wsgi.input'] = self
        self._stream_registered = False

    @staticmethod
    def generate_id():
        return md5.new('%s|%s' % (time(), random())).hexdigest()

    @staticmethod
    def _get_manager():
        app = get_application()
        return os.path.join(gettempdir(), '_zine_streams_' +
                            sha.new(app.instance_folder).hexdigest()[2:10])

    @staticmethod
    def add_active_stream(stream):
        """Add a new stream to the stream index."""
        f = file(StreamReporter._get_manager(), 'a')
        try:
            f.write('%s:%s\n' % (
                stream.transport_id,
                stream._fp.name
            ))
        finally:
            f.close()

    @staticmethod
    def remove_active_stream(stream):
        """Remove a stream from the stream index."""
        filename = StreamReporter._get_manager()
        if not os.path.exists(filename):
            return

        f = file(filename, 'r')
        try:
            lines = [x.strip() for x in f]
        finally:
            f.close()

        for idx, line in enumerate(lines):
            if line.startswith(stream.transport_id + ':'):
                del lines[idx]

        if not lines:
            os.remove(filename)
        else:
            f = file(filename, 'w')
            try:
                for line in lines:
                    f.write(line + '\n')
            finally:
                f.close()

    @staticmethod
    def get_stream_info(transport_id):
        """Get all the stream info for the given transport or return
        `None` if the stream does not exist."""
        filename = StreamReporter._get_manager()
        transport_id = transport_id.splitlines()[0]

        if not os.path.exists(filename):
            return

        f = file(filename)
        try:
            for line in f:
                if line.startswith(transport_id + ':'):
                    _, transport_filename = line.strip().split(':', 1)
                    break
            else:
                return
        finally:
            f.close()

        f = None
        for _ in xrange(40):
            try:
                f = file(transport_filename)
            except IOError:
                sleep(0.001)
        if f is None:
            return

        try:
            return tuple(map(int, f.read().split(';')[0].split(':')[:4]))
        finally:
            f.close()

    def processed(self):
        if self.pos >= self.length:
            self._fp.close()
            StreamReporter.remove_active_stream(self)
        elif not self._stream_registered:
            StreamReporter.add_active_stream(self)
            self._stream_registered = True
        else:
            self._fp.seek(0)
            self._fp.write('%d:%d:%d:%d;\n' % (
                self.start_time,
                int(time()),
                self.pos,
                self.length
            ))
            self._fp.flush()

    @property
    def url_value(self):
        return '_transport_id=%s' % url_quote(self.transport_id)

    def get_hidden_field(self):
        return '_transport_id', self.transport_id

    def __del__(self):
        try:
            # we cannot access globals any more in some situations
            # so we call the cleanup function from the self object.
            self.remove_active_stream(self)
        except:
            pass


def make_hidden_fields(*fields):
    """Create some hidden form data for fields."""
    buf = []
    for field in fields:
        args = field.get_hidden_field()
        if args is not None:
            buf.append(u'<input type="hidden" name="%s" value="%s">' %
                       (escape(args[0]), escape(args[1])))
    return u'\n'.join(buf)
