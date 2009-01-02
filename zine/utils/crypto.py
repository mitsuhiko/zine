"""
    zine.utils.crypto
    ~~~~~~~~~~~~~~~~~

    This module implements various cryptographic functions.

    :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import string
from random import choice, randrange
try:
    from hashlib import sha1, md5
except ImportError:
    from sha import new as sha1
    from md5 import new as md5


KEY_CHARS = string.ascii_letters + string.digits
IDENTIFIER_START = string.ascii_letters + '_'
IDENTIFIER_CHAR = IDENTIFIER_START + string.digits
SALT_CHARS = string.ascii_lowercase + string.digits
SECRET_KEY_CHARS = string.ascii_letters + string.digits + string.punctuation


def gen_salt(length=6):
    """Generate a random string of SALT_CHARS with specified ``length``."""
    if length <= 0:
        raise ValueError('requested salt of length <= 0')
    return ''.join(choice(SALT_CHARS) for _ in xrange(length))


def new_iid():
    """Called by the websetup to get a unique uuid for the application iid."""
    try:
        import uuid
    except ImportError:
        # if there is no uuid support, we create a pseudo-unique id based
        # on the current time.  This should be good enough to keep local
        # installations apart.
        import time
        return '%x%x' % tuple(map(int, str(time.time()).split('.')))
    return uuid.uuid4().hex


def gen_activation_key(length=8):
    """Generate a ``length`` long string of KEY_CHARS, suitable as
    password or activation key.
    """
    if length <= 0:
        raise ValueError('requested key of length <= 0')
    return ''.join(choice(KEY_CHARS) for _ in xrange(length))


def gen_random_identifier(length=8):
    """Generate a random identifier."""
    if length <= 0:
        raise ValueError('requested key of length <= 0')
    return choice(IDENTIFIER_START) + \
           ''.join(choice(IDENTIFIER_CHAR) for _ in xrange(length - 1))


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
    h = sha1()
    h.update(salt)
    h.update(password)
    return 'sha$%s$%s' % (salt, h.hexdigest())


def check_pwhash(pwhash, password):
    """Check a password against a given hash value. Since
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

    >>> check_pwhash('plain$$default', 'default')
    True
    >>> check_pwhash('sha$$5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8', 'password')
    True
    >>> check_pwhash('sha$$5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8', 'wrong')
    False
    >>> check_pwhash('md5$xyz$bcc27016b4fdceb2bd1b369d5dc46c3f', u'example')
    True
    >>> check_pwhash('sha$5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8', 'password')
    False
    >>> check_pwhash('md42$xyz$bcc27016b4fdceb2bd1b369d5dc46c3f', 'example')
    False
    """
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    if pwhash.count('$') < 2:
        return False
    method, salt, hashval = pwhash.split('$', 2)
    if method == 'plain':
        return hashval == password
    elif method == 'md5':
        h = md5()
    elif method == 'sha':
        h = sha1()
    else:
        return False
    h.update(salt)
    h.update(password)
    return h.hexdigest() == hashval
