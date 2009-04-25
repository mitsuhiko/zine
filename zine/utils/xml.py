"""
    zine.utils
    ~~~~~~~~~~

    This module implements XML-related functions and classes.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
import sys
import xmlrpclib
from htmlentitydefs import name2codepoint

from werkzeug import escape, import_string, BaseResponse
from werkzeug.contrib.atom import AtomFeed as BaseAtomFeed

from zine.utils import log


_entity_re = re.compile(r'&([^;]+);')
_striptags_re = re.compile(r'(<!--.*?-->|<[^>]*>)')


#: the xml namespace
XML_NS = 'http://www.w3.org/XML/1998/namespace'


#: a dict of html entities to codepoints. This includes the problematic
#: &apos; character.
html_entities = name2codepoint.copy()
html_entities['apos'] = 39
del name2codepoint


def replace_entities(string):
    """Replace HTML entities in a string:

    >>> replace_entities('foo &amp; bar &raquo; foo')
    u'foo & bar \\xbb foo'
    """
    def handle_match(m):
        name = m.group(1)
        if name in html_entities:
            return unichr(html_entities[name])
        if name[:2] in ('#x', '#X'):
            try:
                return unichr(int(name[2:], 16))
            except ValueError:
                return u''
        elif name.startswith('#'):
            try:
                return unichr(int(name[1:]))
            except ValueError:
                return u''
        return u''
    return _entity_re.sub(handle_match, string)


def to_text(element):
    """Convert an element into text only information."""
    result = []

    def _to_text(element):
        result.append(element.text or u'')
        for child in element.iterchildren():
            _to_text(child)
        result.append(element.tail or u'')

    _to_text(element)
    return u''.join(result)


def strip_tags(s, normalize_whitespace=True):
    """Remove HTML tags in a text.  This also resolves entities."""
    s = _striptags_re.sub('', s)
    s = replace_entities(s)
    if normalize_whitespace:
        s = ' '.join(s.split())
    return s


def generate_rsd(app):
    """Generate the RSD definition for this application apis."""
    from zine.application import url_for
    document = __import__('xml.dom.minidom', None, None, ['']).Document()
    root = document.appendChild(document.createElement('rsd'))
    root.setAttribute('version', '1.0')
    root.setAttribute('xmlns', 'http://archipelago.phrasewise.com/rsd')
    service = root.appendChild(document.createElement('service'))

    attributes = [('engineName', 'Zine'),
                  ('engineLink', 'http://zine.pocoo.org/'),
                  ('homePageLink', url_for('blog/index', _external=True))]

    for attr, value in attributes:
        service.appendChild(document.createElement(attr)) \
               .appendChild(document.createTextNode(value))

    apis = service.appendChild(document.createElement('apis'))
    for name, (blog_id, preferred, endpoint) in app.apis.iteritems():
        element = apis.appendChild(document.createElement('api'))
        element.setAttribute('name', name)
        element.setAttribute('blogID', str(blog_id))
        element.setAttribute('preferred', preferred and 'true' or 'false')
        element.setAttribute('apiLink', url_for(endpoint, _external=True))

    return document.toxml('utf-8')


def dump_xml(obj):
    """Dump an JSON dumpable structure as simple XML."""
    def _inner_dump(obj):
        if obj is None:
            return '<null/>'
        elif obj is True:
            return '<true/>'
        elif obj is False:
            return '<false/>'
        elif isinstance(obj, basestring):
            if isinstance(obj, str):
                obj = obj.decode('utf-8', 'ignore')
            return u'<string value="%s"/>' % (escape(obj, True))
        elif isinstance(obj, (int, long)):
            return '<integer value="%s"/>' % str(obj)
        elif isinstance(obj, float):
            return '<float value="%s"/>' % str(obj)
        elif isinstance(obj, dict):
            return u'<dict>%s</dict>' % ''.join(u'<item><key>%s</key>'
                                                u'<value>%s</value></item>'
                                                % (_inner_dump(key),
                                                   _inner_dump(value)) for
                                                key, value in obj.iteritems())
        elif hasattr(obj, '__iter__'):
            return u'<list>%s</list>' % u''.join(map(obj, _inner_dump))
        else:
            return u'<invalid/>'
    return (u'<?xml version="1.0" encoding="utf-8"?>\n'
            u'<envelope>%s</envelope>' % _inner_dump(obj)).encode('utf-8')


class AtomFeed(BaseAtomFeed):
    """A helper class that creates Atom feeds."""
    import zine
    default_generator = ('Zine', zine.__url__, zine.__version__)
    del zine


class XMLRPC(object):
    """A XMLRPC dispatcher that uses our request and response objects.  It
    also works around a problem with Python 2.4 / 2.5 compatibility and
    registers the introspection functions automatically.
    """
    charset = 'utf-8'

    def __init__(self, no_introspection=False, allow_none=True):
        self.no_introspection = no_introspection
        self.allow_none = allow_none
        self.funcs = {}
        if not no_introspection:
            self.register_introspection_functions()

    def register_function(self, function, name=None):
        """Register a function to respond to XMLRPC requests."""
        if name is None:
            name = function.__name__
        self.funcs[name] = function
        return function

    def register_introspection_functions(self):
        """Register all introspection functions."""
        self.funcs.update({
            'system.methodHelp':        self._system_method_help,
            'system.methodSignature':   self._system_method_signature,
            'system.listMethods':       self._system_list_methods
        })

    def _system_list_methods(self):
        """system.listMethods() => ['add', 'subtract', 'multiple']

        Returns a list of the methods supported by the server.
        """
        return sorted(self.funcs.keys())

    def _system_method_signature(self, method_name):
        """Unsupported."""
        return 'signatures not supported'

    def _system_method_help(self, method_name):
        """system.methodHelp('add') => "Adds two integers together"

        Returns a string containing documentation for the specified method.
        """
        if method_name not in self.funcs:
            return ''
        import inspect
        print self.funcs
        return inspect.getdoc(self.funcs[method_name])

    def _dispatch(self, method, args):
        """Dispatches the XML-RPC method.

        XML-RPC calls are forwarded to a registered function that
        matches the called XML-RPC method name. If no such function
        exists then the call is forwarded to the registered instance,
        if available.
        """
        func = self.funcs.get(method)
        if func is None:
            raise xmlrpclib.Fault(1, 'method "%s" is not supported' % method)
        return func(*args)

    def _marshaled_dispatch(self, data):
        """Dispatches an XML-RPC method from marshalled (XML) data.

        XML-RPC methods are dispatched from the marshalled (XML) data
        using the _dispatch method and the result is returned as
        marshalled data.
        """
        try:
            params, method = xmlrpclib.loads(data)
            response = xmlrpclib.dumps((self._dispatch(method, params),),
                                       methodresponse=True, allow_none=True,
                                       encoding=self.charset)
        except xmlrpclib.Fault, fault:
            response = xmlrpclib.dumps(fault, allow_none=self.allow_none,
                                       encoding=self.charset)
        except:
            exc_type, exc_value, tb = exc_info = sys.exc_info()
            log.exception('Exception in XMLRPC request:', 'xmlrpc', exc_info)
            response = xmlrpclib.dumps(
                xmlrpclib.Fault(1, '%s:%s' % (exc_type, exc_value)),
                encoding=self.charset, allow_none=self.allow_none
            )

        return response

    def handle_request(self, request):
        if request.method == 'POST':
            response = self._marshaled_dispatch(request.data)
            return BaseResponse(response, mimetype='application/xml')
        return BaseResponse('\n'.join((
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">',
            '<title>XMLRPC Interface</title>',
            '<h1>XMLRPC Interface</h1>',
            '<p>This URL provides an XMLRPC interface.  You have to '
            'connect to it using an XMLRPC client.</p>'
        )), 405, [('Allow', 'POST'), ('Content-Type', 'text/html')])

    def __call__(self, request):
        return self.handle_request(request)


class Namespace(object):
    """Attribute access to this class returns fully qualified names for the
    given URI.

    >>> ns = Namespace('http://zine.pocoo.org/')
    >>> ns.foo
    u'{http://zine.pocoo.org/}foo'
    """

    def __init__(self, uri):
        self._uri = unicode(uri)

    def __getattr__(self, name):
        return u'{%s}%s' % (self._uri, name)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return self._uri
