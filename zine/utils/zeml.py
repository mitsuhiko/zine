# -*- coding: utf-8 -*-
"""
    zine.utils.zeml
    ~~~~~~~~~~~~~~~

    This module implements ZEML (Zine Extensible Markup Language), a simple
    HTML inspired markup language that plugins can extend.

    The rules for ZEML are documented as part of the parser.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
import struct
import cPickle as pickle
from copy import deepcopy
from StringIO import StringIO as UniStringIO
from cStringIO import StringIO
from urlparse import urlparse

from werkzeug import escape

from zine.i18n import _
from zine.utils import log
from zine.utils.text import wrap as wraptext
from zine.utils.datastructures import OrderedDict


_tag_name_re = re.compile(r'([\w.-]+)\b(?u)')
_attribute_re = re.compile(r'\s*([\w.-]+)(?:\s*=\s*(".*?"|'
                           "'.*?'|[^\s>]*))?(?us)")
_tag_end_re = re.compile(r'\s*>(?u)')
_entity_re = re.compile(r'&([^;]+);')
_entity_re = re.compile(r'&([^;]+);')
_paragraph_re = re.compile(r'(\s*?\n){2,}')
_whitespace_re = re.compile(ur'\s+(?u)')
_autoparagraphed_elements = set(['div', 'blockquote'])

_entities = {
    'Aacute':       u'\xc1',        'aacute':       u'\xe1',
    'Acirc':        u'\xc2',        'acirc':        u'\xe2',
    'acute':        u'\xb4',        'AElig':        u'\xc6',
    'aelig':        u'\xe6',        'agrave':       u'\xe0',
    'Agrave':       u'\xc0',        'alefsym':      u'\u2135',
    'Alpha':        u'\u0391',      'alpha':        u'\u03b1',
    'AMP':          u'&',           'amp':          u'&',
    'and':          u'\u2227',      'ang':          u'\u2220',
    'apos':         u"'",           'aring':        u'\xe5',
    'Aring':        u'\xc5',        'asymp':        u'\u2248',
    'Atilde':       u'\xc3',        'atilde':       u'\xe3',
    'auml':         u'\xe4',        'Auml':         u'\xc4',
    'bdquo':        u'\u201e',      'Beta':         u'\u0392',
    'beta':         u'\u03b2',      'brvbar':       u'\xa6',
    'bull':         u'\u2022',      'cap':          u'\u2229',
    'ccedil':       u'\xe7',        'Ccedil':       u'\xc7',
    'cedil':        u'\xb8',        'cent':         u'\xa2',
    'Chi':          u'\u03a7',      'chi':          u'\u03c7',
    'circ':         u'\u02c6',      'clubs':        u'\u2663',
    'cong':         u'\u2245',      'copy':         u'\xa9',
    'COPY':         u'\xa9',        'crarr':        u'\u21b5',
    'cup':          u'\u222a',      'curren':       u'\xa4',
    'dagger':       u'\u2020',      'Dagger':       u'\u2021',
    'dArr':         u'\u21d3',      'darr':         u'\u2193',
    'deg':          u'\xb0',        'delta':        u'\u03b4',
    'Delta':        u'\u0394',      'diams':        u'\u2666',
    'divide':       u'\xf7',        'Eacute':       u'\xc9',
    'eacute':       u'\xe9',        'ecirc':        u'\xea',
    'Ecirc':        u'\xca',        'egrave':       u'\xe8',
    'Egrave':       u'\xc8',        'empty':        u'\u2205',
    'emsp':         u'\u2003',      'ensp':         u'\u2002',
    'Epsilon':      u'\u0395',      'epsilon':      u'\u03b5',
    'equiv':        u'\u2261',      'Eta':          u'\u0397',
    'eta':          u'\u03b7',      'ETH':          u'\xd0',
    'eth':          u'\xf0',        'euml':         u'\xeb',
    'Euml':         u'\xcb',        'euro':         u'\u20ac',
    'exist':        u'\u2203',      'fnof':         u'\u0192',
    'forall':       u'\u2200',      'frac12':       u'\xbd',
    'frac14':       u'\xbc',        'frac34':       u'\xbe',
    'frasl':        u'\u2044',      'gamma':        u'\u03b3',
    'Gamma':        u'\u0393',      'ge':           u'\u2265',
    'gt':           u'>',           'GT':           u'>',
    'harr':         u'\u2194',      'hArr':         u'\u21d4',
    'hearts':       u'\u2665',      'hellip':       u'\u2026',
    'iacute':       u'\xed',        'Iacute':       u'\xcd',
    'Icirc':        u'\xce',        'icirc':        u'\xee',
    'iexcl':        u'\xa1',        'Igrave':       u'\xcc',
    'igrave':       u'\xec',        'image':        u'\u2111',
    'infin':        u'\u221e',      'int':          u'\u222b',
    'iota':         u'\u03b9',      'Iota':         u'\u0399',
    'iquest':       u'\xbf',        'isin':         u'\u2208',
    'iuml':         u'\xef',        'Iuml':         u'\xcf',
    'Kappa':        u'\u039a',      'kappa':        u'\u03ba',
    'lambda':       u'\u03bb',      'Lambda':       u'\u039b',
    'lang':         u'\u27e8',      'laquo':        u'\xab',
    'lArr':         u'\u21d0',      'larr':         u'\u2190',
    'lceil':        u'\u2308',      'ldquo':        u'\u201c',
    'le':           u'\u2264',      'lfloor':       u'\u230a',
    'lowast':       u'\u2217',      'loz':          u'\u25ca',
    'lrm':          u'\u200e',      'lsaquo':       u'\u2039',
    'lsquo':        u'\u2018',      'lt':           u'<',
    'LT':           u'<',           'macr':         u'\xaf',
    'mdash':        u'\u2014',      'micro':        u'\xb5',
    'middot':       u'\xb7',        'minus':        u'\u2212',
    'Mu':           u'\u039c',      'mu':           u'\u03bc',
    'nabla':        u'\u2207',      'nbsp':         u'\xa0',
    'ndash':        u'\u2013',      'ne':           u'\u2260',
    'ni':           u'\u220b',      'not':          u'\xac',
    'notin':        u'\u2209',      'nsub':         u'\u2284',
    'Ntilde':       u'\xd1',        'ntilde':       u'\xf1',
    'nu':           u'\u03bd',      'Nu':           u'\u039d',
    'Oacute':       u'\xd3',        'oacute':       u'\xf3',
    'Ocirc':        u'\xd4',
    'ocirc':        u'\xf4',        'oelig':        u'\u0153',
    'OElig':        u'\u0152',      'ograve':       u'\xf2',
    'Ograve':       u'\xd2',        'oline':        u'\u203e',
    'omega':        u'\u03c9',      'Omega':        u'\u03a9',
    'omicron':      u'\u03bf',      'Omicron':      u'\u039f',
    'oplus':        u'\u2295',      'or':           u'\u2228',
    'ordf':         u'\xaa',        'ordm':         u'\xba',
    'oslash':       u'\xf8',        'Oslash':       u'\xd8',
    'otilde':       u'\xf5',        'Otilde':       u'\xd5',
    'otimes':       u'\u2297',      'Ouml':         u'\xd6',
    'ouml':         u'\xf6',        'para':         u'\xb6',
    'part':         u'\u2202',      'permil':       u'\u2030',
    'perp':         u'\u22a5',      'Phi':          u'\u03a6',
    'phi':          u'\u03c6',      'Pi':           u'\u03a0',
    'pi':           u'\u03c0',      'piv':          u'\u03d6',
    'plusmn':       u'\xb1',        'pound':        u'\xa3',
    'Prime':        u'\u2033',      'prime':        u'\u2032',
    'prod':         u'\u220f',      'prop':         u'\u221d',
    'Psi':          u'\u03a8',      'psi':          u'\u03c8',
    'QUOT':         u'"',           'quot':         u'"',
    'radic':        u'\u221a',      'rang':         u'\u27e9',
    'raquo':        u'\xbb',        'rarr':         u'\u2192',
    'rArr':         u'\u21d2',      'rceil':        u'\u2309',
    'rdquo':        u'\u201d',      'real':         u'\u211c',
    'reg':          u'\xae',        'REG':          u'\xae',
    'rfloor':       u'\u230b',      'Rho':          u'\u03a1',
    'rho':          u'\u03c1',      'rlm':          u'\u200f',
    'rsaquo':       u'\u203a',      'rsquo':        u'\u2019',
    'sbquo':        u'\u201a',      'Scaron':       u'\u0160',
    'scaron':       u'\u0161',      'sdot':         u'\u22c5',
    'sect':         u'\xa7',        'shy':          u'\xad',
    'Sigma':        u'\u03a3',      'sigma':        u'\u03c3',
    'sigmaf':       u'\u03c2',      'sim':          u'\u223c',
    'spades':       u'\u2660',      'sub':          u'\u2282',
    'sube':         u'\u2286',      'sum':          u'\u2211',
    'sup':          u'\u2283',      'sup1':         u'\xb9',
    'sup2':         u'\xb2',        'sup3':         u'\xb3',
    'supe':         u'\u2287',      'szlig':        u'\xdf',
    'Tau':          u'\u03a4',      'tau':          u'\u03c4',
    'there4':       u'\u2234',      'Theta':        u'\u0398',
    'theta':        u'\u03b8',      'thetasym':     u'\u03d1',
    'thinsp':       u'\u2009',      'THORN':        u'\xde',
    'thorn':        u'\xfe',        'tilde':        u'\u02dc',
    'times':        u'\xd7',        'trade':        u'\u2122',
    'TRADE':        u'\u2122',      'uacute':       u'\xfa',
    'Uacute':       u'\xda',        'uarr':         u'\u2191',
    'uArr':         u'\u21d1',      'Ucirc':        u'\xdb',
    'ucirc':        u'\xfb',        'Ugrave':       u'\xd9',
    'ugrave':       u'\xf9',        'uml':          u'\xa8',
    'upsih':        u'\u03d2',      'upsilon':      u'\u03c5',
    'Upsilon':      u'\u03a5',      'Uuml':         u'\xdc',
    'uuml':         u'\xfc',        'weierp':       u'\u2118',
    'xi':           u'\u03be',      'Xi':           u'\u039e',
    'Yacute':       u'\xdd',        'yacute':       u'\xfd',
    'yen':          u'\xa5',        'yuml':         u'\xff',
    'Yuml':         u'\u0178',      'zeta':         u'\u03b6',
    'Zeta':         u'\u0396',      'zwj':          u'\u200d',
    'zwnj':         u'\u200c'
}


# support for the dumping/loading system
try:
    _struct = struct.Struct
except AttributeError:
    class _struct(object):
        def __init__(self, fmt):
            self.fmt = fmt
            self.size = struct.calcsize(fmt)
        def pack(self, *args):
            return struct.pack(self.fmt, *args)
        def unpack(self, s):
            return struct.unpack(self.fmt, s)
_short_struct = _struct('!H')
_int_struct = _struct('!I')
_long_struct = _struct('!l')
_opcodes = map(intern, 'NISLMRED')
del _struct

_empty_set = frozenset()


def dumps(obj):
    """Dump an element into a string."""
    stream = StringIO()
    dump(obj, stream)
    return stream.getvalue()


def loads(string):
    """Load an element from a string."""
    return load(StringIO(string))


def dump(obj, stream):
    """Dump an element into a stream."""
    def _serialize(obj):
        if obj is None:
            stream.write('N')
        elif isinstance(obj, (int, long)):
            stream.write('I' + _long_struct.pack(obj))
        elif isinstance(obj, basestring):
            obj = unicode(obj).encode('utf-8')
            stream.write('S' + _long_struct.pack(len(obj)) + obj)
        elif type(obj) is list:
            stream.write('L' + _short_struct.pack(len(obj)))
            for item in obj:
                _serialize(item)
        elif type(obj) is Attributes:
            stream.write('M' + _short_struct.pack(len(obj)))
            for key, value in obj.iteritems():
                _serialize(key)
                _serialize(value)
        elif type(obj) is RootElement:
            stream.write('R')
            _serialize(obj.text)
            _serialize(obj.children)
        elif type(obj) is Element:
            stream.write('E')
            _serialize(obj.name)
            _serialize(obj.children)
            _serialize(obj.attributes)
            _serialize(obj.text)
            _serialize(obj.tail)
        elif isinstance(obj, DynamicElement):
            stream.write('D')
            # pickle into a separate stream, then count the length and
            # write that information together with the class name to
            # the stream.  This is done for two purposes:
            #
            # - other applications that do not support pickle have a
            #   chance to resconstruct at least parts of the tree
            # - if the dynamic element is no longer available, the loading
            #   mechanism can recover.
            pickled = StringIO()
            pickle.dump(obj, pickled, 2)
            pickled = pickled.getvalue()
            _serialize('%s.%s' % (
                obj.__class__.__module__,
                obj.__class__.__name__
            ))
            stream.write(_long_struct.pack(len(pickled)))
            stream.write(pickled)
        else:
            raise TypeError('unsupported object %r' % type(obj).__name__)
    return _serialize(obj)


def load(stream):
    """Load an element from a stream.  This function is optimized for
    performance so that no further caching is needed.
    """
    def _load(parent=None, _get=stream.read, _read_struct=lambda s,
              _get=stream.read: s.unpack(_get(s.size))[0]):
        char = _get(1)
        if char is 'N':
            return None
        elif char is 'I':
            return _read_struct(_long_struct)
        elif char is 'S':
            return unicode(_get(_read_struct(_long_struct)), 'utf-8')
        elif char is 'L':
            return [_load(parent) for x in
                    xrange(_read_struct(_short_struct))]
        elif char is 'M':
            return Attributes([(_load(), _load()) for x in
                              xrange(_read_struct(_short_struct))])
        elif char is 'R':
            rv = object.__new__(RootElement)
            rv.text = _load()
            rv.children = _load(rv)
            return rv
        elif char is 'E':
            rv = object.__new__(Element)
            rv.name = _load()
            rv.children = _load(rv)
            rv.attributes = _load()
            rv.text = _load()
            rv.tail = _load()
            rv.parent = parent
            return rv
        elif char is 'D':
            obj_name = _load()
            try:
                rv = pickle.loads(_get(_read_struct(_long_struct)))
            except Exception, e:
                log.exception(_(u'Error when loading dynamic ZEML element. '
                                u'The system ignored the element.  Maybe a '
                                u'disabled plugin caused the problem.'))
                return BrokenElement(obj_name, e)
            rv.parent = parent
            return rv
        raise ValueError('format error')
    return _load()


def dump_parser_data(parser_data):
    out = StringIO()
    dump(len(parser_data), out)
    for key, value in parser_data.iteritems():
        assert isinstance(key, basestring), 'keys must be strings'
        dump(key, out)
        dump(value, out)
    return out.getvalue()


def load_parser_data(value):
    if value is None:
        return {}
    # the extra str() call is for databases like postgres that
    # insist on using buffers for binary data.
    in_ = StringIO(str(value))
    result = {}
    for x in xrange(load(in_)):
        key = load(in_)
        result[key] = load(in_)
    return result


def attach_parents(element):
    """Attach all parents to a tree of elements."""
    def _walk(element):
        for child in element.children:
            child.parent = element
            _walk(child)
    _walk(element)


def _iter_all(elements):
    for element in elements:
        yield element
        for child in _iter_all(element.children):
            yield child


def _query(elements, expr):
    if expr.startswith('/'):
        expr = expr[1:]
    else:
        elements = _iter_all(elements)
    parts = expr.split('/', 1)
    part = parts.pop(0)
    rest = parts and parts.pop() or None

    test = None
    if part.endswith(']'):
        idx = part.index('[')
        expr = part[idx + 1:-1]
        part = part[:idx]
        if '!=' in expr:
            key, value = expr.split('!=', 1)
            test = lambda x: x.attributes.get(key) != value
        elif '~=' in expr:
            key, value = expr.split('~=', 1)
            test = lambda x: value in x.attributes.get(key, '').split()
        elif '=' in expr:
            key, value = expr.split('=', 1)
            test = lambda x: x.attributes.get(key) == value
        else:
            test = lambda x: expr in x.attributes
    elif part[:1] == '#':
        elements = (x for x in elements if x.attributes.get('id') == part[1:])
    elif part != '*':
        elements = (x for x in elements if x.name == part)

    if test is not None:
        elements = (x for x in elements if test(x))

    def traverse():
        for element in elements:
            if rest:
                for n in element.query(rest):
                    yield n
            else:
                yield element
    return QueryResult(traverse())


class QueryResult(object):
    """Represents the result of a query(). You can also further query this
    object.
    """
    __slots__ = ('_gen', '_results')

    def __init__(self, gen):
        self._gen = gen
        self._results = []

    @property
    def first(self):
        """Get the first element."""
        try:
            return self[0]
        except IndexError:
            pass

    @property
    def last(self):
        """Get the last element. This queries all results first so you should
        try to use first() if possible.
        """
        try:
            return self[-1]
        except IndexError:
            pass

    def query(self, expr):
        """Apply the expression on all result elements."""
        return _query(self, expr)

    def _fetchall(self):
        """Used internally to get all items from the generator."""
        if self._gen is not None:
            for item in self:
                pass

    def __getitem__(self, idx):
        """Get a specific result item."""
        if idx < 0:
            self._fetchall()
        if self._gen is None or idx < len(self._results):
            return self._results[idx]
        i = len(self._results)
        for item in self:
            if i == idx:
                return item
            i += 1
        raise IndexError(idx)

    def __len__(self):
        """Fetch all items and return the number of results."""
        self._fetchall()
        return len(self._results)

    def __iter__(self):
        """Iterate over the results."""
        if self._gen is None:
            for item in self._results:
                yield item
        else:
            for item in self._gen:
                self._results.append(item)
                yield item
            self._gen = None

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            list(self)
        )


class Attributes(OrderedDict):
    """An ordered dict for attributes."""

    def get_int(self, key, default=None):
        """Return an attribute as integer."""
        try:
            return int(self[key])
        except (KeyError, ValueError, TypeError):
            return default


class _BaseElement(object):
    """Base class for all elements."""
    __slots__ = ('__weakref__',)

    name = None
    is_dynamic = False
    is_root = False
    text = u''
    tail = u''

    def to_html(self, stream=None):
        """Convert the element to HTML."""
        if stream is None:
            buffer = []
            write = buffer.append
        else:
            write = stream.write
        html_serializer.serialize(self, write)
        if stream is None:
            return u''.join(buffer)

    def to_text(self, simple=False, multiline=True, **options):
        """Convert the element to text."""
        if simple:
            result = [self.text]
            for child in self.children:
                result.append(child.to_text())
                result.append(child.tail)
            return u''.join(result)
        t = Textifier(**options)
        return (multiline and t.multiline or t.oneline)(self)

    def to_pseudoxml(self, level=0, nostrip=False, _result=None):
        """Convert the element to a pseudo-XML representation for debugging."""
        def appendtext(text):
            if nostrip:
                _result.extend(level * '  ' + x for x in self.text.splitlines())
            elif text.strip():
                _result.extend(level * '  ' + x
                               for x in self.text.strip().splitlines())
        return_something = False
        if _result is None:
            return_something = True
            _result = []
        _result.append('%s<%s%s%s>' % (
            level * '  ', self.name, self.attributes and ' ' or '',
            ', '.join("%s=%r" % item for item in self.attributes.items())))
        appendtext(self.text)
        for child in self.children:
            child.to_pseudoxml(level+1, nostrip, _result)
            appendtext(self.tail)
        if return_something:
            return '\n'.join(_result)

    children = property(lambda x: [])
    attributes = property(lambda x: Attributes())
    parent = None

    def __unicode__(self):
        return self.to_html()

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __nonzero__(self):
        return bool(self.children or self.text or self.tail or
                    self.attributes)

    def __eq__(self, other):
        try:
            return self.__class__ is other.__class__ and \
                   self.name == other.name and \
                   self.children == other.children and \
                   self.attributes == other.attributes and \
                   self.text == other.text and \
                   self.tail == other.tail
        except:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def non_blank(self):
        return bool(self.children or self.text.strip() or
                    self.tail.strip() or self.attributes)

    def query(self, expr):
        return _query(self.children, expr)

    def copy(self):
        return deepcopy(self)

    def walk(self):
        yield self
        for child in _iter_all(self.children):
            yield child


class Element(_BaseElement):
    """Instance of this class hold ZEML trees.  The API is heavily influenced
    by ElementTree but not compatible.  Unlike ElementTree, the ZEML element
    structures can hold so-called dynamic elements that execute code on
    unpickling.

    An element has five attributes:

    `name`
        The name of the element as string if the element is named.

    `children`
        A regular list of `Element` or `DynamicElement` objects.

    `attributes`
        An ordered dict of attributes this element has.  If the parser detects
        an element without value (as in ``<option selected>``) it stores
        `None` as value for that key.

    `text`
        The text of the element.

    `tail`
        The tail text for the outer element.  To understand this, look at the
        following example:

        >>> root = parse_zeml("1 <b>2</b> 3")
        >>> root.text
        u'1 '
        >>> root.children[0].text
        u'2'
        >>> root.children[0].tail
        u' 3'
    """
    __slots__ = ('name', 'children', 'text', 'tail', 'attributes', 'parent')

    def __init__(self, name):
        self.name = name
        self.children = []
        self.attributes = Attributes()
        self.text = u''
        self.tail = u''
        self.parent = None

    def __deepcopy__(self, memo):
        rv = Element(self.name)
        rv.children = deepcopy(self.children, memo)
        rv.attributes = deepcopy(self.attributes, memo)
        rv.text = self.text
        rv.tail = self.tail
        rv.parent = deepcopy(self.parent, memo)
        return rv

    def __repr__(self):
        return '<%s %r>' % (type(self).__name__, self.name)


class RootElement(_BaseElement):
    """Wraps all elements."""
    __slots__ = ('text', 'children')
    is_root = True
    is_dynamic = True
    name = '#root'

    def __init__(self):
        self.text = u''
        self.children = []

    def __deepcopy__(self, memo):
        rv = RootElement()
        rv.text = self.text
        rv.children = deepcopy(self.children, memo)
        return rv


class DynamicElement(_BaseElement):
    """A dynamic element.  A dynamic element has a slightly different
    interface than a normal element.  By definition it has only one attribute
    in common with Element, that is the `tail` text.

    The serializer calls the `to_html` method when it wants to display the
    element but subclasses have to override `render()` to not break the tail
    rendering.
    """
    name = '#dynamic'
    is_dynamic = True

    def render(self):
        """Classes have to overide the render method to output something."""
        raise NotImplementedError()

    def to_html(self):
        """Converts the element to HTML."""
        return self.render() + self.tail

    def __nonzero__(self):
        return True

    def __eq__(self, other):
        if self.__class__ is not other.__class__:
            return False
        return self.__getstate__() == other.__getstate__()

    def __getstate__(self):
        rv = dict(self.__dict__)
        rv.pop('parent', None)
        return rv


class BrokenElement(DynamicElement):
    """Displayed as replacement for a broken dynamic element (an alement
    that can't be unpickled).
    """
    name = '#broken'

    def __init__(self, obj_name, error):
        try:
            message = unicode(error)
        except UnicodeError:
            message = str(error).decode('utf-8', 'replace')
        self.obj_name = obj_name
        self.message = message

    def render(self):
        return u'<div class="error"><strong>%s</strong>: %s</div>' % (
            _('Error loading dynamic element %s') % self.obj_name,
            escape(self.message)
        )


class MarkupErrorElement(DynamicElement):
    """Displayed in the place of erroneous markup."""
    name = '#error'

    def __init__(self, message):
        self.message = message

    def render(self):
        return u'<div class="error"><strong>%s</strong>: %s</div>' % (
               _('Error in markup'), escape(self.message))


class HTMLElement(DynamicElement):
    """An element that stores HTML data."""
    name = '#html'

    def __init__(self, value):
        self.value = value

    def render(self):
        return self.value


class _HTMLSerializer(object):
    """This class can serialize ZEML trees into fragmentary HTML4/5.  The
    output should be compatible to both of the standards but not XHTML!
    It will not try to correct broken trees and the behavior of a broken tree
    is completely undefined but won't cause errors that abort the
    serilization.

    Like the loading system it's heavily optimized for performance.
    """

    # elements that must not have a body
    void_elements = frozenset(['base', 'command', 'event-source', 'link',
                               'meta', 'hr', 'br', 'img', 'embed', 'param',
                               'area', 'col', 'input', 'source'])

    #: elements that work like ZEML's isolated elements
    rcdata_elements = set(['noscript', 'style', 'script', 'iframe', 'noembed',
                           'xmp', 'noframes'])

    #: like ZEML's semi-isolated elements
    cdata_elements = set(['title', 'textarea'])

    #: a dict with sets of all boolean attributes on elements
    boolean_attributes = {
        None:           set(['irrelevant']),
        'style':        set(['scoped']),
        'img':          set(['ismap']),
        'audio':        set(['autoplay','controls']),
        'video':        set(['autoplay','controls']),
        'script':       set(['defer', 'async']),
        'details':      set(['open']),
        'datagrid':     set(['multiple', 'disabled']),
        'command':      set(['hidden', 'disabled', 'checked', 'default']),
        'menu':         set(['autosubmit']),
        'fieldset':     set(['disabled', 'readonly']),
        'option':       set(['disabled', 'readonly', 'selected']),
        'optgroup':     set(['disabled', 'readonly']),
        'button':       set(['disabled', 'autofocus']),
        'input':        set(['disabled', 'readonly', 'required', 'autofocus',
                             'checked', 'ismap']),
        'select':       set(['disabled', 'readonly', 'autofocus', 'multiple']),
        'output':       set(['disabled', 'readonly'])
    }

    def serialize_body(self, element, write):
        if not element.is_root:
            rcdata = element.name in self.rcdata_elements
            cdata = element.name in self.cdata_elements
            if rcdata or cdata:
                value = element.text
                if cdata:
                    value = escape(value)
                write(value)
                return
        if element.text:
            write(escape(element.text))
        for child in element.children:
            self.serialize(child, write)

    def serialize(self, element, write):
        if element.is_root:
            self.serialize_body(element, write)
        elif element.is_dynamic:
            write(element.to_html())
        else:
            write(u'<' + element.name)
            if element.attributes:
                boolean_attributes = \
                    self.boolean_attributes[None] | \
                    self.boolean_attributes.get(element.name, _empty_set)
                for key, value in element.attributes.iteritems():
                    if key in boolean_attributes:
                        write(u' ' + key)
                    else:
                        if value is None:
                            value = u''
                        else:
                            value = escape(value, quote=True)
                        write(u' %s="%s"' % (key, value))
            write(u'>')

            if element.name not in self.void_elements:
                self.serialize_body(element, write)
                write(u'</%s>' % element.name)
            if element.tail:
                write(escape(element.tail))


html_serializer = _HTMLSerializer()


def parse_html(string):
    """Parse an HTML fragment into a ZEML tree."""
    def _convert(element, root=False):
        if root:
            result = RootElement()
        else:
            result = Element(element.name)
            result.attributes.update(element.attributes)
        for child in element.childNodes:
            if child.type == 4:
                if result.children:
                    result.children[-1].tail += child.value
                else:
                    result.text += child.value
            # node type 6 are comments, skip them
            elif child.type != 6:
                new_child = _convert(child)
                new_child.parent = result
                result.children.append(new_child)
        return result

    from html5lib import HTMLParser
    return _convert(HTMLParser().parseFragment(string), True)


def parse_zeml(string, reason, extensions=None):
    """Parse a ZEML string into a element tree."""
    p = Parser(string, reason, extensions)
    p.parse()
    attach_parents(p.result)
    return p.result


def sanitize(tree):
    """Sanitize the tree and return it."""
    return Sanitizer().sanitize(tree)


def split_intro(tree):
    """Split a tree into intro and body.  The tree will be modified!"""
    # for intro sections there must be...
    #   - no text before the first element
    #   - the first element must be <intro>
    if tree.text.strip() or not tree.children \
       or tree.children[0].name != 'intro':
        return RootElement(), tree
    child = tree.children.pop(0)
    intro = RootElement()
    intro.text = child.text
    intro.children = child.children
    body = RootElement()
    body.children = tree.children
    if child.tail:
        if intro.children:
            intro.children[-1].tail += child.tail
        else:
            body.text += child.tail
    return intro, body


def inject_implicit_paragraphs(tree):
    """Inject implicit paragraphs into the tree.  This mimicks the WordPress
    automatic paragraph insertion and can be used to import markup from blogs
    like WordPress that use implicit paragraphs.

    This however must not be used for any kind of ZEML trees because it only
    knows some basic rules for regular HTML.
    """
    def joined_text_iter(node):
        text_buf = [node.text]
        node.text = u''

        def flush_text_buf():
            if text_buf:
                text = u''.join(text_buf)
                del text_buf[:]
                if text:
                    return text

        for child in node.children:
            text = flush_text_buf()
            if text is not None:
                yield text
            yield child
            text_buf.append(child.tail)
            child.tail = u''

        text = flush_text_buf()
        if text is not None:
            yield text

    def make_paragraph(children):
        element = Element('p')
        for child in children:
            if isinstance(child, unicode):
                if element.children:
                    element.children[-1].tail += child
                else:
                    element.text += child
            elif child:
                element.children.append(child)
        return element

    def transform(parent):
        for node in parent.children[:]:
            transform(node)
        if not parent.is_root and \
           parent.name not in _autoparagraphed_elements:
            return
        paragraphs = [[]]

        for item in joined_text_iter(parent):
            if isinstance(item, unicode):
                blockiter = iter(_paragraph_re.split(item))
                for block in blockiter:
                    try:
                        is_paragraph = blockiter.next()
                    except StopIteration:
                        is_paragraph = False
                    if block:
                        paragraphs[-1].append(block)
                    if is_paragraph:
                        paragraphs.append([])
            elif item.name in Parser.block_elements:
                paragraphs.extend((item, []))
            else:
                paragraphs[-1].append(item)

        del parent.children[:]
        for paragraph in paragraphs:
            if not isinstance(paragraph, list):
                parent.children.append(paragraph)
            else:
                for item in paragraph:
                    if not isinstance(item, unicode) or item:
                        parent.children.append(make_paragraph(paragraph))
                        break

    transform(tree)
    return tree


class Parser(object):
    """The ZEML parser.  This parser is able to parse the ZEML syntax which is
    heavily influenced by a mixture of real-world and on-the-paper HTML to get
    an easy to read and write markup syntax.

    ZEML always represents fragmentary and never complete documents in the
    sense of HTML.  There is no support for meta elements and similar things by
    definition (but the parser will happily forward you and let you abuse it).

    A ZEML document is build of multiple elements that make a tree of elements.

    An element exists of multiple characteristics:

    -   each element has a name called the `tag`.  During parsing it tells the
        parser how it should deal with the element (void or not, isolated,
        semi isolated, regular).  After parsing it either becomes an HTML
        element with the same name, one or more HTML elements with different
        names if a plugin modifies the structure or a dynamic element that
        no longer shares information with this element.

        Tag names are converted to lowercase on parsing, thus they are case
        insensitive.

    -   each element also can have multiple `attributes`.  Attributes are
        optional key, value pairs after the tag name until the closing ``>``.
        Attributes without value (different from attributes with an empty
        value!) are special in the sense that some tags will treat them as
        flags if present.  (eg `checked` for HTML checkboxes)

    -   Non-void elements can have contents and an end tag that is
        essentially a slash (optionally with the name of the start tag).

    The parser has internal sets and mappings of element rules that inform it
    how to deal with elements.

    The following flags for elements exist:

    `isolated`
        If an element is isolated everything until the end tag is processed
        as raw text.  Nothing in between is specially handled.  This for
        example is the default flag for `script`, `style` and similar
        elements.

    `semi-isolated`
        If an element is semi isolated the same rules as for `isolated` apply
        but entities are expanded.  This is the default flag for elements like
        `textarea`.

    `void`
        If an element is void it means that the parser will never push it onto
        the stack of open elements and directly close it.  Void elements can
        never have children.  This is the default flag for elements like `br`.

    `block`
        Elements are divided into block and inline elements.  Unless an
        element has the block flag it will be handled as inline element.  This
        information is mainly used for breaking rules.

    A more complex topic are breaking rules.  Breaking rules specify implicit
    auto-close rules.  For example, the ZEML markup ``<p>foo<p>bar`` is
    equivalent to ``<p>foo</p><p>bar</p>`` because the `p` element is
    automatically closed by all block tags.

    An important difference between ZEML and HTML is that in ZEML the text
    directly following an element is part of that element.  For example, if you
    have the ZEML markup ``<p>foo<br>bar``, the `bar` text is the tail of the
    `br` element.
    """

    isolated_elements = set(['script', 'style', 'noscript', 'iframe'])
    semi_isolated_elements = set(['textarea'])
    void_elements = set(['br', 'img', 'area', 'hr', 'param', 'input',
                         'embed', 'col'])
    block_elements = set(['div', 'p', 'form', 'ul', 'ol', 'li', 'table', 'tr',
                          'tbody', 'thead', 'tfoot', 'tr', 'td', 'th', 'dl',
                          'dt', 'dd', 'blockquote', 'h1', 'h2', 'h3', 'h4',
                          'h5', 'h6', 'pre'])
    breaking_rules = [
        (['p'], set(['#block'])),
        (['li'], set(['li'])),
        (['td', 'th'], set(['td', 'th', 'tr', 'tbody', 'thead', 'tfoot'])),
        (['tr'], set(['tr', 'tbody', 'thead', 'tfoot'])),
        (['thead', 'tbody', 'tfoot'], set(['thead', 'tbody', 'tfoot'])),
        (['dd', 'dt'], set(['dl', 'dt', 'dd'])),
        (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], set(['#block']))
    ]

    def __init__(self, string, parsing_reason, extensions=None):
        self.string = unicode(string)
        self.parsing_reason = parsing_reason
        self.end = len(self.string)
        self.pos = 0
        self.result = RootElement()
        self.state = 'data'
        self.stack = [self.result]

        self.isolated_elements = self.isolated_elements.copy()
        self.semi_isolated_elements = self.semi_isolated_elements.copy()
        self.void_elements = self.void_elements.copy()
        self.block_elements = self.block_elements.copy()

        breaking_rules = self.breaking_rules
        self.breaking_rules = {}
        for elements, breakers in breaking_rules:
            for element in elements:
                self.breaking_rules[element] = breakers.copy()

        # register all element handlers.
        self.extensions = {}
        for extension in extensions or ():
            if extension.is_isolated:
                self.isolated_elements.add(extension.name)
            if extension.is_void:
                self.void_elements.add(extension.name)
            if extension.broken_by:
                self.breaking_rules[extension.name] = set(extension.broken_by)
            if extension.is_block_level:
                self.block_elements.add(extension.name)
            self.extensions[extension.name] = extension

    @property
    def finished(self):
        """Returns true if the parser finished parsing."""
        return self.pos >= self.end or self.state == 'done'

    @property
    def current(self):
        """The current outermost element."""
        return self.stack[-1]

    @property
    def in_root_tag(self):
        """True if the parser is in the root tag."""
        return len(self.stack) == 1

    def resolve_entities(self, string):
        """This function is called for every string that is written to the
        element tree.  It resolves the known HTML5 entities and numerical
        entities into characters and returns unknown entities as they were
        defined.
        """
        def handle_match(m):
            name = m.group(1)
            if name in _entities:
                return _entities[name]
            try:
                if name[:2] in ('#x', '#X'):
                    return unichr(int(name[2:], 16))
                elif name.startswith('#'):
                    return unichr(int(name[1:]))
            except ValueError:
                pass
            return m.group(0)
        return _entity_re.sub(handle_match, string)

    def is_breaking(self, tag, element):
        """When given a tag and an element object it checks if the tag is
        able to break the element.
        """
        breaking = self.breaking_rules.get(element.name)
        if not breaking:
            return False
        if tag in breaking:
            return True
        return (tag in self.block_elements and
                '#block' or '#inline') in breaking

    def process(self, element):
        """Called after an element is left.  Calls element handlers to
        process them.
        """
        if element.name in self.extensions:
            extension = self.extensions[element.name]
            content = element
            if extension.is_isolated:
                content = element.text
            bad_atts = set(element.attributes).difference(extension.attributes)
            if bad_atts:
                return MarkupErrorElement(
                    _('Invalid attribute given to %s tag: %s') %
                    (extension.name, bad_atts.pop()))
            element = extension.process(element.attributes, content,
                                        self.parsing_reason)
        return element

    def enter(self, tag):
        """Enter the given tag.  This will automatically leave the current
        element if the tag given can break it.
        """
        # if the tag is not nestable and we are directly inside a tag with
        # the same name we pop.
        while self.is_breaking(tag, self.current):
            self.leave(None)
        element = Element(tag)
        self.current.children.append(element)
        if tag not in self.void_elements:
            self.stack.append(element)
        return element

    def leave(self, tag):
        """Leave the tag given or the outermost tag if the tag is None.
        This process is rather complex and defined as follows:

        -   if the tag is not given (None) or the tag has the name of the
            current element this tag is left.  If the tag is not given and
            we are about to leave the root element it does nothing instead.

        -   Otherwise it iterates reverse over the stack of open elements and
            checks for two things.  First of all it stops processing if it
            reaches an element that doesn't have special breaking rules which
            means that it has to be closed explicitly.  If it reaches the
            element named with the tag given it leaves all elements between
            the current one and the found one.

        Otherwise it leaves no element at all.  If an element is left the
        element handler for that tag is called and can replace it.
        """
        # if no tag is given or the name of the innermost is given, left
        # the last opened on.
        if not tag or tag == self.current.name:
            # if that's however the root tag, we don't leave it
            if not self.in_root_tag:
                self.current.children[-1] = self.process(self.stack.pop())
        # otherwise check if the tag we are closing is in the stack and the
        # tags in between are allowed to be closed by any tag.
        else:
            closable = True
            for idx, element in enumerate(reversed(self.stack)):
                if element.name == tag:
                    if closable:
                        for num in xrange(idx + 1):
                            self.leave(None)
                    break
                elif not self.breaking_rules.get(element.name):
                    closable = False

    def read_until(self, string):
        """Read everything to the string but don't consume the string."""
        pos = self.string.find(string, self.pos)
        if pos < 0:
            pos = self.end
        rv = self.string[self.pos:pos]
        self.pos = pos
        return rv

    def skip_until(self, string, skip_needle=True):
        """Skip everything to the string given and consume that one too.
        This function returns nothing.
        """
        self.read_until(string)
        if skip_needle:
            self.pos = min(self.end, self.pos + len(string))

    def peek_char(self):
        """Return the next character or `None` but don't advance the pointer."""
        try:
            return self.string[self.pos]
        except IndexError:
            return None

    def get_char(self):
        """Return the next character or `None` and advance the pointer."""
        rv = self.peek_char()
        if rv is not None:
            self.pos += 1
            return rv

    def match(self, regexp):
        """Match a regular expression at the current position and return
        the match object.  If the match was successful the pointer is
        advanced automatically.
        """
        match = regexp.match(self.string, self.pos)
        if match is not None:
            self.pos = match.end()
            return match

    def test_string(self, string):
        """Match the string with the current position.  Do not advance the
        pointer and return a bool.
        """
        return self.string[self.pos:self.pos + len(string)] == string

    def write_text(self, text):
        """Like `write_raw_text` but resolve entities."""
        self.write_raw_text(self.resolve_entities(text))

    def write_raw_text(self, text):
        """Write text to the current element."""
        if self.current.children:
            self.current.children[-1].tail += text
        else:
            self.current.text += text

    def parse(self):
        """Parse the whole string into an element tree."""
        while not self.finished:
            self.state = getattr(self, 'parse_' + self.state)()
        while not self.in_root_tag:
            self.leave(None)

    def parse_data(self):
        """Parse everything up to the next tag."""
        data = self.read_until('<')
        if data:
            if self.current.name in self.isolated_elements:
                self.write_raw_text(data)
            else:
                self.write_text(data)
        if self.finished:
            return 'done'
        self.pos += 1
        return 'start_tag'

    def parse_start_tag(self):
        """Parse a start tag or jumps to the comment/end_tag or data
        parsing function.
        """
        if self.peek_char() == u'/':
            self.pos += 1
            return 'end_tag'

        if self.current.name in self.isolated_elements or \
           self.current.name in self.semi_isolated_elements:
            self.write_raw_text(u'<')
            return 'data'

        if self.test_string(u'!--'):
            return 'comment'

        match = self.match(_tag_name_re)
        if match is None:
            self.write_raw_text(u'<')
            return 'data'

        element = self.enter(match.group(1))
        while 1:
            match = self.match(_attribute_re)
            if match is None:
                if self.finished:
                    state = 'done'
                elif self.match(_tag_end_re):
                    state = 'data'
                else:
                    self.pos += 1
                    continue
                # it's a void element, process it now that it's finished.
                # we know it's the last children so we can easily replace it.
                if element.name in self.void_elements:
                    self.current.children[-1] = self.process(element)
                return state
            name, value = match.groups()
            name = name.lower()
            if value is not None:
                if value[:1] == value[-1:] and value[0] in u'"\'':
                    value = value[1:-1]
                value = self.resolve_entities(value)
            element.attributes[name] = value

    def parse_end_tag(self):
        """Parse an end tag."""
        match = self.match(_tag_name_re)
        if match is not None:
            tag = match.group(1).lower()
            if self.current.name != tag and \
              (self.current.name in self.isolated_elements or
               self.current.name in self.semi_isolated_elements):
                self.write_raw_text(u'</' + match.group(0))
                return 'data'
        else:
            tag = None
        self.skip_until(u'>')
        if self.finished:
            return 'done'
        self.leave(tag)
        return 'data'

    def parse_comment(self):
        """Parse everything to the end of the comment and return to the
        data parser.
        """
        self.skip_until(u'-->')
        return 'data'


class Sanitizer(object):
    """A helper that sanitizes untrusted ZEML trees."""

    acceptable_elements = set([
        'a', 'abbr', 'acronym', 'address', 'area', 'b', 'big', 'blockquote',
        'br', 'button', 'caption', 'center', 'cite', 'code', 'col',
        'colgroup', 'dd', 'del', 'dfn', 'dir', 'div', 'dl', 'dt', 'em',
        'fieldset', 'font', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
        'i', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'map',
        'menu', 'ol', 'optgroup', 'option', 'p', 'pre', 'q', 's', 'samp',
        'select', 'small', 'span', 'strike', 'strong', 'sub', 'sup', 'table',
        'tbody', 'td', 'textarea', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u',
        'ul', 'var'
    ])

    acceptable_attributes = set([
        'abbr', 'accept', 'accept-charset', 'accesskey', 'action', 'align',
        'alt', 'axis', 'border', 'cellpadding', 'cellspacing', 'char',
        'charoff', 'charset', 'checked', 'cite', 'class', 'clear', 'cols',
        'colspan', 'color', 'compact', 'coords', 'datetime', 'dir',
        'disabled', 'enctype', 'for', 'frame', 'headers', 'height', 'href',
        'hreflang', 'hspace', 'id', 'ismap', 'label', 'lang', 'longdesc',
        'maxlength', 'media', 'method', 'multiple', 'name', 'nohref',
        'noshade', 'nowrap', 'prompt', 'readonly', 'rel', 'rev', 'rows',
        'rowspan', 'rules', 'scope', 'selected', 'shape', 'size', 'span',
        'src', 'start', 'style', 'summary', 'tabindex', 'target', 'title',
        'type', 'usemap', 'valign', 'value', 'vspace', 'width'
    ])

    uri_attributes = set(['href', 'src', 'cite', 'action', 'longdesc'])

    acceptable_css_properties = set([
        'azimuth', 'background-color', 'border-bottom-color',
        'border-collapse', 'border-color', 'border-left-color',
        'border-right-color', 'border-top-color', 'clear', 'color',
        'cursor', 'direction', 'display', 'elevation', 'float', 'font',
        'font-family', 'font-size', 'font-style', 'font-variant',
        'font-weight', 'height', 'letter-spacing', 'line-height', 'overflow',
        'pause', 'pause-after', 'pause-before', 'pitch', 'pitch-range',
        'richness', 'speak', 'speak-header', 'speak-numeral',
        'speak-punctuation', 'speech-rate', 'stress', 'text-align',
        'text-decoration', 'text-indent', 'unicode-bidi', 'vertical-align',
        'voice-family', 'volume', 'white-space', 'width'
    ])

    acceptable_css_keywords = set([
        'auto', 'aqua', 'black', 'block', 'blue', 'bold', 'both', 'bottom',
        'brown', 'center', 'collapse', 'dashed', 'dotted', 'fuchsia',
        'gray', 'green', '!important', 'italic', 'left', 'lime', 'maroon',
        'medium', 'none', 'navy', 'normal', 'nowrap', 'olive', 'pointer',
        'purple', 'red', 'right', 'solid', 'silver', 'teal', 'top',
        'transparent', 'underline', 'white', 'yellow'
    ])

    acceptable_protocols = set([
        'ed2k', 'ftp', 'http', 'https', 'irc', 'mailto', 'news', 'gopher',
        'nntp', 'telnet', 'webcal', 'xmpp', 'callto', 'feed', 'urn',
        'aim', 'rsync', 'tag', 'ssh', 'sftp', 'rtsp', 'afs', 'git', 'msn'
    ])

    _css_url_re = re.compile(r'url\s*\(\s*[^\s)]+?\s*\)\s*')
    _css_sanity_check_re = re.compile(r'''(?x)
        ^(
            [:,;#%.\sa-zA-Z0-9!]
          |  \w-\w
          | '[\s\w]+'|"[\s\w]+"
          | \([\d,\s]+\)
        )*$
    ''')
    _css_pair_re = re.compile(r'([-\w]+)\s*:\s*([^:;]*)')
    _css_unit_re = re.compile(r'''(?x)
        ^(
            #[0-9a-f]+
          | rgb\(\d+%?,\d*%?,?\d*%?\)?
          | \d{0,2}\.?\d{0,2}(cm|em|ex|in|mm|pc|pt|px|%|,|\))?
        )$
    ''')

    def is_allowed_uri(self, uri):
        return urlparse(uri).scheme in self.acceptable_protocols

    def clean_css(self, css):
        css = self._css_url_re.sub(u' ', css)
        if self._css_sanity_check_re.match(css) is None:
            return u''

        clean = []
        for prop, value in self._css_pair_re.findall(css):
            if not value:
                continue
            if prop.lower() in self.acceptable_css_properties:
                clean.append('%s: %s' % (prop, value))
            elif prop.split('-', 1)[0].lower() in \
                 ('background', 'border', 'margin', 'padding'):
                for keyword in value.split():
                    if not keyword in self.acceptable_css_keywords and \
                       not self._css_unit_re.match(keyword):
                        break
                else:
                    clean.append('%s: %s' % (prop, value))

        return u'; '.join(clean)

    def sanitize(self, element):
        previous_child = None

        def write_text(text):
            if previous_child:
                previous_child.tail += text
            else:
                element.text += text

        iterator = enumerate(element.children)
        element.children = []
        for idx, child in iterator:
            child = self.sanitize(child)
            if child.name not in self.acceptable_elements:
                if child.text:
                    write_text(child.text)
                element.children.extend(child.children)
                if child.tail:
                    write_text(child.tail)
                if child.children:
                    previous_child = child.children[-1]
                else:
                    previous_child = element
            else:
                for key, value in child.attributes.items():
                    if key not in self.acceptable_attributes or \
                       (key in self.uri_attributes and
                        not self.is_allowed_uri(value)):
                        del child.attributes[key]
                style = child.attributes.get('style')
                if style:
                    child.attributes['style'] = self.clean_css(style)
                previous_child = child
                element.children.append(child)

        return element


class Textifier(object):
    """Convert ZEML into plain text with rudimentary markup."""
    INDENT = 4
    WIDTH = 72

    class Skip(Exception):
        """Raise this to skip visiting children and departure."""

    class Cell(object):
        """Represents a table cell."""
        def __init__(self, lines, span):
            self.lines = lines
            self.span = span
        def __iter__(self):
            return iter(self.lines)

    def __init__(self, initial_indent=0, max_width=WIDTH, collect_urls=False,
                 ignore_relative_urls=True):
        self.collect_urls = collect_urls
        self.ignore_relative_urls = ignore_relative_urls
        self.result = UniStringIO()

        self.max_width = max_width
        self.indentation = initial_indent
        self.indentfirstline = 0
        self.curpar = []
        self.context = []
        self.liststack = []
        self.table = None
        self.table_ncols = 0
        self.keep_whitespace = False
        self.collected_links = {}

    def oneline(self, element):
        return u' '.join(self.multiline(element).splitlines()).strip()

    def multiline(self, element):
        self.textify(element)
        self.flush_par()
        self.write_links()
        return self.result.getvalue()

    def textify(self, element):
        """Convert one element and its children."""
        if not element:
            return
        elname = element.name.replace('#', '_')
        try:
            getattr(self, 'visit_' + elname, self.visit_unknown)(element)
        except self.Skip:
            return
        if element.text:
            self.curpar.append(element.text)
        for child in element.children:
            self.textify(child)
            if child.tail:
                self.curpar.append(child.tail)
        getattr(self, 'depart_' + elname, self.depart_unknown)(element)

    def collect_link(self, link):
        """Add a link to the collection of links, and return the number
        to reference it with.
        """
        rv = self.collected_links.get(link)
        if rv is None:
            self.collected_links[link] = rv = len(self.collected_links) + 1
        return rv

    def write_links(self):
        """Write all collected links."""
        links = [(v, k) for k, v in self.collected_links.items()]
        links.sort()
        for i, link in links:
            self.write('[%d] %s' % (i, link))

    def flush_par(self, noskip=False, force=False, nowrap=False):
        """Format and write the current paragraph."""
        if nowrap:
            par = self.get_par(wrap=False).splitlines()
        else:
            par = self.get_par(wrap=True)
        if par or force:
            for i, line in enumerate(par):
                self.write(line, first=(i==0))
            if not noskip:
                self.write()

    def get_par(self, wrap, width=None):
        """Format and return the current paragraph, and reset it."""
        if not self.curpar:
            if wrap:
                return []
            else:
                return ''
        text = ''.join(self.curpar).lstrip()
        if not self.keep_whitespace:
            text = _whitespace_re.sub(u' ', text)
        self.curpar = []
        if wrap:
            # must return a list!
            return wraptext(text, width or
                            (self.max_width - self.indentation)).splitlines()
        else:
            return text

    def write(self, text='', nl=True, first=False):
        """Write a line of text to the output buffer."""
        indent = self.indentation * ' '
        if first:
            self.result.write(indent[:self.indentfirstline or None] + text)
            self.indentfirstline = 0
        elif text: # don't write indentation only
            self.result.write(indent + text)
        if nl:
            self.result.write('\n')

    # -- block element visitors

    def hx_depart(c):
        def depart(self, element):
            par = self.get_par(wrap=False)
            self.write(par)
            self.write(c * len(par))
            self.write()
        return depart

    depart_h1 = hx_depart('=')
    depart_h2 = hx_depart('-')
    depart_h3 = hx_depart('~')
    depart_h4 = hx_depart('^')
    depart_h5 = hx_depart('`')
    depart_h6 = hx_depart('`')

    def visit_p(self, element):
        pass
    def depart_p(self, element):
        self.flush_par()

    def visit_blockquote(self, element):
        self.indentation += self.INDENT
    def depart_blockquote(self, element):
        self.flush_par()
        self.indentation -= self.INDENT

    def visit_ul(self, element):
        self.flush_par()
        self.liststack.append(None)
    def depart_ul(self, element):
        self.liststack.pop()
        self.flush_par(force=True)
    visit_dir = visit_ul
    depart_dir = depart_ul

    def visit_ol(self, element):
        self.flush_par()
        self.liststack.append(1)
    def depart_ol(self, element):
        self.liststack.pop()
        self.flush_par(force=True)

    def visit_li(self, element):
        if self.liststack and self.liststack[-1] is not None:
            indent = 4
            self.curpar.append('%-3s ' % (str(self.liststack[-1]) + '.'))
            self.liststack[-1] += 1
        else:
            indent = 2
            self.curpar.append('* ')
        self.indentfirstline = -indent
        self.indentation += indent
        self.context.append(indent)
    def depart_li(self, element):
        self.flush_par(noskip=True)
        self.indentation -= self.context.pop()

    def visit_dt(self, element):
        pass
    def depart_dt(self, element):
        self.flush_par(noskip=True)

    def visit_dd(self, element):
        self.indentation += self.INDENT
    def depart_dd(self, element):
        self.flush_par()
        self.indentation -= self.INDENT

    def visit_pre(self, element):
        self.keep_whitespace = True
    def depart_pre(self, element):
        self.flush_par(nowrap=True)
        self.keep_whitespace = False

    # -- table element visitors

    def visit_table(self, element):
        self.flush_par()
        if self.table:
            self.curpar.append('[[table]]')
            raise self.Skip()
        self.table = []
        # find number of table columns
        firstrow = element.query('/tbody/tr').first or \
                   element.query('/thead/tr').first or \
                   element.query('/tfoot/tr').first or \
                   element.query('/tr').first
        if firstrow is None:
            raise self.Skip()
        self.table_ncols = 0
        for entry in firstrow.children:
            if entry.name in ('td', 'th'):
                span = max(entry.attributes.get_int('colspan', 1), 1)
                self.table_ncols += span
        available_width = self.max_width - self.indentation
        self.table_colwidth = (available_width - 5) / self.table_ncols
        if self.table_colwidth < 10:
            self.table_colwidth = 10
    def depart_table(self, element):
        rows = []
        ncols = self.table_ncols
        realwidths = [0] * ncols
        separator = 0

        # find out the real columns widths, pass 1: single cells
        for row_or_sep in self.table:
            if row_or_sep == 'sep':
                separator = len(rows)
            else:
                for i, cell in enumerate(row_or_sep):
                    if cell and cell.span == 1 and cell.lines:
                        maxwidth = max(map(len, cell.lines))
                        realwidths[i] = max(realwidths[i], maxwidth)
                rows.append(row_or_sep)
        # pass 2: colspans
        for row in rows:
            for i, cell in enumerate(row):
                if cell and cell.span > 1:
                    maxwidth = max(map(len, cell.lines))
                    if i + cell.span - 1 < ncols:
                        cumwidth = sum(realwidths[j]
                                       for j in range(i, i+cell.span))
                        if cumwidth < maxwidth:
                            realwidths[i] += (maxwidth - cumwidth)

        def writesep(char='-'):
            out = ['+']
            for width in realwidths:
                out.append(char * (width+2))
                out.append('+')
            self.write(''.join(out))

        def writerow(row):
            if len(row) == 1:
                lines = [(x,) for x in row[0]]
            else:
                lines = map(None, *row)
            for line in lines:
                out = []
                for i, (cellline, cell) in enumerate(zip(line, row)):
                    if cell:
                        out.append('|')
                        if cell.span > 1:
                            cumwidth = sum(realwidths[j]
                                           for j in range(i, i+cell.span))
                            out.append(' ' + (cellline or '').ljust(
                                cumwidth + 3 * cell.span - 2))
                        else:
                            out.append(' ' + (cellline or '').ljust(
                                realwidths[i] + 1))
                out.append('|')
                self.write(''.join(out))

        for i, row in enumerate(rows):
            if separator and i == separator:
                writesep('=')
            else:
                writesep('-')
            writerow(row)
        writesep('-')
        self.table = None
        self.flush_par(force=True)

    def visit_tbody(self, element):
        self.table.append('sep')

    def visit_tr(self, element):
        self.table.append([])

    def visit_caption(self, element):
        self.table.append([])
        self.visit_td(element, span=self.table_ncols)

    def visit_td(self, element, span=None):
        old_result = self.result
        old_max_width = self.max_width
        old_indentation = self.indentation
        old_table = self.table
        old_table_ncols = self.table_ncols
        old_table_colwidth = self.table_colwidth

        self.result = UniStringIO()
        if span is None:
            span = max(element.attributes.get_int('colspan', 1), 1)
        self.max_width = self.table_colwidth * span
        self.indentation = 0
        self.table = None
        rootel = RootElement()
        rootel.text = element.text
        rootel.children = element.children
        self.textify(rootel)
        old_table[-1].append(self.Cell(
            self.result.getvalue().rstrip().splitlines(), span))
        old_table[-1].extend([[]] * (span-1))

        self.result = old_result
        self.max_width = old_max_width
        self.indentation = old_indentation
        self.table = old_table
        self.table_ncols = old_table_ncols
        self.table_colwidth = old_table_colwidth

        raise self.Skip
    visit_th = visit_td

    # -- inline element visitors

    def simple_decorator(s):
        def visit_or_depart(self, element):
            self.curpar.append(s)
        return visit_or_depart

    visit_b = depart_b = simple_decorator('*')
    visit_code = depart_code = simple_decorator('`')
    visit_dfn = depart_dfn = simple_decorator('*')
    visit_em = depart_em = simple_decorator('*')
    visit_i = depart_i = simple_decorator('+')
    visit_kbd = depart_kbd = simple_decorator('`')
    visit_q = depart_q = simple_decorator('"')
    visit_samp = depart_samp = simple_decorator('`')
    visit_strong = depart_strong = simple_decorator('**')
    visit_s = depart_s = simple_decorator('-')
    visit_tt = depart_tt = simple_decorator('`')
    visit_u = depart_u = simple_decorator('_')
    visit_var = depart_var = simple_decorator('*')

    def visit_a(self, element):
        pass
    def depart_a(self, element):
        if 'href' in element.attributes:
            if self.ignore_relative_urls and \
               not urlparse(element.attributes['href']).scheme:
                return
            if self.collect_urls:
                link_id = self.collect_link(element.attributes['href'])
                self.curpar.append(' [%s]' % link_id)
            else:
                self.curpar.append(' <%s>' % element.attributes['href'])

    def visit_img(self, element):
        alt = element.attributes.get('alt', 'image')
        if alt:
            self.curpar.append('[%s]' % alt)

    # -- special element visitors

    def visit__html(self, element):
        self.curpar.append('[[HTML]]')

    def visit__dynamic(self, element):
        self.curpar.append('[[dynamic content]]')

    def depart__root(self, element):
        self.flush_par()

    def visit_script(self, element):
        raise self.Skip()

    def visit_style(self, element):
        raise self.Skip()

    def depart_div(self, element):
        self.flush_par()

    def visit_unknown(self, element):
        pass
    def depart_unknown(self, element):
        pass
