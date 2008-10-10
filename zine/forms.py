# -*- coding: utf-8 -*-
"""
    zine.forms
    ~~~~~~~~~~

    The form classes the zine core uses.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from zine.i18n import _, lazy_gettext
from zine.application import get_application, emit_event
from zine.database import db
from zine.models import User, Comment
from zine.utils import forms, log
from zine.utils.http import redirect_to
from zine.utils.validators import ValidationError, is_valid_email, \
     is_valid_url


class LoginForm(forms.Form):
    """The form for the login page."""
    user = forms.ModelField(User, 'username', required=True, messages=dict(
        not_found=lazy_gettext(u'User "%(value)s" does not exist.'),
        required=lazy_gettext(u'You have to enter a username.')
    ))
    password = forms.TextField(widget=forms.PasswordInput)
    permanent = forms.BooleanField()

    def context_validate(self, data):
        if not data['user'].check_password(data['password']):
            log.warning(_('Failed login attempt from "%s", invalid password')
                        % data['user'].username, 'auth')
            raise ValidationError(_('Incorrect password.'))


class ChangePasswordForm(forms.Form):
    """The form used on the password-change dialog in the admin panel."""
    old_password = forms.TextField(lazy_gettext(u'Old password'), required=True,
                                   widget=forms.PasswordInput)
    new_password = forms.TextField(lazy_gettext(u'New password'), required=True,
                                   widget=forms.PasswordInput)
    check_password = forms.TextField(lazy_gettext(u'Repeat password'),
                                     required=True,
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
    author = forms.TextField(lazy_gettext(u'Name*'), required=True,
                             max_length=100, messages=dict(
        too_long=lazy_gettext(u'Your name is too long.'),
        required=lazy_gettext(u'You have to enter your name.')
    ))
    email = forms.TextField(lazy_gettext(u'Mail* (not published)'),
                            required=True, validators=[is_valid_email()],
                            messages=dict(
        required=lazy_gettext(u'You have to enter a valid e-mail address.')
    ))
    www = forms.TextField(lazy_gettext(u'Website'), validators=[is_valid_url(
        message=lazy_gettext(u'You have to enter a valid URL or omit the field.')
    )])
    body = forms.TextField(lazy_gettext(u'Text'), min_length=2, max_length=6000,
                           messages=dict(
        too_short=lazy_gettext(u'Your comment is too short.'),
        too_long=lazy_gettext(u'Your comment is too long.'),
        required=lazy_gettext(u'You have to enter a comment.')
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

    def context_validate(self, data):
        if not self.post.comments_enabled:
            raise ValidationError(_('Post is closed for commenting.'))

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

    def create_if_valid(self, req):
        """The one-trick pony for commenting.  Passed a request it tries to
        use the request data to submit a comment to the post.  If the request
        is not a post request or the form is invalid the return value is None,
        otherwise a redirect response to the new comment.
        """
        if req.method != 'POST' or not self.validate(req.form):
            return

        # if we don't have errors let's save it and emit an
        # `before-comment-saved` event so that plugins can do
        # block comments so that administrators have to approve it
        comment = self.make_comment()

        #! use this event to block comments before they are saved.  This
        #! is useful for antispam and other ways of moderation.
        emit_event('before-comment-saved', req, comment)

        # Moderate Comment?  Now that the spam check any everything
        # went through the processing we explicitly set it to
        # unmodereated if the blog configuration demands that
        if not comment.blocked and comment.requires_moderation:
            comment.status = COMMENT_UNMODERATED
            comment.blocked_msg = _(u'Comment waiting for approval')

        db.commit()

        #! this is sent directly after the comment was saved.  Useful if
        #! you want to send mail notifications or whatever.
        emit_event('after-comment-saved', req, comment)

        # Still allow the user to see his comment if it's blocked
        if comment.blocked:
            comment.make_visible_for_request(req)

        return redirect_to(self.post)


class PluginForm(forms.Form):
    """The form for plugin activation and deactivation."""
    active_plugins = forms.MultiChoiceField(widget=forms.CheckboxGroup)
    disable_guard = forms.BooleanField(lazy_gettext(u'Disable plugin guard'),
        help_text=lazy_gettext(u'If the plugin guard is disabled errors '
                               u'on plugin setup are not catched.'))

    def __init__(self, initial=None):
        self.app = app = get_application()
        self.active_plugins.choices = sorted([(x.name, x.display_name)
                                              for x in app.plugins.values()],
                                             key=lambda x: x[1].lower())
        if initial is None:
            initial = dict(
                active_plugins=[x.name for x in app.plugins.itervalues()
                                if x.active],
                disable_guard=not app.cfg['plugin_guard']
            )
        forms.Form.__init__(self, initial)

    def apply(self):
        """Apply the changes."""
        t = self.app.cfg.edit()
        t['plugins'] = u', '.join(sorted(self.data['active_plugins']))
        t['plugin_guard'] = not self.data['disable_guard']
        t.commit()


class LogForm(forms.Form):
    """A form for the logfiles."""
    filename = forms.TextField(lazy_gettext(u'Filename'))
    level = forms.ChoiceField(lazy_gettext(u'Log Level'),
                              choices=[(k, lazy_gettext(k)) for k, v
                                       in sorted(log.LEVELS.items(),
                                                 key=lambda x: x[1])])

    def __init__(self, initial=None):
        self.app = app = get_application()
        if initial is None:
            initial = dict(
                filename=app.cfg['log_file'],
                level=app.cfg['log_level']
            )
        forms.Form.__init__(self, initial)

    def apply(self):
        """Apply the changes."""
        t = self.app.cfg.edit()
        t['log_file'] = self.data['filename']
        t['log_level'] = self.data['level']
        t.commit()
