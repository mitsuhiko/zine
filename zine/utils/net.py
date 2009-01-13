# -*- coding: utf-8 -*-
"""
    zine.utils.net
    ~~~~~~~~~~~~~~

    This module implements various network related functions and among
    others a minimal urllib implementation that supports timeouts.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from cStringIO import StringIO
import os
import urlparse
import socket
import httplib

from werkzeug import Response, Headers

from zine.application import Response
from zine.utils.datastructures import OrderedDict
from zine.utils.exceptions import ZineException


#: default timeout is two seconds to not slow down the system
#: too much.  Nice websites answer in that time.
DEFAULT_TIMEOUT = 2


def open_url(url, data=None, timeout=DEFAULT_TIMEOUT, **kwargs):
    """This function parses the URL and opens the connection.  The
    following protocols are supported:

    -   `http`
    -   `https`
    """
    parts = urlparse.urlsplit(url)
    handler = _url_handlers.get(parts.scheme)
    if handler is None:
        raise URLError('unsupported URL schema %r' % parts.scheme)
    if isinstance(data, basestring):
        data = StringIO(data)
    obj = handler(parts, timeout, **kwargs)
    return obj.open(data)


def create_connection(address, timeout=DEFAULT_TIMEOUT):
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
        except error, msg:
            if sock is not None:
                sock.close()

    raise error, msg


def find_content_length(data_or_fp):
    try:
        return len(data_or_fp)
    except TypeError:
        try:
            return os.fstat(data_or_fp.fileno().st_size)
        except (AttributeError, OSError):
            pass


class NetException(ZineException):
    pass


class CannotSendRequest(NetException):
    pass


class BadStatusLine(NetException):
    pass


class URLError(NetException):
    pass


class URLHandler(object):

    default_port = 0

    def __init__(self, parsed_url, timeout=DEFAULT_TIMEOUT):
        self.parsed_url = parsed_url
        self.timeout = timeout
        self.closed = False
        self._socket = None
        self._buffer = []

    @property
    def addr(self):
        """The address tuple."""
        netloc = self.parsed_url.netloc
        if netloc.startswith('['):
            host_end = netloc.find(']')
            if host_end < 0:
                raise URLError('invalid ipv6 address')
            host = netloc[1:host_end]
            port = netloc[host_end + 2:]
        else:
            pieces = netloc.split(':', 1)
            if len(pieces) == 1:
                host = pieces[0]
                port = None
            else:
                host, port = pieces
        if not port:
            port = self.default_port
        else:
            try:
                port = int(port)
            except ValueError:
                raise URLError('not a valid port number')
        return host, port

    @property
    def host_string(self):
        host, port = self.addr
        try:
            host = host.encode('ascii')
        except UnicodeError:
            host = host.encode('idna')
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
        return urlparse.urlunsplit(self.parsed_url)

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
        try:
            if hasattr(data, 'read'):
                while 1:
                    s = data.read(8192)
                    if not s:
                        break
                    self.socket.sendall(s)
            else:
                self.socket.sendall(data)
        except socket.error, v:
            if v[0] == 32: # Broken pipe
                self.close()
            raise

    def send_buffered(self, data):
        if hasattr(data, 'read'):
            data = data.read()
        self._buffer.append(data)

    def send_buffer(self):
        buffer = ''.join(self._buffer)
        del self._buffer[:]
        self.send(buffer)

    def open(self, data=None):
        """Return a response object."""
        return Response()


class HTTPHandler(URLHandler):
    """Opens HTTP connections."""
    default_port = 80
    http_version = '1.1'

    STATE_IDLE, STATE_SENDING, STATE_SENT = range(3)

    def __init__(self, parsed_url, timeout=DEFAULT_TIMEOUT,
                 method=None):
        URLHandler.__init__(self, parsed_url, timeout)
        self.headers = Headers()
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
        path = self.parsed_url.path or '/'
        if self.parsed_url.query:
            path += '?' + self.parsed_url.query
        self.send_buffered('%s %s HTTP/%s\r\n' % (self._method, str(path),
                                                  self.http_version))
        self.send_buffered('\r\n'.join('%s: %s' % item for item in
                           self.headers.to_list()) + '\r\n\r\n')
        if isinstance(data, basestring):
            self.send_buffered(data)
            data = None
        self.send(data)
        self._state = self.STATE_SENT

    def open(self, data=None):
        # if no method is set switch between GET and POST based on
        # the data.  This is for example the case if the URL was
        # opened with open_url().
        if self._method is None:
            if data:
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
            content_length = find_content_length(data)
            if content_length is not None:
                self.headers['Content-Length'] = content_length

        self.send_request(data)
        return HTTPResponse(self)


class HTTPSHandler(HTTPHandler):
    """Opens HTTPS connections."""
    default_port = 443

    def __init__(self, parsed_url, timeout=DEFAULT_TIMEOUT,
                 default_method=None, key_file=None,
                 cert_file=None):
        HTTPHandler.__init__(self, parsed_url, timeout, default_method)
        self.key_file = key_file
        self.cert_file = cert_file

    def connect(self):
        try:
            # 2.6 and higher
            from ssl import wrap_socket
        except ImportError:
            # 2.4 and 2.5
            from httplib import FakeSocket
            def wrap_socket(sock, key, cert):
                ssl = socket.ssl(sock, key, cert)
                return FakeSocket(sock, ssl)
        return wrap_socket(HTTPHandler.connect(self),
                           self.key_file, self.cert_file)


class HTTPResponse(Response):

    def __init__(self, http_handler):
        self._socket = http_handler.socket
        resp = httplib.HTTPResponse(self._socket,
                                    method=http_handler._method)
        resp.begin()
        headers = resp.getheaders()
        def make_iterable():
            while 1:
                data = resp.read(8092)
                if not data:
                    break
                yield data
        Response.__init__(self, make_iterable(), resp.status, headers)
        self._httplib_resp = resp
        if resp.will_close:
            self.close()

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
