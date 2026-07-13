# -*- coding: utf-8 -*-
"""
    zine.utils.net
    ~~~~~~~~~~~~~~

    This module implements various network related functions and among
    others a minimal urllib implementation that supports timeouts.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from io import BytesIO
import os
import urllib.parse
import socket
import ssl
import http.client

from werkzeug.datastructures import Headers
from werkzeug.utils import cached_property

from zine._compat import url_decode
from zine.application import Response, get_application
from zine.utils.exceptions import ZineException


def open_url(url, data=None, timeout=None,
             allow_internal_requests=True, **kwargs):
    """This function parses the URL and opens the connection.  The
    following protocols are supported:

    -   `http`
    -   `https`

    Per default requests to Zine itself trigger an internal request.  This
    can be disabled by setting `allow_internal_requests` to False.
    """
    app = get_application()
    if timeout is None:
        timeout = (app.cfg['default_network_timeout']
                   if app is not None else 30)
    parts = urllib.parse.urlsplit(url)
    if app is not None:
        blog_url = urllib.parse.urlsplit(app.cfg['blog_url'])
        if allow_internal_requests and \
           parts.scheme in ('http', 'https') and \
           blog_url.netloc == parts.netloc and \
           parts.path.startswith(blog_url.path):
            path = parts.path[len(blog_url.path):].lstrip('/')
            method = kwargs.pop('method', None)
            if method is None:
                method = data is not None and 'POST' or 'GET'
            make_response = lambda *a: URLResponse(url, *a)
            return app.perform_subrequest(path,
                                          url_decode(parts.query),
                                          method, data, timeout=timeout,
                                          response_wrapper=make_response,
                                          **kwargs)
    handler = _url_handlers.get(parts.scheme)
    if handler is None:
        raise URLError('unsupported URL schema %r' % parts.scheme)
    if isinstance(data, str):
        data = BytesIO(data.encode('utf-8'))
    obj = None
    try:
        obj = handler(parts, timeout, **kwargs)
        return obj.open(data)
    except Exception as error:
        if obj is not None:
            obj.close()
        if isinstance(error, NetException):
            raise
        raise NetException(
            '%s: %s' % (error.__class__.__name__, str(error))
        ) from error


def create_connection(address, timeout=30):
    """Connect to address and return the socket object."""
    msg = "getaddrinfo returns an empty list"
    host, port = address

    for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sa)
            return sock
        except socket.error as msg:
            if sock is not None:
                sock.close()

    raise ConnectionError(msg)


def get_content_length(data_or_fp):
    """Try to get the content length from the given string or file
    pointer.  If the length can't be determined the return value
    is None.
    """
    try:
        return len(data_or_fp)
    except TypeError:
        try:
            position = data_or_fp.tell()
            data_or_fp.seek(0, os.SEEK_END)
            length = data_or_fp.tell() - position
            data_or_fp.seek(position)
            return length
        except (AttributeError, OSError, ValueError):
            pass
        try:
            position = data_or_fp.tell()
            return os.fstat(data_or_fp.fileno()).st_size - position
        except (AttributeError, OSError, ValueError):
            pass


class NetException(ZineException):
    pass


class CannotSendRequest(NetException):
    pass


class BadStatusLine(NetException):
    pass


class URLError(NetException):
    pass


class ConnectionError(NetException):
    pass


class URLHandler(object):

    default_port = 0

    def __init__(self, parsed_url, timeout=30):
        self.parsed_url = parsed_url
        self.timeout = timeout
        self.closed = False
        self._socket = None
        self._buffer = []

    @property
    def addr(self):
        """The address tuple."""
        host = self.parsed_url.hostname
        if not host:
            raise URLError('URL does not contain a host')
        try:
            port = self.parsed_url.port
        except ValueError:
            raise URLError('not a valid port number')
        return host, port or self.default_port

    @property
    def host_string(self):
        host, port = self.addr
        try:
            host.encode('ascii')
        except UnicodeError:
            host = host.encode('idna').decode('ascii')
        if ':' in host:
            host = '[%s]' % host
        if port != self.default_port:
            host = '%s:%d' % (host, port)
        return host

    @property
    def host(self):
        return self.addr[0]

    @property
    def port(self):
        return self.addr[1]

    @property
    def url(self):
        return urllib.parse.urlunsplit(self.parsed_url)

    @property
    def socket(self):
        if self._socket is None:
            if self.closed:
                raise TypeError('handler closed')
            self._socket = self.connect()
        return self._socket

    def connect(self):
        return create_connection(self.addr, self.timeout)

    def close(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self.closed = True

    def send(self, data):
        if self._buffer:
            self.send_buffer()
        if data is None:
            return
        if isinstance(data, str):
            data = data.encode('utf-8')
        try:
            if hasattr(data, 'read'):
                while 1:
                    s = data.read(8192)
                    if not s:
                        break
                    if isinstance(s, str):
                        s = s.encode('utf-8')
                    self.socket.sendall(s)
            else:
                self.socket.sendall(data)
        except OSError as error:
            if error.errno == 32:  # Broken pipe
                self.close()
            raise

    def send_buffered(self, data):
        if hasattr(data, 'read'):
            data = data.read()
        if isinstance(data, str):
            data = data.encode('latin-1')
        self._buffer.append(data)

    def send_buffer(self):
        buffer = b''.join(self._buffer)
        del self._buffer[:]
        self.send(buffer)

    def open(self, data=None):
        """Return a `URLResponse` object."""
        return Response()


class HTTPHandler(URLHandler):
    """Opens HTTP connections."""
    default_port = 80
    http_version = '1.1'

    STATE_IDLE, STATE_SENDING, STATE_SENT = list(range(3))

    def __init__(self, parsed_url, timeout=30, method=None, headers=None):
        URLHandler.__init__(self, parsed_url, timeout)
        self.headers = Headers(headers)
        self._state = self.STATE_IDLE
        self._method = method

    @property
    def method(self):
        return self._method or 'GET'

    def send(self, data):
        if self._state == self.STATE_IDLE:
            self._state = self.STATE_SENDING
        return URLHandler.send(self, data)

    def send_request(self, data):
        path = urllib.parse.quote(
            self.parsed_url.path or '/',
            safe="/%:@!$&'()*+,;=-._~",
        )
        if self.parsed_url.query:
            query = urllib.parse.quote(
                self.parsed_url.query,
                safe="=&?/%:@!$'()*+,;~-._",
            )
            path += '?' + query
        self.send_buffered('%s %s HTTP/%s\r\n' % (self._method, str(path),
                                                  self.http_version))
        self.send_buffered('\r\n'.join('%s: %s' % item for item in
                           self.headers.to_wsgi_list()) + '\r\n\r\n')
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.send(data)
        self._state = self.STATE_SENT

    def open(self, data=None):
        # if no method is set switch between GET and POST based on
        # the data.  This is for example the case if the URL was
        # opened with open_url().
        if self._method is None:
            if data is not None:
                self._method = 'POST'
            else:
                self._method = 'GET'

        if self._state != self.STATE_IDLE:
            raise CannotSendRequest()

        if self.http_version == '1.1':
            if 'host' not in self.headers:
                self.headers['Host'] = self.host_string
            if 'accept-encoding' not in self.headers:
                self.headers['Accept-Encoding'] = 'identity'

        if 'content-length' not in self.headers:
            content_length = get_content_length(data)
            if content_length is not None:
                self.headers['Content-Length'] = content_length

        self.send_request(data)
        return HTTPResponse(self)


class HTTPSHandler(HTTPHandler):
    """Opens HTTPS connections."""
    default_port = 443

    def __init__(self, parsed_url, timeout=30, method=None, key_file=None,
                 cert_file=None, headers=None, ssl_context=None):
        HTTPHandler.__init__(self, parsed_url, timeout, method, headers)
        self.key_file = key_file
        self.cert_file = cert_file
        self.ssl_context = ssl_context

    def connect(self):
        context = self.ssl_context or ssl.create_default_context()
        if self.cert_file is not None:
            context.load_cert_chain(self.cert_file, self.key_file)
        return context.wrap_socket(
            HTTPHandler.connect(self), server_hostname=self.host
        )


class URLResponse(Response):

    def __init__(self, url, body, status=200, headers=None):
        Response.__init__(self, body, status, headers)
        self.url = url

    @cached_property
    def stream(self):
        return BytesIO(self.get_data())


class HTTPResponse(URLResponse):

    def __init__(self, http_handler):
        self._socket = http_handler.socket
        resp = http.client.HTTPResponse(self._socket,
                                    method=http_handler._method)
        resp.begin()
        headers = resp.getheaders()
        def make_iterable():
            while 1:
                data = resp.read(8092)
                if not data:
                    break
                yield data
        URLResponse.__init__(self, http_handler.url, make_iterable(),
                             resp.status, headers)
        self._httplib_resp = resp

    def close(self):
        Response.close(self)
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._httplib_resp is not None:
            self._httplib_resp.close()
            self._httplib_resp = None


_url_handlers = {
    'http':         HTTPHandler,
    'https':        HTTPSHandler
}
