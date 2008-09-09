# -*- coding: utf-8 -*-
"""
    zine.forms
    ~~~~~~~~~~

    The form classes the zine core uses.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from zine.i18n import _, lazy_gettext
from zine.models import User
from zine.utils import forms
from zine.utils.validators import ValidationError, is_valid_email, \
     is_valid_url


class LoginForm(forms.Form):
    """The form for the login page."""
    user = forms.ModelField(User, 'username', required=True, messages=dict(
        not_found=lazy_gettext('User "%(value)s" does not exist.'),
        required=lazy_gettext('You have to enter a username.')
    ))
    password = forms.TextField(widget=forms.PasswordInput)
    permanent = forms.BooleanField()

    def context_validate(self, data):
        if not data['user'].check_password(data['password']):
            raise ValidationError(_('Incorrect password.'))


class ChangePasswordForm(forms.Form):
    """The form used on the password-change dialog in the admin panel."""
    old_password = forms.TextField(required=True, widget=forms.PasswordInput)
    new_password = forms.TextField(required=True, widget=forms.PasswordInput)
    check_password = forms.TextField(required=True,
                                     widget=forms.PasswordInput)

    def validate_old_password(self, value):
        if not self.request.user.check_password(value):
            raise ValidationError(_('The old password you\'ve '
                                    'entered is wrong.'))

    def context_validate(self, data):
        if data['new_password'] != data['check_password']:
            raise ValidationError(_('The two passwords don\'t match.'))


class NewCommentForm(forms.Form):
    """The form for new comments."""
    name = forms.TextField(required=True, max_length=100)
    email = forms.TextField(required=True, validators=[is_valid_email])
    www = forms.TextField(validators=[is_valid_url])
    body = forms.TextField(min_length=2, max_length=6000, widget=forms.Textarea)
    parent = forms.TextField()
