# -*- coding: utf-8 -*-
"""
    textpress.utils
    ~~~~~~~~~~~~~~~

    This module implements various functions used all over the code.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import re
import unicodedata
import sha
import md5
import string
import math
from time import time, strptime
from datetime import datetime, timedelta
from random import choice, randrange, random
from urlparse import urlparse
from simplejson import dumps as dump_json, loads as load_json

from werkzeug.utils import lazy_property

DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']

KEY_CHARS = string.ascii_letters + string.digits
SALT_CHARS = string.ascii_lowercase + string.digits

REPLACEMENT_TABLE = {
    u'\xdf': 'ss',
    u'\xe4': 'ae',
    u'\xe6': 'ae',
    u'\xf0': 'dh',
    u'\xf6': 'oe',
    u'\xfc': 'ue',
    u'\xfe': 'th'
}

_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|}]+')

_mail_re = re.compile(
    r'([a-zA-Z0-9_\.\-])+'
    r'\@(([a-zA-Z0-9\-])+\.)+([a-zA-Z0-9]{2,})+$'
)

# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules is crap)
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)


def gettext(string, plural=None, n=1):
    """Translate something. XXX: add real translation here"""
    if plural is not None and n != 1:
        return plural
    return string

_ = gettext


def gen_salt(length=6):
    """
    Generate a random string of SALT_CHARS with specified ``length``.
    """
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


def gen_password(length=8, add_numbers=True, mix_case=True,
                 add_special_char=True):
    """
    Generate a pronounceable password.
    """
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


def gen_sid():
    """Generate a session id."""
    return md5.new('%s|%s' % (time(), random())).hexdigest()


def gen_pwhash(password):
    """
    Return a the password encrypted in sha format with a random salt.
    """
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    salt = gen_salt(6)
    h = sha.new()
    h.update(salt)
    h.update(password)
    return 'sha$%s$%s' % (salt, h.hexdigest())


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
            for search, replace in REPLACEMENT_TABLE.iteritems():
                word = word.replace(search, replace)
            word = unicodedata.normalize('NFKD', word)
            result.append(word.encode('ascii', 'ignore'))
    return u'-'.join(result)


def format_datetime(obj):
    """Format a datetime object. Later with i18n"""
    from textpress.application import get_application
    return obj.strftime(str(get_application().cfg['datetime_format']))


def format_date(obj):
    """Format a date or datetime object so that it's displays the date."""
    from textpress.application import get_application
    return obj.strftime(str(get_application().cfg['date_format']))


def format_month(obj):
    """Formats a month."""
    # XXX: l10n!!!
    return obj.strftime('%B %Y')


def parse_datetime(string):
    """Do all you can do to parse the string into a datetime object."""
    if string.lower() == _('now'):
        return datetime.utcnow()
    from textpress.application import get_application
    convert = lambda fmt: datetime(*strptime(string, fmt)[:7])
    cfg = get_application().cfg

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


def markup(text):
    """Markup format a text. Used for comments."""
    from textpress.markup import MarkupParser
    return MarkupParser(text).to_html()


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
    The timezone is normalized to UTC, we always use UTC objects internally.
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
