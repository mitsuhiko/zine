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


class LoginForm(forms.Form):
    """The form for the login page.  All the validation happens in the
    context validate function and with error messages that display the
    message in a way that it can be displayed on top of all fields and
    not next to the field that caused the error.
    """
    user = forms.ModelField(User, 'username', message=
                            lazy_gettext('User "%(value)s" does not exist.'))
    password = forms.TextField(widget=forms.PasswordInput)
    permanent = forms.BooleanField()

    def context_validate(self, data):
        if not data['user']:
            raise forms.ValidationError(_('You have to enter a username'))
        if not data['user'].check_password(data['password']):
            raise forms.ValidationError(_('Incorrect password.'))


class ChangePasswordForm(forms.Form):
    """The form used on the password-change dialog in the admin panel."""
    old_password = forms.TextField(required=True, widget=forms.PasswordInput)
    new_password = forms.TextField(required=True, widget=forms.PasswordInput)
    check_password = forms.TextField(required=True,
                                     widget=forms.PasswordInput)

    def validate_old_password(self, value):
        if not self.request.user.check_password(value):
            raise forms.ValidationError(_('The old password you\'ve '
                                          'entered is wrong.'))

    def context_validate(self, data):
        if data['new_password'] != data['check_password']:
            raise forms.ValidationError(_('The two passwords don\'t match.'))
