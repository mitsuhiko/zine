# -*- coding: utf-8 -*-
"""
    zine.forms
    ~~~~~~~~~~

    The form classes the zine core uses.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime

from zine.i18n import _, lazy_gettext, list_languages
from zine.application import get_application, get_request, emit_event
from zine.database import db
from zine.models import User, Comment, Post, Category, STATUS_DRAFT, \
     STATUS_PUBLISHED, COMMENT_UNMODERATED
from zine.utils import forms, log
from zine.utils.http import redirect_to
from zine.utils.validators import ValidationError, is_valid_email, \
     is_valid_url, is_valid_slug, is_valid_url_prefix
from zine.utils.redirects import register_redirect


class LoginForm(forms.Form):
    """The form for the login page."""
    user = forms.ModelField(User, 'username', required=True, messages=dict(
        not_found=lazy_gettext(u'User "%(value)s" does not exist.'),
        required=lazy_gettext(u'You have to enter a username.')
    ), on_not_found=lambda user:
        log.warning(_('Failed login attempt, user "%s" does not exist')
                      % user, 'auth')
    )
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
        self.req = get_request()
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
        ip = self.req and self.req.remote_addr or '0.0.0.0'
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
        """The one-trick pony for commenting.  Passed a req it tries to
        use the req data to submit a comment to the post.  If the req
        is not a post req or the form is invalid the return value is None,
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

        #! this is sent directly after the comment was saved.  Useful if
        #! you want to send mail notifications or whatever.
        emit_event('after-comment-saved', req, comment)

        # Commit so that make_visible_for_request can access the comment id.
        db.commit()

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


class PostForm(forms.Form):
    """This is the baseclass for all forms that deal with posts.  There are
    two builtin subclasses for the builtin content types 'entry' and 'page'.
    """
    title = forms.TextField(lazy_gettext(u'Title'), max_length=150,
                            required=True)
    text = forms.TextField(lazy_gettext(u'Text'), max_length=65000,
                           widget=forms.Textarea)
    status = forms.ChoiceField(lazy_gettext(u'Publication status'), choices=[
                               (STATUS_DRAFT, lazy_gettext(u'Draft')),
                               (STATUS_PUBLISHED, lazy_gettext(u'Published'))])
    pub_date = forms.DateTimeField(lazy_gettext(u'Publication date'))
    slug = forms.TextField(lazy_gettext(u'Slug'), validators=[is_valid_slug()])
    author = forms.ModelField(User, 'username', lazy_gettext('Author'),
                              widget=forms.SelectBox)
    tags = forms.CommaSeparated(forms.TextField(), lazy_gettext(u'Tags'))
    categories = forms.Multiple(forms.ModelField(Category, 'category_id'),
                                lazy_gettext(u'Categories'),
                                widget=forms.CheckboxGroup)
    parser = forms.ChoiceField(lazy_gettext(u'Parser'))
    comments_enabled = forms.BooleanField(lazy_gettext(u'Enable comments'))
    pings_enabled = forms.BooleanField(lazy_gettext(u'Enable pingbacks'))
    ping_links = forms.BooleanField(lazy_gettext(u'Ping links'))

    #: the content type for this field.
    content_type = None

    def __init__(self, post=None, initial=None):
        self.app = get_application()
        self.post = post

        if post is not None:
            initial = forms.fill_dict(initial,
                title=post.title,
                text=post.text,
                status=post.status,
                pub_date=post.pub_date,
                slug=post.slug,
                author=post.author,
                tags=[x.name for x in post.tags],
                categories=[x.id for x in post.categories],
                parser=post.parser,
                comments_enabled=post.comments_enabled,
                pings_enabled=post.pings_enabled,
                ping_links=not post.parser_missing
            )
        else:
            initial = forms.fill_dict(initial, status=STATUS_DRAFT)

            # if we have a request, we can use the current user as a default
            req = get_request()
            if req and req.user:
                initial['author'] = req.user

        initial.setdefault('parser', self.app.cfg['default_parser'])

        self.author.choices = [x.username for x in User.query.all()]
        self.parser.choices = self.app.list_parsers()
        self.parser_missing = post and post.parser_missing
        if self.parser_missing:
            self.parser.choices.append((post.parser, _('%s (missing)') %
                                        post.parser.title()))

        self.categories.choices = [(c.id, c.name) for c in
                                   Category.query.all()]

        forms.Form.__init__(self, initial)

    def validate_slug(self, value):
        """Make sure the slug is unique."""
        query = Post.query.filter_by(slug=value)
        if self.post is not None:
            query = query.filter(Post.id != self.post.id)
        existing = query.first()
        if existing is not None:
            raise ValidationError(_('This slug is already in use'))

    def validate_parser(self, value):
        """Make sure the missing parser is not selected."""
        if self.parser_missing and value == self.post.parser:
            raise ValidationError(_('The selected parser is no longer '
                                    'available on the system.'))

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.new = self.post is None
        widget.post = self.post
        widget.parser_missing = self.parser_missing
        return widget

    def make_post(self):
        """A helper function that creates a post object from the data."""
        data = self.data
        post = Post(data['title'], data['author'], data['text'], data['slug'],
                    content_type=self.content_type)
        post.bind_categories(data['categories'])
        post.bind_tags(data['tags'])
        self._set_common_attributes(post)
        return post

    def save_changes(self):
        """Save the changes back to the database.  This also adds a redirect
        if the slug changes.
        """
        old_slug = self.post.slug
        forms.set_fields(self.port, self.data, 'title', 'author', 'text')
        if self.data['slug']:
            self.post.slug = self.data['slug']
        else:
            self.post.set_auto_slug()
        add_redirect = self.post.is_published and old_slug != self.post.slug
        self._set_common_attributes(self.post)
        if add_redirect:
            register_redirect(old_slug, self.post.slug)

    def _set_common_attributes(self, post):
        forms.set_fields(post, self.data, 'comments_enabled', 'pings_enabled',
                         'status', 'parser')
        post.bind_categories(self.data['categories'])
        post.bind_tags(self.data['tags'])

        now = datetime.utcnow()
        pub_date = self.data['pub_date']
        if pub_date is None and post.status == STATUS_PUBLISHED:
            pub_date = now
        post.pub_date = pub_date
        post.last_update = now


class EntryForm(PostForm):
    content_type = 'entry'

    def __init__(self, post=None, initial=None):
        app = get_application()
        PostForm.__init__(self, post, forms.fill_dict(initial,
            comments_enabled=app.cfg['comments_enabled'],
            pings_enabled=app.cfg['pings_enabled'],
            ping_links=True
        ))


class PageForm(PostForm):
    content_type = 'page'


class PostDeleteForm(forms.Form):
    """Baseclass for deletion forms of posts."""

    def __init__(self, post=None, initial=None):
        self.app = get_application()
        self.post = post
        forms.Form.__init__(self, initial)

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.post = self.post
        return widget

    def delete_post(self):
        """Deletes the post from the db."""
        emit_event('before-post-deleted', self.post)
        db.delete(self.post)


class EditCommentForm(forms.Form):
    """Form for comment editing in admin."""
    author = forms.TextField(lazy_gettext(u'Author'), required=True)
    email = forms.TextField(lazy_gettext(u'Email'),
                            validators=[is_valid_email()])
    www = forms.TextField(lazy_gettext(u'Website'),
                          validators=[is_valid_url()])
    text = forms.TextField(lazy_gettext(u'Text'), widget=forms.Textarea)
    pub_date = forms.DateTimeField(lazy_gettext(u'Date'), required=True)
    parser = forms.ChoiceField(lazy_gettext(u'Parser'), required=True)
    blocked = forms.BooleanField(lazy_gettext(u'Block Comment'))
    blocked_msg = forms.TextField(lazy_gettext(u'Reason'))

    def __init__(self, comment, initial=None):
        self.app = get_application()
        self.comment = comment
        initial = forms.fill_dict(initial,
            author=comment.author,
            email=comment.email,
            www=comment.www,
            text=comment.text,
            pub_date=comment.pub_date,
            parser=comment.parser,
            blocked=comment.blocked,
            blocked_msg=comment.blocked_msg
        )
        self.parser.choices = self.app.list_parsers()
        self.parser_missing = comment.parser_missing
        if self.parser_missing:
            self.parser.choices.append((post.parser, _('%s (missing)') %
                                        post.parser.title()))
        forms.Form.__init__(self, initial)

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.comment = self.comment
        return widget

    def save_changes(self):
        """Save the changes back to the database."""
        forms.set_fields(self.comment, self.data, 'text', 'pub_date', 'parser',
                         'blocked', 'blocked_msg')

        # only apply these if the comment is not anonymous
        if self.comment.anonymous:
            forms.set_fields(self.comment, self.data, 'author', 'email', 'www')


class ConfigForm(forms.Form):

    def __init__(self, initial=None):
        self.app = get_application()
        if initial is None:
            initial = {}
            for name in self.fields:
                initial[name] = self.app.cfg[name]
        forms.Form.__init__(self, initial)

    def apply(self):
        t = self.app.cfg.edit()
        for key, value in self.data.iteritems():
            if t[key] != value:
                t[key] = value
        t.commit()


class LogForm(ConfigForm):
    """A form for the logfiles."""
    log_file = forms.TextField(lazy_gettext(u'Filename'))
    log_level = forms.ChoiceField(lazy_gettext(u'Log Level'),
                                  choices=[(k, lazy_gettext(k)) for k, v
                                           in sorted(log.LEVELS.items(),
                                                     key=lambda x: x[1])])


class BasicOptionsForm(ConfigForm):
    """The form where the basic options are changed."""
    blog_title = forms.TextField(lazy_gettext(u'Blog title'))
    blog_tagline = forms.TextField(lazy_gettext(u'Blog tagline'))
    blog_email = forms.TextField(lazy_gettext(u'Blog email'))
    language = forms.ChoiceField(lazy_gettext(u'Language'))
    session_cookie_name = forms.TextField(lazy_gettext(u'Cookie Name'))
    comments_enabled = forms.BooleanField(lazy_gettext(u'Comments enabled'),
        help_text=lazy_gettext(u'enable comments per default'))
    moderate_comments = forms.ChoiceField(lazy_gettext(u'Comment Moderation'),
                                          choices=[
        (0, lazy_gettext(u'Automatically approve all comments')),
        (1, lazy_gettext(u'An administrator must always aprove the comment')),
        (2, lazy_gettext(u'Automatically approve comments by known comment authors'))
    ], widget=forms.RadioButtonGroup)
    pings_enabled = forms.BooleanField(lazy_gettext(u'Pingbacks enabled'),
        help_text=lazy_gettext(u'enable pingbacks per default'))
    use_flat_comments = forms.BooleanField(lazy_gettext(u'Use flat comments'),
        help_text=lazy_gettext(u'All comments are posted top-level'))
    default_parser = forms.ChoiceField(lazy_gettext(u'Default parser'))
    comment_parser = forms.ChoiceField(lazy_gettext(u'Comment parser'))
    posts_per_page = forms.IntegerField(lazy_gettext(u'Posts per page'))

    def __init__(self, initial=None):
        ConfigForm.__init__(self, initial)
        self.language.choices = list_languages()
        self.default_parser.choices = self.comment_parser.choices = \
            self.app.list_parsers()


class URLOptionsForm(ConfigForm):
    """The form for url changes."""
    blog_url_prefix = forms.TextField(lazy_gettext(u'Blog URL prefix'),
                                      validators=[is_valid_url_prefix()])
    admin_url_prefix = forms.TextField(lazy_gettext(u'Admin URL prefix'),
                                       validators=[is_valid_url_prefix()])
    category_url_prefix = forms.TextField(lazy_gettext(u'Category URL prefix'),
                                          validators=[is_valid_url_prefix()])
    tags_url_prefix = forms.TextField(lazy_gettext(u'Tag URL prefix'),
                                      validators=[is_valid_url_prefix()])
    profiles_url_prefix = forms.TextField(lazy_gettext(u'Author Profiles URL prefix'),
                                          validators=[is_valid_url_prefix()])
