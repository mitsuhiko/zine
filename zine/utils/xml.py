"""
    zine.utils
    ~~~~~~~~~~

    This module implements XML-related functions and classes.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: BSD
"""
import re
import sys
from htmlentitydefs import name2codepoint
from SimpleXMLRPCServer import SimpleXMLRPCDispatcher

from werkzeug import escape, import_string, BaseResponse
from werkzeug.contrib.atom import AtomFeed as BaseAtomFeed


_entity_re = re.compile(r'&([^;]+);')
_striptags_re = re.compile(r'(<!--.*?-->|<[^>]*>)')


#: a dict of html entities to codepoints. This includes the problematic
#: &apos; character.
_html_entities = name2codepoint.copy()
_html_entities['apos'] = 39
del name2codepoint


def replace_entities(string):
    """Replace HTML entities in a string:

    >>> replace_entities('foo &amp; bar &raquo; foo')
    u'foo & bar \\xbb foo'
    """
    def handle_match(m):
        name = m.group(1)
        if name in _html_entities:
            return unichr(_html_entities[name])
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


class XMLRPC(object, SimpleXMLRPCDispatcher):
    """A XMLRPC dispatcher that uses our request and response objects.  It
    also works around a problem with Python 2.4 / 2.5 compatibility and
    registers the introspection functions automatically.
    """

    def __init__(self, no_introspection=False):
        if sys.version_info[:2] < (2, 5):
            SimpleXMLRPCDispatcher.__init__(self)
        else:
            SimpleXMLRPCDispatcher.__init__(self, False, 'utf-8')
        if not no_introspection:
            self.register_introspection_functions()

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
