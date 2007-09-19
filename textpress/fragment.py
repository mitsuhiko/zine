# -*- coding: utf-8 -*-
"""
    textpress.fragment
    ~~~~~~~~~~~~~~~~~~

    This module implements the fragment system used by the parsers from
    the `textpress.parsers` module.  All parsers have to return such
    fragments so that the caching system can work properly, and more
    important, that plugins can modify the dom tree.  Full plugin support
    may only be possible for the simplehtml parser, but all other parsers
    should try to do their best to provide a compatible interface.

    What's guaranteed is that the `process-doc-tree` callback is called once
    the node tree is assambled by the parser and that (if there are dynamic
    nodes in the returned tree) the `process-node-callback` event is called
    during rendering.

    If the tree is completely static the optimizer will just store a static
    fragment which you cannot query.  Thus if the returned node tree should
    be queryable, it's important to disable the optimizer.

    Here a small example plugin that displays the current time in all
    nodes that have a tp:contents="clock" attribute::

        from datetime import datetime

        def process_tree(event):
            doctree = event.data['doctree']
            for node in doctree.query('*[tp:contents=clock]'):
                del node.attributes['contents']
                node.add_render_callback('testplugin/show_clock')

        def node_callback(event):
            if event.data['identifier'] == 'testplugin/show_clock':
                time = datetime.now().strftime('%H:%M')
                if event.data['text_only']:
                    return time
                return event.data['node'].render(inject=time)

        def setup(app, plugin):
            app.connect_event('process-doc-tree', process_tree)
            app.connect_event('process-node-callback', node_callback)

    In the editor you can then have this snippet to trigger the
    execution::

        The current time is <span tp:contents="clock">time goes here</span>.

    Plugins have to make sure that they delete non HTML compatible
    attributes from the node they control to make sure the output isn't
    that bad. The preferred prefix for plugins is "tp:".

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import pickle
from itertools import izip
from weakref import WeakKeyDictionary
from xml.sax.saxutils import quoteattr, escape

from textpress.application import emit_event


#: list of self closing html tags for *rendering*
SELF_CLOSING_TAGS = ['br', 'img', 'area', 'hr', 'param', 'meta',
                     'link', 'base', 'input', 'embed', 'col']


def dump_tree(tree):
    """Dump a doctree into a string."""
    # special case: empty tree
    if not tree:
        return ''
    def walk(node):
        children = [walk(n) for n in node.children]
        attr = [getattr(node, x) for x in _node_members]
        return _node_types[node.__class__], children, attr
    return pickle.dumps(walk(tree), 2)


def load_tree(data):
    """Load a doctree from a string."""
    # special case: empty data, return empty fragment
    if not data:
        return StaticFragment()
    def walk(node_type, children, attr, parent=None):
        node = object.__new__(_node_types_reverse[node_type])
        node.parent = parent
        node.children = c = list.__new__(NodeList)
        list.__init__(c, [walk(parent=node, *x) for x in children])
        c.node = node
        for key, value in izip(_node_members, attr):
            setattr(node, key, value)
        return node
    return walk(*pickle.loads(data))


def _query(nodes, rule):
    """
    Query some nodes.

    ``element/subelement``:
        query all given elements that also have a given subelement.

    ``/element/subelement``:
        query all given elements that are children of this element that
        have a given subelement.

    ``*/span``:
        get all non top level spans

    ``*/#``:
        get all non top level text nodes

    ``/+``:
        get all top level non text nodes

    ``*[id=foo]``
        get all elements with the id "foo".

    ``div[class!=syntax]``
        get all div elements for wich the class is not syntax.

    ``a[@id]``
        get all links with an ID

    ``h1[!id]``
        get all h1 headlines without an ID
    """
    if rule.startswith('/'):
        rule = rule[1:]
    else:
        nodes = _iter_all(nodes)
    parts = rule.split('/', 1)
    part = parts.pop(0)
    rest = parts and parts.pop() or None

    if part.endswith(']'):
        idx = part.index('[')
        rule = part[idx + 1:-1]
        part = part[:idx]
        if '=' in rule:
            key, value = rule.split('=')
            test = lambda x: x.attributes.get(key) == value
        elif '!=' in rule:
            key, value = rule.split('!=')
            test = lambda x: x.attributes.get(key) != value
        elif rule.startswith('!'):
            rule = rule[1:]
            test = lambda x: rule not in x.attributes
        elif rule.startswith('@'):
            rule = rule[1:]
            test = lambda x: rule in x.attributes
        else:
            raise ValueError('unknown rule')
    else:
        test = None

    if part == '#':
        nodes = (x for x in nodes if x.value is not None)
    elif part == '+':
        nodes = (x for x in nodes if x.value is None)
    elif part != '*':
        nodes = (x for x in nodes if x.name == part)
    if test is not None:
        nodes = (x for x in nodes if test(x))

    def traverse():
        for node in nodes:
            if rest:
                for n in node.query(rest):
                    yield n
            else:
                yield node
    return QueryResult(traverse())


def _iter_all(nodes):
    """Iterate over all nodes and ignore double matches."""
    def inner(nodes):
        for node in nodes:
            yield node
            for item in inner(node.children):
                yield item
    return inner(nodes)


class Node(object):
    """
    Simple node class. Subclass this class and add your own render method to
    add dynamic stuff.
    """
    __slots__ = ('name', 'attributes', 'children', 'value', 'callback_data',
                 'parent')

    def __init__(self, name, attributes=None):
        self.name = name
        self.attributes = attributes or {}
        self.children = NodeList(self)
        self.value = None
        self.callback_data = None
        self.parent = None

    def render(self, inject=None):
        """
        Render the node. If `callback_data` is not None (a plugin patched
        that in the `process-doc-tree` phase) a `process-callback-node`
        event is sent with the node as only argument. If the plugin returns
        `None` the next plugins tries. If it returns a string it will be
        used instead of the normal HTML representation of the node.

        If inject is a string it will be rendered instead of the child
        elements and the callback will not be called. This is useful for
        callback nodes that just want to change the contents of a node.

        Injecting just works with the normal Node, not with a data, text
        or fragment node.
        """
        if inject is None:
            rv = self._render_callback(False)
            if rv is not None:
                return rv
        attributes = u' '.join(u'%s=%s' % (key, quoteattr(value)) for
                               key, value in self.attributes.iteritems())
        buf = [u'<%s' % self.name]
        if attributes:
            buf.append(u' ' + attributes)
        buf.append(u'>')
        if self.name not in SELF_CLOSING_TAGS:
            if inject is not None:
                buf.append(inject)
            else:
                for child in self.children:
                    buf.append(child.render())
            buf.append(u'</%s>' % self.name)
        return u''.join(buf)

    def _render_callback(self, text_only):
        """Helper frunction for render() and .text"""
        if self.callback_data:
            for identifier, data in self.callback_data:
                for item in emit_event('process-node-callback', identifier,
                                       data, self, text_only):
                    if item is not None:
                        return item

    @property
    def text(self):
        """Return the joined values of all data nodes."""
        #: if the callback wants something different do so.
        rv = self._render_callback(True)
        if rv is not None:
            return rv
        #: <br> thingies are linebreaks!
        if self.name == 'br':
            return u'\n'
        rv = u''.join(x.text for x in self)
        # if we are a paragraph make sure we put two \n at the end
        if self.name == 'p':
            rv += u'\n\n'
        return rv

    @property
    def dynamic_node(self):
        """Return `True` if this node is a dynamic one."""
        if self.callback_data:
            return True
        for node in self.children:
            if node.dynamic_node:
                return True
        return False

    def optimize(self):
        """
        Simplify the node. This is an irreversible process and
        might change semantics. Do this only after a tree was created
        and you're sure that you don't need any of the special behaviour
        and more.
        """
        return self

    def add_render_callback(self, identifier, data=None):
        """Add a new callback to this node."""
        if self.callback_data is None:
            self.callback_data = []
        self.callback_data.append((identifier, data))

    def query(self, rule):
        """Query the node."""
        return _query(self.children, rule)

    def __unicode__(self):
        """Converting a node to unicode is the same as rendering."""
        return self.render()

    def __str__(self):
        """Converting a node to str is rendering and encoding to utf-8."""
        return self.render().encode('utf-8')

    def __iter__(self):
        """Iterate over the childnodes."""
        return iter(self.children)

    def __getitem__(self, item):
        """Get children or attributes."""
        if isinstance(item, (int, long)):
            return self.children[item]
        return self.attributes[item]

    def __contains__(self, item):
        """No contains check! Too magical"""
        raise TypeError()

    def __nonzero__(self):
        """Check if we have something in that node."""
        return bool((self.children or self.attributes or self.callback_data or
                     self.value))

    def __repr__(self):
        return u'<%s %r>' % (
            self.__class__.__name__,
            unicode(self)
        )


class NodeList(list):
    """
    A list that updates "parent" on set and delete.
    """
    __slots__ = ('node',)

    def __init__(self, node):
        list.__init__(self)
        self.node = node

    def __delitem__(self, idx):
        self.pop(idx)

    def __delslice__(self, start, end):
        for node in self[start:end]:
            node.parent = None
        list.__delslice__(self, start, end)

    def __setitem__(self, idx, item):
        if isinstance(idx, slice):
            raise TypeError('extended slicing not supported')
        if item.parent is not None:
            raise TypeError('%r already bound to %r' % (item, item.parent))
        node = self[idx]
        node.parent = None
        item.parent = self.node
        list.__setitem__(self, idx, item)

    def __setslice__(self, start, end, seq):
        idx = start
        for node, new in izip(self[start:end], seq):
            if new.parent is not None:
                raise TypeError('%r already bound to %r' % (item, item.parent))
            node.parent = None
            new.parent = self.node
            self[idx] = new
            idx += 1

    def extend(self, other):
        """Add all nodes from the sequence passed."""
        for item in other:
            self.append(item)
    __iadd__ = extend

    def append(self, item):
        """Append a node to the list."""
        if item.parent is not None:
            raise TypeError('%r already bound to %r' % (item, item.parent))
        item.parent = self.node
        list.append(self, item)

    def insert(self, pos, item):
        """Insert a node at a given position."""
        if item.parent is not None:
            raise TypeError('%r already bound to %r' % (item, item.parent))
        item.parent = self.node
        list.insert(self, pos, item)

    def pop(self, index=None):
        """Delete a node at index (per default -1) from the
        list and delete it."""
        if index is None:
            node = list.pop(self)
        else:
            node = list.pop(self, index)
        node.parent = None
        return node

    def remove(self, item):
        """Remove a node from the list."""
        for idx, node in self:
            if node is item:
                del self[idx]
                return
        raise ValueError('node not in list')

    def replace(self, node, new):
        """replace a node with a new one."""
        for idx, n in enumerate(self):
            if n == node:
                self[idx] = new
                return
        raise ValueError('node not in list')

    def _unsupported(self, *args, **kwargs):
        raise TypeError('unsupported operation')

    __imul__ = __mul__ = __rmul__ = _unsupported

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__,
            list.__repr__(self)
        )


class QueryResult(object):
    """
    Represents the result of a query(). You can also further query this
    object.
    """
    __slots__ = ('_gen', '_results')

    def __init__(self, gen):
        self._gen = gen
        self._results = []

    @property
    def first(self):
        """Get the first node."""
        return self[0]

    @property
    def last(self):
        """
        Get the last node. This queries the all results first so you should
        try to use first if possible.
        """
        return self[-1]

    @property
    def text(self):
        """Return the joined values of all data nodes."""
        return u''.join(x.value for x in self if x.value is not None)

    def query(self, rule):
        """Apply the rule on all result nodes."""
        return _query(self, rule)

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


class TextNode(Node):
    """Like a normal node just that it holds a value."""
    __slots__ = ()

    def __init__(self, value):
        Node.__init__(self, None)
        self.value = value

    @property
    def text(self):
        return self.value

    def render(self, inject=None):
        return escape(self.value)


class DataNode(Node):
    """A node with XML data in it."""
    __slots__ = ()

    def __init__(self, value):
        Node.__init__(self, None)
        self.value = value

    @property
    def text(self):
        return u''

    def render(self, inject=None):
        return self.value


class Fragment(Node):
    """The outermost node."""
    __slots__ = ()

    def __init__(self):
        Node.__init__(self, None)

    def render(self, inject=None):
        return u''.join(n.render() for n in self.children)

    def optimize(self):
        """
        If this fragment is the fragment of a non dynamic node
        collection we can safely replace it with a `StaticFragment`.
        """
        if not self.dynamic_node:
            return StaticFragment(self)
        return self


class StaticFragment(Fragment):
    """An alternative to the normal fragment which is completely static."""

    def __init__(self, base=None):
        Fragment.__init__(self)
        if base is None:
            self.value = u''
        elif isinstance(base, basestring):
            self.value = unicode(base)
        elif isinstance(base, Node):
            self.value = base.render()
        else:
            raise TypeError('unicode or node required.')

    @property
    def text(self):
        return u''

    def render(self, inject=None):
        return self.value

    def optimize(self):
        return self


# helpers for the dumping system
_node_members = ('name', 'attributes', 'value', 'callback_data')
_node_types = {
    Node:           0,
    TextNode:       1,
    DataNode:       2,
    Fragment:       3,
    StaticFragment: 4
}
_node_types_reverse = [Node, TextNode, DataNode, Fragment, StaticFragment]
