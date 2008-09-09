# -*- coding: utf-8 -*-
"""
    zine.forms
    ~~~~~~~~~~

    The form classes the zine core uses.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from zine.i18n import _, lazy_gettext
from zine.models import User, Comment
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

    def __init__(self, user, initial=None):
        forms.Form.__init__(self, initial)
        self.user = user

    def validate_old_password(self, value):
        if not self.user.check_password(value):
            raise ValidationError(_('The old password you\'ve '
                                    'entered is wrong.'))

    def context_validate(self, data):
        if data['new_password'] != data['check_password']:
            raise ValidationError(_('The two passwords don\'t match.'))


class NewCommentForm(forms.Form):
    """New comment form for authors."""
    author = forms.TextField(required=True, max_length=100, messages=dict(
        too_long=lazy_gettext('Your name is too long.'),
        required=lazy_gettext('You have to enter your name.')
    ))
    email = forms.TextField(required=True, validators=[is_valid_email()],
                            messages=dict(
        required=lazy_gettext('You have to enter a valid e-mail address.')
    ))
    www = forms.TextField(validators=[is_valid_url(
        message=lazy_gettext('You have to enter a valid URL or omit the field.')
    )])
    body = forms.TextField(min_length=2, max_length=6000, messages=dict(
        too_short=lazy_gettext('Your comment is too short.'),
        too_long=lazy_gettext('Your comment is too long.'),
        required=lazy_gettext('You have to enter a comment.')
    ), widget=forms.Textarea)
    parent = forms.HiddenModelField(Comment)

    def __init__(self, post, user, initial=None):
        forms.Form.__init__(self, initial)
        self.post = post
        self.user = user

        # if the user is logged in the form is a bit smaller
        if user.is_somebody:
            del self.fields['author'], self.fields['email'], self.fields['www']

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.small_form = self.user.is_somebody
        return widget

    def validate_parent(self, value):
        # this message is only displayed if the user tempered with
        # the form data
        if value.post != self.post:
            raise ValidationError(_('Invalid object referenced.'))

    def make_comment(self):
        """A handy helper to create a comment from the validated form."""
        ip = self.request and self.request.remote_addr or '0.0.0.0'
        if self.user.is_somebody:
            author = self.user
            email = www = None
        else:
            author = self['author']
            email = self['email']
            www = self['www']
        return Comment(self.post, author, self['body'], email, www,
                       self['parent'], submitter_ip=ip)
