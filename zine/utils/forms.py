# -*- coding: utf-8 -*-
"""
    zine.utils.forms
    ~~~~~~~~~~~~~~~~

    The Zine form handling.

    License notice: largely based on diva's form handling.

    :copyright: Copyright 2007-2008 by Armin Ronacher, Christopher Lenz.
    :license: GNU GPL.
"""
import re
from copy import copy
from unicodedata import normalize

from zine.i18n import gettext, ngettext


_decode = re.compile(r'\[(\w+)\]').findall


def decode(data):
    """Decodes the flat dictionary d into a nested structure.

    >>> decode({'foo': 'bar'})
    {'foo': 'bar'}

    >>> decode({'foo[0]': 'bar', 'foo[1]': 'baz'})
    {'foo': ['bar', 'baz']}

    >>> data = decode({'foo[bar]': '1', 'foo[baz]': '2'})
    >>> assert data == {'foo': {'bar': '1', 'baz': '2'}}

    >>> decode({'foo[bar][0]': 'baz', 'foo[bar][1]': 'buzz'})
    {'foo': {'bar': ['baz', 'buzz']}}

    >>> decode({'foo[0][bar]': '23', 'foo[1][baz]': '42'})
    {'foo': [{'bar': '23'}, {'baz': '42'}]}

    >>> decode({'foo[0][0]': '23', 'foo[0][1]': '42'})
    {'foo': [['23', '42']]}

    >>> decode({'foo': ['23', '42']})
    {'foo': ['23', '42']}
    """
    result = {}
    lists = []

    for key, value in data.items():
        pos = key.find('[')
        if pos == -1:
            result[key] = value
        else:
            names = [key[:pos]] + _decode(key[pos:])
            container = result
            end = len(names) - 1
            for idx in range(end):
                curname = names[idx]
                if curname not in container:
                    nextname = names[idx + 1]
                    container[curname] = {}
                    if nextname.isdigit():
                        container[curname]['__list__'] = True
                container = container[curname]
            container[names[-1]] = value

    def _convert(data):
        if type(data) is dict:
            if '__list__' in data:
                del data['__list__']
                data = [_convert(v) for k, v in sorted(data.items())]
            else:
                data = dict((k, _convert(v)) for k, v in data.items())
        return data

    return _convert(result)


def encode(data):
    """Encodes a nested structure into a flat dictionary.

    >>> encode({'foo': 'bar'})
    {'foo': 'bar'}

    >>> encode({'foo': ['bar', 'baz']})
    {'foo[0]': 'bar', 'foo[1]': 'baz'}

    >>> encode({'foo': [{'bar': '42', 'baz': '43'}]})
    {'foo[0][baz]': '43', 'foo[0][bar]': '42'}
    """
    def _encode(data=data, prefix='', result={}):
        if isinstance(data, dict):
            for key, value in data.items():
                if key is None:
                    name = prefix
                elif not prefix:
                    name = key
                else:
                    name = "%s[%s]" % (prefix, key)
                _encode(value, name, result)
        elif isinstance(data, list):
            for i in range(len(data)):
                _encode(data[i], "%s[%d]" % (prefix, i), result=result)
        else:
            result[prefix] = data
        return result
    return _encode()


class ValidationError(Exception):
    """Exception raised when invalid data is encountered."""

    def unpack(self, key=None):
        return {key: [self.args[0]]}


class Converter(object):
    """Internal baseclass for fields."""

    def __init__(self):
        self._validate_functions = []

    def __call__(self, value, form=None):
        value = self.convert(value, form)
        for validator in self._validate_functions:
            validator(form, value)
        return value

    def convert(self, value, form):
        """This can be overridden by subclasses and performs the value
        conversion.  If the converting process is triggered without a form
        the form parameter will be `None`.
        """
        return unicode(value)

    def clone(self):
        """Creates a clone of the converter."""
        rv = object.__new__(self.__class__)
        for key, value in self.__dict__.iteritems():
            rv.__dict__[key] = copy(value)
        return rv

    def add_validator(cls, validator):
        """Adds a new validation function to the converter.
        The function is passed two arguments: the form as first argument and
        the value as second.  If the converter is used without a form, the
        first parameter will be `None`.

        The function has to return `None` and raise a `ValidationError` if the
        validation failed.

        Examples:

        >>> def is_even(form, value):
        ...     if value % 2 != 0:
        ...         raise ValidationError('value must be even')
        >>> field = IntegerField()
        >>> field.add_validator(is_even)
        """
        cls._validate_functions.append(validator)

    def __copy__(self):
        return self.clone()


class Field(Converter):
    """Abstract field base class."""


class Mapping(Field):
    """Apply a set of fields to a dictionary of values.

    >>> field = Mapping(name=StringField(), age=IntegerField())
    >>> field({'name': u'John Doe', 'age': u'42'})
    {'age': 42, 'name': u'John Doe'}
    """

    class ValidationErrors(ValidationError):

        def __init__(self, errors):
            ValidationError.__init__(self, '%d error%s' % (
                len(errors), len(errors) != 1 and 's' or ''
            ))
            self.errors = errors

        def __unicode__(self):
            return ', '.join([str(e) for e in self.errors.values()])

        def unpack(self, key=None):
            retval = {}
            for name, error in self.errors.items():
                retval.update(error.unpack(key=name))
            return retval


    def __init__(self, **fields):
        Field.__init__(self)
        self.fields = fields

    def convert(self, value, form):
        errors = {}
        result = {}
        for name, field in self.fields.items():
            try:
                result[name] = field(value.get(name, ''), form)
            except ValidationError, e:
                errors[name] = e
        if errors:
            raise self.ValidationErrors(errors)
        return result

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.fields)


class FormAsField(Mapping):
    """If a form is converted into a field the returned field object is an
    instance of this class.  The behavior is mostly equivalent to a normal
    :class:`Mapping` field with the difference that it as an attribute called
    :attr:`form` that points to the form it was created from.
    """

    def __init__(self):
        raise TypeError('can\'t create %r instances' %
                        self.__class__.__name__)


class Multiple(Field):
    """Apply a single field to a sequence of values.

    >>> field = Multiple(IntegerField())
    >>> field([u'1', u'2', u'3'])
    [1, 2, 3]
    """

    class ValidationErrors(ValidationError):

        def __init__(self, errors):
            ValidationError.__init__(self, '%d error%s' % (
                len(errors), len(errors) != 1 and 's' or ''
            ))
            self.errors = errors

        def __unicode__(self):
            return ', '.join([str(e) for e in self.errors])

        def unpack(self, key=None):
            return {key: [e.unpack() for e in self.errors]}


    def __init__(self, field, min_size=None, max_size=None):
        Field.__init__(self)
        self.field = field
        self.min_size = min_size
        self.max_size = max_size

    def convert(self, value, form):
        errors = []
        if self.min_size is not None and len(value) < self.min_size:
            errors.append(ValidationError(
                ngettext('Please provide at least %d item.',
                         'Please provide at least %d items.',
                         self.min_size) % self.min_size
            ))
        if self.max_size is not None and len(value) > self.max_size:
            errors.append(ValidationError(
                ngettext('Please provide no more than %d item.',
                         'Please provide no more than %d items.',
                         self.max_size) % self.max_size
            ))
        result = []
        for item in value:
            try:
                result.append(self.field(item, form))
            except ValidationError, e:
                errors.append(e)
        if errors:
            raise self.ValidationErrors(errors)
        return result

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.field)


class StringField(Field):
    """Field for strings.

    >>> field = StringField(required=True, min_length=6)
    >>> field('foo bar')
    u'foo bar'
    >>> field('')
    Traceback (most recent call last):
      ...
    ValidationError: This field is required.

    You can also specify a regular expression that the content must match using
    the `pattern` parameter:

    >>> field = StringField(pattern=r'\w+')
    >>> field('foo bar')
    Traceback (most recent call last):
      ...
    ValidationError: The value does not match pattern "^\w+$".

    Because displaying regular expression patterns to the user is ugly almost
    always unhelpful, you can specify a custom error message that should be
    used when the pattern does not match:

    >>> from zine.i18n import lazy_gettext
    >>> field = StringField(pattern=r'\w+',
    ...                     message=lazy_gettext('Only letters allowed here.'))
    >>> field('foo bar')
    Traceback (most recent call last):
      ...
    ValidationError: Only letters allowed here.
    """

    def __init__(self, required=False, min_length=None, max_length=None,
                 pattern=None, message=None):
        Field.__init__(self)
        self.required = required
        self.min_length = min_length
        self.max_length = max_length
        if isinstance(pattern, basestring):
            pattern = re.compile('^%s$' % pattern)
        self.pattern = pattern
        if pattern and not message:
            message = gettext('The value does not match pattern "%s".') % \
                      pattern.pattern
        self.message = message

    def convert(self, value, form):
        value = unicode(value)
        if self.required and not value:
            raise ValidationError(gettext('This field is required.'))
        if self.min_length is not None and len(value) < self.min_length:
            raise ValidationError(
                ngettext('Please enter at least %d character.',
                         'Please enter at least %d characters.',
                         self.min_length) % self.min_length
            )
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(
                ngettext('Please enter no more than %d character.',
                         'Please enter no more than %d characters.',
                         self.max_length) % self.max_length
            )
        if self.pattern is not None and not self.pattern.match(value):
            raise ValidationError(self.message)
        return value


class IntegerField(Field):
    """Field for integers.

    >>> field = IntegerField(min_value=0, max_value=99)
    >>> field('13')
    13

    >>> field('thirteen')
    Traceback (most recent call last):
      ...
    ValidationError: Please enter a whole number.

    >>> field('193')
    Traceback (most recent call last):
      ...
    ValidationError: Ensure this value is less than or equal to 99.
    """

    def __init__(self, required=False, min_value=None, max_value=None):
        Field.__init__(self)
        self.required = required
        self.min_value = min_value
        self.max_value = max_value

    def convert(self, value, form):
        if not value:
            if self.required:
                raise ValidationError(gettext('This field is required.'))
            return None
        try:
            value = int(value)
        except ValueError:
            raise ValidationError(gettext('Please enter a whole number.'))

        if self.min_value is not None and value < self.min_value:
            raise ValidationError(
                gettext('Ensure this value is greater than or equal to '
                        '%s.') % self.min_value
            )
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(
                gettext('Ensure this value is less than or equal to '
                        '%s.') % self.max_value
            )

        return int(value)


class BooleanField(Field):
    """Field for boolean values.

    >>> field = BooleanField()
    >>> field('1')
    True

    >>> field = BooleanField()
    >>> field('')
    False
    """

    def convert(self, value, form):
        return bool(value)


class FormMeta(type):
    """Meta class for forms."""

    def __new__(cls, name, bases, d):
        fields = {}
        validator_functions = {}

        for base in bases:
            if hasattr(base, '_converter'):
                # base._converter is always a Mapping converter
                fields.update(base._converter.fields)

        context_validate = d.get('context_validate')

        for key, value in d.iteritems():
            if key.startswith('validate_') and callable(value):
                validator_functions[key[9:]] = value
            elif isinstance(value, Field):
                fields[key] = value

        for field_name, func in validator_functions.iteritems():
            if field_name in fields:
                fields[field_name].add_validator(func)

        d['_converter'] = conv = Mapping(**fields)
        if context_validate is not None:
            conv.add_validator(context_validate)

        return type.__new__(cls, name, bases, d)

    def add_validator(cls, validator):
        cls._converter.add_validator(validator)


class Form(object):
    """Form base class.

    >>> class PersonForm(Form):
    ...     name = StringField(required=True)
    ...     age = IntegerField()

    >>> form = PersonForm()
    >>> form.validate({'name': 'johnny', 'age': '42'})
    True
    >>> form['name']
    u'johnny'
    >>> form['age']
    42

    Let's cause a simple validation error:

    >>> form = PersonForm()
    >>> form.validate({'name': '', 'age': 'fourty-two'})
    False
    >>> print form.errors['age'][0]
    Please enter a whole number.
    >>> print form.errors['name'][0]
    This field is required.

    You can also add custom validation routines for fields by adding methods
    that start with the prefix ``validate_`` and the field name that take the
    value as argument. For example:

    >>> class PersonForm(Form):
    ...     name = StringField(required=True)
    ...     age = IntegerField()
    ...
    ...     def validate_name(self, value):
    ...         if not value.isalpha():
    ...             raise ValidationError('The value must only contain letters')

    >>> form = PersonForm()
    >>> form.validate({'name': 'mr.t', 'age': '42'})
    False
    >>> form.errors
    {'name': ['The value must only contain letters']}

    You can also validate multiple fields in the context of other fields.
    That validation is performed after all other validations.  Just add a
    method called ``context_validate`` that is passed the dict of all fields::

    >>> class RegisterForm(Form):
    ...     username = StringField(required=True)
    ...     password = StringField(required=True)
    ...     password_again = StringField(required=True)
    ...
    ...     def context_validate(self, data):
    ...         if data['password'] != data['password_again']:
    ...             raise ValidationError('The two passwords don\'t match')

    >>> form = RegisterForm()
    >>> form.validate({'username': 'admin', 'password': 'blah',
    ...                'password_again': 'blag'})
    ...
    False
    >>> form.errors
    {None: ['The two passwords don\'t match']}
    """
    __metaclass__ = FormMeta

    def __init__(self, id=None, name=None, defaults=None):
        self.id = id
        self.name = name
        if defaults is None:
            defaults = {}
        self.defaults = defaults
        self.reset()

    def as_field(self):
        """Returns a field object for this form."""
        field = self._converter.clone()
        field.__class__ = FormAsField
        field.form = self
        return field

    @property
    def fields(self):
        return self._converter.fields

    def reset(self):
        self.data = self.defaults.copy()
        self.errors = {}

    @property
    def is_valid(self):
        return not self.errors

    def validate(self, data):
        d = self.data.copy()
        d.update(decode(data))
        errors = {}
        try:
            data = self._converter(d)
        except ValidationError, e:
            errors = e.unpack()
        self.data.update(data)
        self.errors = errors
        return not errors
