"""
    zine.utils.crypto
    ~~~~~~~~~~~~~~~~~

    This module implements various cryptographic functions.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import sha
import string
from random import choice, randrange


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
    h = sha.new()
    h.update(salt)
    h.update(password)
    return 'sha$%s$%s' % (salt, h.hexdigest())
