# -*- coding: utf-8 -*-
"""
    textpress.utils
    ~~~~~~~~~~~~~~~

    This module implements various functions used all over the code.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import re
import unicodedata
import sha
import md5
import string
import math
import new
import sys
import os
import logging
import pytz
from time import time, strptime, sleep
from datetime import datetime, date, timedelta
from random import choice, randrange, random
from urlparse import urlparse, urljoin, urlsplit
from tempfile import NamedTemporaryFile, gettempdir
from smtplib import SMTP, SMTPException
from email.MIMEText import MIMEText
from simplejson import dumps as dump_json, loads as load_json
from SimpleXMLRPCServer import SimpleXMLRPCDispatcher
from htmlentitydefs import name2codepoint

from werkzeug import cached_property, escape, url_quote, Local, \
     LocalManager, ClosingIterator, BaseResponse
from werkzeug.exceptions import Forbidden
from werkzeug.contrib.reporterstream import BaseReporterStream

DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']

KEY_CHARS = string.ascii_letters + string.digits
SALT_CHARS = string.ascii_lowercase + string.digits
SECRET_KEY_CHARS = string.ascii_letters + string.digits + string.punctuation

_tagify_replacement_table = {
    u'\xdf': 'ss',
    u'\xe4': 'ae',
    u'\xe6': 'ae',
    u'\xf0': 'dh',
    u'\xf6': 'oe',
    u'\xfc': 'ue',
    u'\xfe': 'th'
}

_entity_re = re.compile(r'&([^;]+);')
_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|}]+')
_striptags_re = re.compile(r'(<!--.*?-->|<[^>]*>)')

_mail_re = re.compile(
    r'([a-zA-Z0-9_\.\-])+'
    r'\@(([a-zA-Z0-9\-])+\.)+([a-zA-Z0-9]{2,})+$'
)

_mail_split_re = re.compile(r'^(.*?)(?:\s+<(.+)>)?$')

#: a dict of html entities to codepoints. This includes the problematic
#: &apos; character.
_html_entities = name2codepoint.copy()
_html_entities['apos'] = 39
del name2codepoint

# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules is crap)
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)

TIMEZONES = set(pytz.common_timezones)
get_timezones_for_country = pytz.country_timezones

# load dynamic constants
from textpress._dynamic import *

# our local stuff
local = Local()
local_manager = LocalManager([local])

_version_info = None

def get_version_info():
    """Get the TextPress version info tuple."""
    global _version_info
    if _version_info is None:
        import textpress
        p = textpress.__version__.split()
        version = map(int, p.pop(0).split('.'))
        while len(version) < 3:
            version.append(0)

        if p:
            tag = p.pop(0)
            assert not p
        else:
            tag = 'release'

        from subprocess import Popen, PIPE
        hg = Popen(['hg', 'tip'], stdout=PIPE, stderr=PIPE, stdin=PIPE,
                   cwd=os.path.dirname(textpress.__file__))
        hg.stdin.close()
        hg.stderr.close()
        rv = hg.stdout.read()
        hg.stdout.close()
        hg.wait()
        hg_node = None
        if hg.wait() == 0:
            for line in rv.splitlines():
                p = line.split(':', 1)
                if len(p) == 2 and p[0].lower().strip() == 'changeset':
                    hg_node = p[1].strip()
                    break
        _version_info = tuple(version) + (tag, hg_node)
    return _version_info


def gettext(string, plural=None, n=1):
    """Translate something. XXX: add real translation here"""
    if plural is not None and n != 1:
        return plural
    return string

_ = gettext


def gen_salt(length=6):
    """Generate a random string of SALT_CHARS with specified ``length``."""
    if length <= 0:
        raise ValueError('requested salt of length <= 0')
    return ''.join(choice(SALT_CHARS) for _ in xrange(length))


def gen_activation_key(length=8):
    """
    Generate a ``length`` long string of KEY_CHARS, suitable as
    password or activation key.
    """
    if length <= 0:
        raise ValueError('requested key of length <= 0')
    return ''.join(choice(KEY_CHARS) for _ in xrange(length))


def gen_secret_key():
    """Generate a new secret key."""
    return ''.join(choice(SECRET_KEY_CHARS) for _ in xrange(64))


def gen_password(length=8, add_numbers=True, mix_case=True,
                 add_special_char=True):
    """Generate a pronounceable password."""
    if length <= 0:
        raise ValueError('requested password of length <= 0')
    consonants = 'bcdfghjklmnprstvwz'
    vowels = 'aeiou'
    if mix_case:
        consonants = consonants * 2 + consonants.upper()
        vowels = vowels * 2 + vowels.upper()
    pw =  ''.join([choice(consonants) +
                   choice(vowels) +
                   choice(consonants + vowels) for _
                   in xrange(length // 3 + 1)])[:length]
    if add_numbers:
        n = length // 3
        if n > 0:
            pw = pw[:-n]
            for _ in xrange(n):
                pw += choice('0123456789')
    if add_special_char:
        tmp = randrange(0, len(pw))
        l1 = pw[:tmp]
        l2 = pw[tmp:]
        if max(len(l1), len(l2)) == len(l1):
            l1 = l1[:-1]
        else:
            l2 = l2[:-1]
        return l1 + choice('#$&%?!') + l2
    return pw


def gen_pwhash(password):
    """Return a the password encrypted in sha format with a random salt."""
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    salt = gen_salt(6)
    h = sha.new()
    h.update(salt)
    h.update(password)
    return 'sha$%s$%s' % (salt, h.hexdigest())


def replace_entities(string):
    """
    Replace HTML entities in a string:

    >>> replace_entities('foo &amp; bar &raquo; foo')
    ...
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


def check_external_url(app, url, check=False):
    blog_url = app.cfg['blog_url']
    check = urljoin(blog_url, url)

    if check:
        # check if the url is on the same server
        # as configured
        c1 = urlsplit(blog_url)[:2]
        c2 = urlsplit(check)[:2]
        if c1 != c2:
            raise ValueError('The url %s is not on the same server'
                             'as configured. Please notify the administrator'
                             % check)
    return check


def check_pwhash(pwhash, password):
    """
    Check a password against a given hash value. Since
    many forums save md5 passwords with no salt and it's
    technically impossible to convert this to an sha hash
    with a salt we use this to be able to check for
    plain passwords::

        plain$$default

    md5 passwords without salt::

        md5$$c21f969b5f03d33d43e04f8f136e7682

    md5 passwords with salt::

        md5$123456$7faa731e3365037d264ae6c2e3c7697e

    sha passwords::

        sha$123456$118083bd04c79ab51944a9ef863efcd9c048dd9a

    Note that the integral passwd column in the table is
    only 60 chars long. If you have a very large salt
    or the plaintext password is too long it will be
    truncated.
    """
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    if pwhash.count('$') < 2:
        return False
    method, salt, hashval = pwhash.split('$', 2)
    if method == 'plain':
        return hashval == password
    elif method == 'md5':
        h = md5.new()
    elif method == 'sha':
        h = sha.new()
    else:
        return False
    h.update(salt)
    h.update(password)
    return h.hexdigest() == hashval


def gen_slug(text):
    """remove accents and make text lowercase."""
    result = []
    for word in _punctuation_re.split(text.lower()):
        if word:
            for search, replace in _tagify_replacement_table.iteritems():
                word = word.replace(search, replace)
            word = unicodedata.normalize('NFKD', word)
            result.append(word.encode('ascii', 'ignore'))
    return u'-'.join(result)


def format_datetime(obj, format=None):
    """Format a datetime object. Later with i18n"""
    cfg = local.application.cfg
    tzinfo = pytz.timezone(str(cfg['timezone']))
    if type(obj) is date:
        obj = datetime(obj.year, obj.month, obj.day, tzinfo=tzinfo)
    else:
        obj = obj.replace(tzinfo=tzinfo)
    if format is None:
        format = cfg['datetime_format']
    return obj.strftime(format.encode('utf-8')).decode('utf-8')


def format_date(obj):
    """Format a date or datetime object so that it's displays the date."""
    return format_datetime(obj, local.application.cfg['date_format'])


def format_month(obj):
    """Formats a month."""
    # XXX: l10n!!!
    return format_datetime(obj, '%B %Y')


def parse_datetime(string):
    """Do all you can do to parse the string into a datetime object."""
    if string.lower() == _('now'):
        return datetime.utcnow()
    convert = lambda fmt: datetime(*strptime(string, fmt)[:7])
    cfg = local.application.cfg

    # first of all try the datetime_format because it's likely that
    # the users inputs the date like chosen in the config
    try:
        return convert(cfg['datetime_format'])
    except ValueError:
        pass

    # no go with time only, and current day
    base = datetime.utcnow()
    for fmt in TIME_FORMATS:
        try:
            val = convert(fmt)
        except ValueError:
            continue
        return base.replace(hour=val.hour, minute=val.minute,
                            second=val.second)

    # no try date + time
    def combined():
        for t_fmt in TIME_FORMATS:
            for d_fmt in DATE_FORMATS:
                yield t_fmt + ' ' + d_fmt
                yield d_fmt + ' ' + t_fmt

    for fmt in combined():
        try:
            return convert(fmt)
        except ValueError:
            pass

    raise ValueError('invalid date format')


def is_valid_email(mail):
    """Check if the string passed is a valid mail address."""
    return _mail_re.match(mail) is not None


def is_valid_url(url):
    """Check if the string passed is a valid url."""
    protocol = urlparse(url)[0]
    return protocol and protocol != 'javascript'


def is_valid_ip(value):
    """Check if the string provided is a valid IP."""
    # XXX: ipv6!
    idx = 0
    for idx, bit in enumerate(value.split('.')):
        if not bit.isdigit() or not 0 <= int(value) <= 255:
            return False
    return idx == 3


def parse_iso8601(value):
    """
    Parse an iso8601 date into a datetime object.
    The timezone is normalized to UTC, we always use UTC objects
    internally.
    """
    m = _iso8601_re.match(value)
    if m is None:
        raise ValueError('not a valid iso8601 date value')

    groups = m.groups()
    args = []
    for group in groups[:-2]:
        if group is not None:
            group = int(group)
        args.append(group)
    seconds = groups[-2]
    if seconds is not None:
        if '.' in seconds:
            args.extend(map(int, seconds.split('.')))
        else:
            args.append(int(seconds))

    rv = datetime(*args)
    tz = groups[-1]
    if tz and tz != 'Z':
        args = map(int, tz[1:].split(':'))
        delta = timedelta(hours=args[0], minutes=args[1])
        if tz[0] == '+':
            rv += delta
        else:
            rv -= delta

    return rv


def format_iso8601(obj):
    """Format a datetime object for iso8601"""
    return obj.strftime('%Y-%d-%mT%H:%M:%SZ')


def generate_rsd(app):
    """Generate the RSD definition for this application apis."""
    from textpress.application import url_for
    from xml.dom.minidom import Document
    document = Document()
    root = document.appendChild(document.createElement('rsd'))
    root.setAttribute('version', '1.0')
    root.setAttribute('xmlns', 'http://archipelago.phrasewise.com/rsd')
    service = root.appendChild(document.createElement('service'))

    attributes = [('engineName', 'TextPress'),
                  ('engineLink', 'http://textpress.pocoo.org/'),
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


try:
    import _ast
except ImportError:
    can_build_eventmap = False
else:
    can_build_eventmap = True


def build_eventmap(app):
    """
    Walk through all the builtins and plugins for an application and
    look for emit_event() calls. This is useful for plugin developers that
    want to find possible entry points without having to dig the source or
    missing documentation. Speaking of documentation: This could help for
    that too.
    """
    if not can_build_eventmap:
        raise RuntimeError('this feature requires python 2.5')
    import textpress

    textpress_root = os.path.realpath(os.path.dirname(textpress.__file__))
    searchpath = [(textpress_root, '__builtin__')]

    for plugin in app.plugins.itervalues():
        path = os.path.realpath(plugin.path)
        if os.path.commonprefix([textpress_root, path]) != textpress_root:
            searchpath.append((plugin.path, plugin.name))

    def walk_ast(ast):
        if isinstance(ast, _ast.Call) and \
           isinstance(ast.func, _ast.Name) and \
           ast.func.id == 'emit_event' and \
           ast.args and \
           isinstance(ast.args[0], _ast.Str):
            yield ast.args[0].s, ast.func.lineno
        for field in ast._fields or ():
            value = getattr(ast, field)
            if isinstance(value, (tuple, list)):
                for node in value:
                    if isinstance(node, _ast.AST):
                        for item in walk_ast(node):
                            yield item
            elif isinstance(value, _ast.AST):
                for item in walk_ast(value):
                    yield item

    result = {}
    for folder, prefix in searchpath:
        offset = len(folder)
        for dirpath, dirnames, filenames in os.walk(folder):
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                filename = os.path.join(dirpath, filename)
                shortname = filename[offset:]

                f = file(filename)
                try:
                    ast = compile(f.read(), filename, 'exec', 0x400)
                finally:
                    f.close()

                for event, lineno in walk_ast(ast):
                    result.setdefault(event, []).append((prefix, shortname,
                                                         lineno))

    return result


def make_hidden_fields(*fields):
    """Create some hidden form data for fields."""
    buf = []
    for field in fields:
        args = field.get_hidden_field()
        if args is not None:
            buf.append(u'<input type="hidden" name="%s" value="%s">' %
                       (escape(args[0]), escape(args[1])))
    return u'\n'.join(buf)


def split_email(s):
    """
    Split a mail address:

        >>> split_email("John Doe")
        ('John Doe', None)
        >>> split_email("John Doe <john@doe.com>")
        ('John Doe', 'john@doe.com')
        >>> split_email("john@doe.com")
        (None, 'john@doe.com')
    """
    p1, p2 = _mail_split_re.search(s).groups()
    if p2:
        return p1, p2
    elif is_valid_email(p1):
        return None, p1
    return p1, None


def send_email(subject, text, to_addrs, quiet=True):
    """Send a mail using the `EMail` class."""
    e = EMail(subject, text, to_addrs)
    if quiet:
        return e.send_quiet()
    return e.send()


class EMail(object):
    """
    Represents one E-Mail message that can be sent.
    """

    def __init__(self, subject=None, text='', to_addrs=None):
        self.app = app = local.application
        self.subject = u' '.join(subject.splitlines())
        self.text = text
        from_addr = app.cfg['blog_email']
        if not from_addr:
            from_addr = 'noreply@' + urlparse(app.cfg['blog_url'])\
                    [1].split(':')[0]
        self.from_addr = u'%s <%s>' % (
            app.cfg['blog_title'],
            from_addr
        )
        self.to_addrs = []
        if isinstance(to_addrs, basestring):
            self.add_addr(to_addrs)
        else:
            for addr in to_addrs:
                self.add_addr(addr)

    def add_addr(self, addr):
        """
        Add an mail address to the list of recipients
        """
        lines = addr.splitlines()
        if len(lines) != 1:
            raise ValueError('invalid value for email address')
        self.to_addrs.append(lines[0])

    def send(self):
        """
        Send the message.
        """
        if not self.subject or not self.text or not self.to_addrs:
            raise RuntimeError("Not all mailing parameters filled in")
        try:
            smtp = SMTP(self.app.cfg['smtp_host'])
        except SMTPException, e:
            raise RuntimeError(str(e))

        if self.app.cfg['smtp_user']:
            try:
                try:
                    smtp.login(self.app.cfg['smtp_user'],
                               self.app.cfg['smtp_password'])
                except SMTPException, e:
                    raise RuntimeError(str(e))
            finally:
                smtp.quit()

        msg = MIMEText(self.text)
        msg['From'] = self.from_addr
        msg['To'] = ', '.join(self.to_addrs)
        msg['Subject'] = self.subject

        try:
            try:
                return smtp.sendmail(self.from_addr, self.to_addrs,
                                     msg.as_string())
            except SMTPException, e:
                raise RuntimeError(str(e))
        finally:
            smtp.quit()

    def send_quiet(self):
        """
        Send the message, swallowing exceptions.
        """
        try:
            return self.send()
        except Exception:
            return


class Pagination(object):
    """Pagination helper."""

    def __init__(self, endpoint, page, per_page, total, url_args=None):
        self.endpoint = endpoint
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = int(math.ceil(self.total / float(self.per_page)))
        self.url_args = url_args or {}
        self.necessary = self.pages > 1

    def generate(self, normal='<a href="%(url)s">%(page)d</a>',
                 active='<strong>%(page)d</strong>', commata=',\n',
                 ellipsis=' ...\n', threshold=3, prev_link=False,
                 next_link=False, gray_prev_link=True, gray_next_link=True):
        from textpress.application import url_for
        was_ellipsis = False
        result = []
        prev = None
        next = None
        get_link = lambda x: url_for(self.endpoint, page=x, **self.url_args)

        for num in xrange(1, self.pages + 1):
            if num - 1 == self.page:
                next = num
            if num + 1 == self.page:
                prev = num
            if num <= threshold or num > self.pages - threshold or \
               abs(self.page - num) < math.ceil(threshold / 2.0):
                if result and result[-1] != ellipsis:
                    result.append(commata)
                was_space = False
                link = get_link(num)
                template = num == self.page and active or normal
                result.append(template % {
                    'url':      link,
                    'page':     num
                })
            elif not was_ellipsis:
                was_ellipsis = True
                result.append(ellipsis)

        if next_link:
            if next is not None:
                result.append(u' <a href="%s">Next &raquo;</a>' %
                              get_link(next))
            elif gray_next_link:
                result.append(u' <span class="disabled">Next &raquo;</span>')
        if prev_link:
            if prev is not None:
                result.insert(0, u'<a href="%s">&laquo; Prev</a> ' %
                              get_link(prev))
            elif gray_prev_link:
                result.insert(0, u'<span class="disabled">&laquo; Prev</span> ')

        return u''.join(result)


class RequestLocal(object):
    """
    All attributes on this object are request local and deleted after the
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


class HiddenFormField(object):
    """
    Baseclass for special hidden fields.
    """

    def get_hidden_field(self):
        pass

    def __unicode__(self):
        return make_hidden_fields(self)


class XMLRPC(object, SimpleXMLRPCDispatcher):
    """
    A XMLRPC dispatcher that uses our request and response objects.  It
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


class IntelligentRedirect(HiddenFormField):
    """
    An intelligent redirect tries to go back to the page the user
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
        self.request = local.request
        self.invalid_targets = []

    def add_invalid(self, *args, **kwargs):
        """
        Add an invalid target. Invalid targets are URLs we don't want to visit
        again. For example if a post is deleted from the post edit page it's
        a bad idea to redirect back to the edit page because in that situation
        the edit page would return a page not found.
        """
        from textpress.application import url_for
        self.invalid_targets.append(url_for(*args, **kwargs))

    def get_redirect_target(self):
        """
        Check the request and get the redirect target if possible.
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

    def __call__(self, *args, **kwargs):
        """Trigger the redirect."""
        from textpress.application import redirect, url_for
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
    """
    This class is used in the admin panel to avoid CSRF attacks.

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
        self.request = request = local.request
        self.token = sha.new('%s|%s|%s|%s' % (
            request.path,
            local.application.cfg['secret_key'],
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
    """
    This class can wrap `wsgi.input` so that we get upload notifications
    during uploading.

    TextPress also provides a service called `get_upload_info` that returns
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
    """

    def __init__(self, transport_id=None):
        self.request = request = local.request

        if transport_id is None:
            transport_id = request.args.get('_transport_id')
        if transport_id is None:
            transport_id = StreamReporter.generate_id()
        self.transport_id = transport_id
        self.start_time = int(time())

        self._fp = NamedTemporaryFile(prefix='_textpress_upload_')
        BaseReporterStream.__init__(self, request.environ, 1024 * 50)
        request.environ['wsgi.input'] = self
        self._stream_registered = False

    @staticmethod
    def generate_id():
        return md5.new('%s|%s' % (time(), random())).hexdigest()

    @staticmethod
    def _get_manager():
        app = local.application
        return os.path.join(gettempdir(), '_textpress_streams_' +
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
