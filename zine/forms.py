# -*- coding: utf-8 -*-
"""
    zine.forms
    ~~~~~~~~~~

    The form classes the zine core uses.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from copy import copy
from datetime import datetime

from zine.i18n import _, lazy_gettext, list_languages
from zine.application import get_application, get_request, emit_event
from zine.config import DEFAULT_VARS
from zine.database import db, posts
from zine.models import User, Group, Comment, Post, Category, Tag, \
     NotificationSubscription, STATUS_DRAFT, STATUS_PUBLISHED, \
     STATUS_PROTECTED, STATUS_PRIVATE, \
     COMMENT_UNMODERATED, COMMENT_MODERATED, \
     COMMENT_BLOCKED_USER, COMMENT_BLOCKED_SPAM, COMMENT_DELETED
from zine.parsers import render_preview
from zine.privileges import bind_privileges
from zine.notifications import send_notification_template, NEW_COMMENT, \
     COMMENT_REQUIRES_MODERATION
from zine.utils import forms, log, dump_json
from zine.utils.http import redirect_to
from zine.utils.validators import ValidationError, is_valid_email, \
     is_valid_url, is_valid_slug, is_not_whitespace_only
from zine.utils.redirects import register_redirect, change_url_prefix


def config_field(cfgvar, label=None, **kwargs):
    """Helper function for fetching fields from the config."""
    if isinstance(cfgvar, forms.Field):
        field = copy(cfgvar)
    else:
        field = copy(DEFAULT_VARS[cfgvar])
    field._position_hint = forms._next_position_hint()
    if label is not None:
        field.label = label
    for name, value in kwargs.iteritems():
        setattr(field, name, value)
    return field


class LoginForm(forms.Form):
    """The form for the login page."""
    user = forms.ModelField(User, 'username', required=True, messages=dict(
        not_found=lazy_gettext(u'User “%(value)s” does not exist.'),
        required=lazy_gettext(u'You have to enter a username.')
    ), on_not_found=lambda user:
        log.warning(_(u'Failed login attempt, user “%s” does not exist')
                      % user, 'auth')
    )
    password = forms.TextField(widget=forms.PasswordInput)
    permanent = forms.BooleanField()

    def context_validate(self, data):
        if not data['user'].check_password(data['password']):
            log.warning(_(u'Failed login attempt from “%s”, invalid password')
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
    # implementation detail: the maximum length of the column in the
    # database is longer than that.  However we don't want users to
    # insert too long names there.  The long column is reserved for
    # pingbacks and such.
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
                           required=True, messages=dict(
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
        if value.post != self.post:
            #_ this message is only displayed if the user tempered with
            #_ the form data
            raise ValidationError(_('Invalid object referenced.'))

    def context_validate(self, data):
        if not self.post.comments_enabled:
            raise ValidationError(_('Post is closed for commenting.'))
        if self.post.comments_closed:
            raise ValidationError(_('Commenting is no longer possible.'))

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

        # send out a notification if the comment is not spam.  Nobody is
        # interested in notifications on spam...
        if not comment.is_spam:
            if comment.blocked:
                notification_type = COMMENT_REQUIRES_MODERATION
            else:
                notification_type = NEW_COMMENT
            send_notification_template(notification_type,
                'notifications/on_new_comment.zeml',
                user=req.user, comment=comment)

        # Still allow the user to see his comment if it's blocked
        if comment.blocked:
            comment.make_visible_for_request(req)

        return redirect_to(self.post)


class PluginForm(forms.Form):
    """The form for plugin activation and deactivation."""
    active_plugins = forms.MultiChoiceField(widget=forms.CheckboxGroup)
    disable_guard = forms.BooleanField(lazy_gettext(u'Disable plugin guard'),
        help_text=lazy_gettext(u'If the plugin guard is disabled errors '
                               u'on plugin setup are not caught.'))

    def __init__(self, initial=None):
        self.app = app = get_application()
        self.active_plugins.choices = sorted([(x.name, x.display_name)
                                              for x in app.plugins.values()],
                                             key=lambda x: x[1].lower())
        if initial is None:
            initial = dict(
                active_plugins=[x.name for x in app.plugins.itervalues()
                                if x.active]
            )
        forms.Form.__init__(self, initial)

    def apply(self):
        """Apply the changes."""
        t = self.app.cfg.edit()
        t['plugins'] = u', '.join(sorted(self.data['active_plugins']))
        t.commit()


class RemovePluginForm(forms.Form):
    """Dummy form for plugin removing."""

    def __init__(self, plugin):
        forms.Form.__init__(self)
        self.plugin = plugin


class PostForm(forms.Form):
    """This is the baseclass for all forms that deal with posts.  There are
    two builtin subclasses for the builtin content types 'entry' and 'page'.
    """
    title = forms.TextField(lazy_gettext(u'Title'), max_length=150,
                            validators=[is_not_whitespace_only()],
                            required=False)
    text = forms.TextField(lazy_gettext(u'Text'), max_length=65000,
                           widget=forms.Textarea)
    status = forms.ChoiceField(lazy_gettext(u'Publication status'), choices=[
                               (STATUS_DRAFT, lazy_gettext(u'Draft')),
                               (STATUS_PUBLISHED, lazy_gettext(u'Published')),
                               (STATUS_PROTECTED, lazy_gettext(u'Protected')),
                               (STATUS_PRIVATE, lazy_gettext(u'Private'))])
    pub_date = forms.DateTimeField(lazy_gettext(u'Publication date'),
        help_text=lazy_gettext(u'Clear this field to update to current time'))
    slug = forms.TextField(lazy_gettext(u'Slug'), validators=[is_valid_slug()],
        help_text=lazy_gettext(u'Clear this field to autogenerate a new slug'))
    author = forms.ModelField(User, 'username', lazy_gettext('Author'),
                              widget=forms.SelectBox)
    tags = forms.CommaSeparated(forms.TextField(), lazy_gettext(u'Tags'))
    categories = forms.Multiple(forms.ModelField(Category, 'id'),
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
        self.preview = False

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

        # if we have have an old post and the parser is not missing and
        # it was published when the form was created we collect the old
        # posts so that we don't have to ping them another time.
        self._old_links = set()
        if self.post is not None and not self.post.parser_missing and \
           self.post.is_published:
            self._old_links.update(self.post.find_urls())

    def validate(self, data):
        """We only validate if we're not in preview mode."""
        self.preview = 'preview' in data
        return forms.Form.validate(self, data) and not self.preview

    def find_new_links(self):
        """Return a list of all new links."""
        for link in self.post.find_urls():
            if not link in self._old_links:
                yield link

    def validate_slug(self, value):
        """Make sure the slug is unique."""
        query = Post.query.filter_by(slug=value)
        if self.post is not None:
            query = query.filter(Post.id != self.post.id)
        existing = query.first()
        if existing is not None:
            raise ValidationError(_('This slug is already in use.'))

    def validate_parser(self, value):
        """Make sure the missing parser is not selected."""
        if self.parser_missing and value == self.post.parser:
            raise ValidationError(_('Selected parser is no longer '
                                    'available on the system.'))

    def render_preview(self):
        """Renders the preview for the post."""
        return render_preview(self.data['text'], self.data['parser'])

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.new = self.post is None
        widget.post = self.post
        widget.preview = self.preview
        widget.render_preview = self.render_preview
        widget.parser_missing = self.parser_missing
        return widget

    def make_post(self):
        """A helper function that creates a post object from the data."""
        data = self.data
        post = Post(data['title'], data['author'], data['text'], data['slug'],
                    parser=data['parser'], content_type=self.content_type,
                    pub_date=data['pub_date'])
        post.bind_categories(data['categories'])
        post.bind_tags(data['tags'])
        self._set_common_attributes(post)
        self.post = post
        return post

    def save_changes(self):
        """Save the changes back to the database.  This also adds a redirect
        if the slug changes.
        """
        if not self.data['pub_date']:
            # If user deleted publication timestamp, make a new one.
            self.data['pub_date'] = datetime.utcnow()
        old_slug = self.post.slug
        old_parser = self.post.parser
        forms.set_fields(self.post, self.data, 'title', 'author', 'parser')
        if (self.data['text'] != self.post.text
            or self.data['parser'] != old_parser):
            self.post.text = self.data['text']
        add_redirect = self.post.is_published and old_slug != self.post.slug

        self.post.touch_times(self.data['pub_date'])
        self.post.bind_slug(self.data['slug'])

        self._set_common_attributes(self.post)
        if add_redirect:
            register_redirect(old_slug, self.post.slug)

    def _set_common_attributes(self, post):
        forms.set_fields(post, self.data, 'comments_enabled', 'pings_enabled',
                         'status')
        post.bind_categories(self.data['categories'])
        post.bind_tags(self.data['tags'])

    def taglist(self):
        """Return all available tags as a JSON-encoded list."""
        tags = [t.name for t in Tag.query.all()]
        return dump_json(tags)


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


class _CommentBoundForm(forms.Form):
    """Internal baseclass for comment bound forms."""

    def __init__(self, comment, initial=None):
        self.app = get_application()
        self.comment = comment
        forms.Form.__init__(self, initial)

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.comment = self.comment
        return widget


class EditCommentForm(_CommentBoundForm):
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
        _CommentBoundForm.__init__(self, comment, forms.fill_dict(initial,
            author=comment.author,
            email=comment.email,
            www=comment.www,
            text=comment.text,
            pub_date=comment.pub_date,
            parser=comment.parser,
            blocked=comment.blocked,
            blocked_msg=comment.blocked_msg
        ))
        self.parser.choices = self.app.list_parsers()
        self.parser_missing = comment.parser_missing
        if self.parser_missing and comment.parser is not None:
            self.parser.choices.append((comment.parser, _('%s (missing)') %
                                        comment.parser.title()))

    def save_changes(self):
        """Save the changes back to the database."""
        old_parser = self.comment.parser
        forms.set_fields(self.comment, self.data, 'pub_date', 'parser',
                         'blocked_msg')

        if (self.data['text'] != self.comment.text
            or self.data['parser'] != old_parser):
            self.comment.text = self.data['text']

        # update status
        if self.data['blocked']:
            if not self.comment.blocked:
                self.comment.status = COMMENT_BLOCKED_USER
        else:
            self.comment.status = COMMENT_MODERATED

        # only apply these if the comment is not anonymous
        if self.comment.anonymous:
            forms.set_fields(self.comment, self.data, 'author', 'email', 'www')


class DeleteCommentForm(_CommentBoundForm):
    """Helper form that is used to delete comments."""

    def delete_comment(self):
        """Deletes the comment from the db."""
        delete_comment(self.comment)


class ApproveCommentForm(_CommentBoundForm):
    """Helper form for comment approvement."""

    def approve_comment(self):
        """Approve the comment."""
        #! plugins can use this to react to comment approvals.
        emit_event('before-comment-approved', self.comment)
        self.comment.status = COMMENT_MODERATED
        self.comment.blocked_msg = u''


class BlockCommentForm(_CommentBoundForm):
    """Form used to block comments."""

    message = forms.TextField(lazy_gettext(u'Reason'))

    def __init__(self, comment, initial=None):
        self.req = get_request()
        _CommentBoundForm.__init__(self, comment, initial)

    def block_comment(self):
        msg = self.data['message']
        if not msg and self.req:
            msg = _(u'blocked by %s') % self.req.user.display_name
        self.comment.status = COMMENT_BLOCKED_USER
        self.comment.bocked_msg = msg


class MarkCommentForm(_CommentBoundForm):
    """Form used to block comments."""

    def __init__(self, comment, initial=None):
        self.req = get_request()
        _CommentBoundForm.__init__(self, comment, initial)

    def mark_as_spam(self):
        emit_event('before-comment-mark-spam', self.comment)
        self.comment.status = COMMENT_BLOCKED_SPAM
        self.comment.blocked_msg = _("Comment reported as spam by %s" %
                                    get_request().user.display_name)
    def mark_as_ham(self):
        emit_event('before-comment-mark-ham', self.comment)
        emit_event('before-comment-approved', self.comment)
        self.comment.status = COMMENT_MODERATED
        self.comment.blocked_msg = u''


class _CategoryBoundForm(forms.Form):
    """Internal baseclass for category bound forms."""

    def __init__(self, category, initial=None):
        self.app = get_application()
        self.category = category
        forms.Form.__init__(self, initial)

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.category = self.category
        widget.new = self.category is None
        return widget


class EditCategoryForm(_CategoryBoundForm):
    """Form that is used to edit or create a category."""

    slug = forms.TextField(lazy_gettext(u'Slug'), validators=[is_valid_slug()])
    name = forms.TextField(lazy_gettext(u'Name'), max_length=50, required=True,
                           validators=[is_not_whitespace_only()])
    description = forms.TextField(lazy_gettext(u'Description'),
                                  max_length=5000, widget=forms.Textarea)

    def __init__(self, category=None, initial=None):
        if category is not None:
            initial = forms.fill_dict(initial,
                slug=category.slug,
                name=category.name,
                description=category.description
            )
        _CategoryBoundForm.__init__(self, category, initial)

    def validate_slug(self, value):
        """Make sure the slug is unique."""
        query = Category.query.filter_by(slug=value)
        if self.category is not None:
            query = query.filter(Category.id != self.category.id)
        existing = query.first()
        if existing is not None:
            raise ValidationError(_('This slug is already in use'))

    def make_category(self):
        """A helper function that creates a category object from the data."""
        category = Category(self.data['name'], self.data['description'],
                            self.data['slug'] or None)
        self.category = category
        return category

    def save_changes(self):
        """Save the changes back to the database.  This also adds a redirect
        if the slug changes.
        """
        old_slug = self.category.slug
        forms.set_fields(self.category, self.data, 'name', 'description')
        if self.data['slug']:
            self.category.slug = self.data['slug']
        elif not self.category.slug:
            self.category.set_auto_slug()
        if old_slug != self.category.slug:
            register_redirect(old_slug, self.category.slug)


class DeleteCategoryForm(_CategoryBoundForm):
    """Used for deleting categories."""

    def delete_category(self):
        """Delete the category from the database."""
        #! plugins can use this to react to category deletes.  They can't stop
        #! the deleting of the category but they can delete information in
        #! their own tables so that the database is consistent afterwards.
        emit_event('before-category-deleted', self.category)
        db.delete(self.category)


class CommentMassModerateForm(forms.Form):
    """This form is used for comment mass moderation."""
    selected_comments = forms.MultiChoiceField(widget=forms.CheckboxGroup)
    per_page = forms.ChoiceField(choices=[20, 40, 60, 80, 100],
                                 label=lazy_gettext('Comments Per Page:'))

    def __init__(self, comments, initial=None):
        self.comments = comments
        self.selected_comments.choices = [c.id for c in self.comments]
        forms.Form.__init__(self, initial)

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.comments = self.comments
        return widget

    def iter_selection(self):
        selection = set(self.data['selected_comments'])
        for comment in self.comments:
            if comment.id in selection:
                yield comment

    def delete_selection(self):
        for comment in self.iter_selection():
            delete_comment(comment)

    def approve_selection(self, comment=None):
        if comment:
            emit_event('before-comment-approved', comment)
            comment.status = COMMENT_MODERATED
            comment.blocked_msg = u''
        else:
            for comment in self.iter_selection():
                emit_event('before-comment-approved', comment)
                comment.status = COMMENT_MODERATED
                comment.blocked_msg = u''

    def block_selection(self):
        for comment in self.iter_selection():
            emit_event('before-comment-blocked', comment)
            comment.status = COMMENT_BLOCKED_USER
            comment.blocked_msg = _("Comment blocked by %s" %
                                    get_request().user.display_name)

    def mark_selection_as_spam(self):
        for comment in self.iter_selection():
            emit_event('before-comment-mark-spam', comment)
            comment.status = COMMENT_BLOCKED_SPAM
            comment.blocked_msg = _("Comment marked as spam by %s" %
                                    get_request().user.display_name)
    def mark_selection_as_ham(self):
        for comment in self.iter_selection():
            emit_event('before-comment-mark-ham', comment)
            self.approve_selection(comment)


class _GroupBoundForm(forms.Form):
    """Internal baseclass for group bound forms."""

    def __init__(self, group, initial=None):
        forms.Form.__init__(self, initial)
        self.app = get_application()
        self.group = group

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.group = self.group
        widget.new = self.group is None
        return widget


class EditGroupForm(_GroupBoundForm):
    """Edit or create a group."""

    groupname = forms.TextField(lazy_gettext(u'Groupname'), max_length=30,
                                validators=[is_not_whitespace_only()],
                                required=True)
    privileges = forms.MultiChoiceField(lazy_gettext(u'Privileges'),
                                        widget=forms.CheckboxGroup)

    def __init__(self, group=None, initial=None):
        if group is not None:
            initial = forms.fill_dict(initial,
                groupname=group.name,
                privileges=[x.name for x in group.privileges]
            )
        _GroupBoundForm.__init__(self, group, initial)
        self.privileges.choices = self.app.list_privileges()

    def validate_groupname(self, value):
        query = Group.query.filter_by(name=value)
        if self.group is not None:
            query = query.filter(Group.id != self.group.id)
        if query.first() is not None:
            raise ValidationError(_('This groupname is already in use'))

    def _set_common_attributes(self, group):
        forms.set_fields(group, self.data)
        bind_privileges(group.privileges, self.data['privileges'])

    def make_group(self):
        """A helper function that creates a new group object."""
        group = Group(self.data['groupname'])
        self._set_common_attributes(group)
        self.group = group
        return group

    def save_changes(self):
        """Apply the changes."""
        self.group.name = self.data['groupname']
        self._set_common_attributes(self.group)


class DeleteGroupForm(_GroupBoundForm):
    """Used to delete a group from the admin panel."""

    action = forms.ChoiceField(lazy_gettext(u'What should Zine do with users '
                                            u'assigned to this group?'),
                              choices=[
        ('delete_membership', lazy_gettext(u'Do nothing, just detach the membership')),
        ('relocate', lazy_gettext(u'Move the users to another group'))
    ], widget=forms.RadioButtonGroup)
    relocate_to = forms.ModelField(Group, 'id', lazy_gettext(u'Relocate users to'),
                                   widget=forms.SelectBox)

    def __init__(self, group, initial=None):
        self.relocate_to.choices = [('', u'')] + [
            (g.id, g.name) for g in Group.query.filter(Group.id != group.id)
        ]

        _GroupBoundForm.__init__(self, group, forms.fill_dict(initial,
            action='delete_membership'))

    def context_validate(self, data):
        if data['action'] == 'relocate' and not data['relocate_to']:
            raise ValidationError(_('You have to select a group that '
                                    'gets the users assigned.'))

    def delete_group(self):
        """Deletes a group."""
        if self.data['action'] == 'relocate':
            new_group = Group.query.filter_by(self.data['reassign_to'].id).first()
            for user in self.group.users:
                if not new_group in user.groups:
                    user.groups.append(new_group)
        db.commit()

        #! plugins can use this to react to user deletes.  They can't stop
        #! the deleting of the group but they can delete information in
        #! their own tables so that the database is consistent afterwards.
        #! Additional to the group object the form data is submitted.
        emit_event('before-group-deleted', self.group, self.data)
        db.delete(self.group)


class _UserBoundForm(forms.Form):
    """Internal baseclass for user bound forms."""

    def __init__(self, user, initial=None):
        forms.Form.__init__(self, initial)
        self.app = get_application()
        self.user = user

    def as_widget(self):
        widget = forms.Form.as_widget(self)
        widget.user = self.user
        widget.new = self.user is None
        return widget


class EditUserForm(_UserBoundForm):
    """Edit or create a user."""

    username = forms.TextField(lazy_gettext(u'Username'), max_length=30,
                               validators=[is_not_whitespace_only()],
                               required=True)
    real_name = forms.TextField(lazy_gettext(u'Realname'), max_length=180)
    display_name = forms.ChoiceField(lazy_gettext(u'Display name'))
    description = forms.TextField(lazy_gettext(u'Description'),
                                  max_length=5000, widget=forms.Textarea)
    email = forms.TextField(lazy_gettext(u'Email'), required=True,
                            validators=[is_valid_email()])
    www = forms.TextField(lazy_gettext(u'Website'),
                          validators=[is_valid_url()])
    password = forms.TextField(lazy_gettext(u'Password'),
                               widget=forms.PasswordInput)
    privileges = forms.MultiChoiceField(lazy_gettext(u'Privileges'),
                                        widget=forms.CheckboxGroup)
    groups = forms.MultiChoiceField(lazy_gettext(u'Groups'),
                                    widget=forms.CheckboxGroup)
    is_author = forms.BooleanField(lazy_gettext(u'List as author'),
        help_text=lazy_gettext(u'This user is listed as author'))

    def __init__(self, user=None, initial=None):
        if user is not None:
            initial = forms.fill_dict(initial,
                username=user.username,
                real_name=user.real_name,
                display_name=user._display_name,
                description=user.description,
                email=user.email,
                www=user.www,
                privileges=[x.name for x in user.own_privileges],
                groups=[g.name for g in user.groups],
                is_author=user.is_author
            )
        _UserBoundForm.__init__(self, user, initial)
        self.display_name.choices = [
            (u'$username', user and user.username or _('Username')),
            (u'$real_name', user and user.real_name or _('Realname'))
        ]
        self.privileges.choices = self.app.list_privileges()
        self.groups.choices = [g.name for g in Group.query.all()]
        self.password.required = user is None

    def validate_username(self, value):
        query = User.query.filter_by(username=value)
        if self.user is not None:
            query = query.filter(User.id != self.user.id)
        if query.first() is not None:
            raise ValidationError(_('This username is already in use'))

    def _set_common_attributes(self, user):
        forms.set_fields(user, self.data, 'www', 'real_name', 'description',
                         'display_name', 'is_author')
        bind_privileges(user.own_privileges, self.data['privileges'], user)
        bound_groups = set(g.name for g in user.groups)
        choosen_groups = set(self.data['groups'])
        group_mapping = dict((g.name, g) for g in Group.query.all())
        # delete groups
        for group in (bound_groups - choosen_groups):
            user.groups.remove(group_mapping[group])
        # and add new groups
        for group in (choosen_groups - bound_groups):
            user.groups.append(group_mapping[group])

    def make_user(self):
        """A helper function that creates a new user object."""
        user = User(self.data['username'], self.data['password'],
                    self.data['email'])
        self._set_common_attributes(user)
        self.user = user
        return user

    def save_changes(self):
        """Apply the changes."""
        self.user.username = self.data['username']
        if self.data['password']:
            self.user.set_password(self.data['password'])
        self.user.email = self.data['email']
        self._set_common_attributes(self.user)


class DeleteUserForm(_UserBoundForm):
    """Used to delete a user from the admin panel."""

    action = forms.ChoiceField(lazy_gettext(u'What should Zine do with posts '
                                            u'written by this user?'), choices=[
        ('delete', lazy_gettext(u'Delete them permanently')),
        ('reassign', lazy_gettext(u'Reassign posts'))
    ], widget=forms.RadioButtonGroup)
    reassign_to = forms.ModelField(User, 'id',
                                   lazy_gettext(u'Reassign posts to'),
                                   widget=forms.SelectBox)

    def __init__(self, user, initial=None):
        self.reassign_to.choices = [('', u'')] + [
            (u.id, u.username)
            for u in User.query.filter(User.id != user.id)
        ]
        _UserBoundForm.__init__(self, user, forms.fill_dict(initial,
            action='reassign'
        ))

    def context_validate(self, data):
        if self.user.posts.count() is 0:
            data['action'] = None
        if data['action'] == 'reassign' and not data['reassign_to']:
            raise ValidationError(_('You have to select a user to reassign '
                                    'the posts to.'))

    def delete_user(self):
        """Deletes the user."""
        if self.data['action'] == 'reassign':
            db.execute(posts.update(posts.c.author_id == self.user.id), dict(
                author_id=self.data['reassign_to'].id
            ))

        # find all the comments by this author and make them comments that
        # are no longer linked to the author.
        for comment in self.user.comments.all():
            comment.unbind_user()

        #! plugins can use this to react to user deletes.  They can't stop
        #! the deleting of the user but they can delete information in
        #! their own tables so that the database is consistent afterwards.
        #! Additional to the user object the form data is submitted.
        emit_event('before-user-deleted', self.user, self.data)
        db.delete(self.user)


class EditProfileForm(_UserBoundForm):
    """Edit or create a user's profile."""

    username = forms.TextField(lazy_gettext(u'Username'), max_length=30,
                               validators=[is_not_whitespace_only()],
                               required=True)
    real_name = forms.TextField(lazy_gettext(u'Realname'), max_length=180)
    display_name = forms.ChoiceField(lazy_gettext(u'Display name'))
    description = forms.TextField(lazy_gettext(u'Description'),
                                  max_length=5000, widget=forms.Textarea)
    email = forms.TextField(lazy_gettext(u'Email'), required=True,
                            validators=[is_valid_email()])
    www = forms.TextField(lazy_gettext(u'Website'),
                          validators=[is_valid_url()])
    password = forms.TextField(lazy_gettext(u'Password'),
                               widget=forms.PasswordInput)
    password_confirm = forms.TextField(lazy_gettext(u'Confirm password'),
                                       widget=forms.PasswordInput,
                                       help_text=lazy_gettext(u'Confirm password'))

    def __init__(self, user=None, initial=None):
        if user is not None:
            initial = forms.fill_dict(initial,
                username=user.username,
                real_name=user.real_name,
                display_name=user._display_name,
                description=user.description,
                email=user.email,
                www=user.www
            )
        _UserBoundForm.__init__(self, user, initial)
        self.display_name.choices = [
            (u'$username', user and user.username or _('Username')),
            (u'$real_name', user and user.real_name or _('Realname'))
        ]

    def validate_email(self, value):
        query = User.query.filter_by(email=value)
        if self.user is not None:
            query = query.filter(User.id != self.user.id)
        if query.first() is not None:
            raise ValidationError(_('This email address is already in use'))

    def validate_password(self, value):
        if 'password_confirm' in self.data:
            password_confirm = self.data['password_confirm']
        else:
            password_confirm = self.request.values.get('password_confirm', '')
        if ((not value == password_confirm) or (value and not password_confirm)
            or (password_confirm and not value)):
            raise ValidationError(_('Passwords do not match'))


    def save_changes(self):
        """Apply the changes."""
        if self.data['password']:
            self.user.set_password(self.data['password'])
        self.user.real_name = self.data['real_name']
        self.user.display_name = self.data['display_name']
        self.user.description = self.data['description']
        self.user.email = self.data['email']
        self.user.www = self.data['www']


class DeleteAccountForm(_UserBoundForm):
    """Used for a user to delete a his own account."""

    password = forms.TextField(
        lazy_gettext(u"Your password is required to delete your account:"),
        required=True, widget=forms.PasswordInput,
        messages = dict(required=lazy_gettext(u'Your password is required!'))
    )

    def __init__(self, user, initial=None):
        _UserBoundForm.__init__(self, user, forms.fill_dict(initial,
            action='delete'
        ))

    def validate_password(self, value):
        if not self.user.check_password(value):
            raise ValidationError(_(u'Invalid password'))

    def delete_user(self):
        """Deletes the user's account."""
        # find all the comments by this author and make them comments that
        # are no longer linked to the author.
        for comment in self.user.comments.all():
            comment.unbind_user()

        #! plugins can use this to react to user deletes.  They can't stop
        #! the deleting of the user but they can delete information in
        #! their own tables so that the database is consistent afterwards.
        #! Additional to the user object the form data is submitted.
        emit_event('before-user-deleted', self.user, self.data)
        db.delete(self.user)


class _ConfigForm(forms.Form):
    """Internal baseclass for forms that operate on config values."""

    def __init__(self, initial=None):
        self.app = get_application()
        if initial is None:
            initial = {}
            for name in self.fields:
                initial[name] = self.app.cfg[name]
        forms.Form.__init__(self, initial)

    def _apply(self, t, skip):
        for key, value in self.data.iteritems():
            if key not in skip:
                t[key] = value

    def apply(self):
        t = self.app.cfg.edit()
        self._apply(t, set())
        t.commit()


class LogOptionsForm(_ConfigForm):
    """A form for the logfiles."""
    log_file = config_field('log_file', lazy_gettext(u'Filename'))
    log_level = config_field('log_level', lazy_gettext(u'Log Level'))


class BasicOptionsForm(_ConfigForm):
    """The form where the basic options are changed."""
    blog_title = config_field('blog_title', lazy_gettext(u'Blog title'))
    blog_tagline = config_field('blog_tagline', lazy_gettext(u'Blog tagline'))
    blog_email = config_field('blog_email', lazy_gettext(u'Blog email'))
    language = config_field('language', lazy_gettext(u'Language'))
    timezone = config_field('timezone', lazy_gettext(u'Timezone'))
    session_cookie_name = config_field('session_cookie_name',
                                       lazy_gettext(u'Cookie Name'))
    comments_enabled = config_field('comments_enabled',
        label=lazy_gettext(u'Comments enabled'),
        help_text=lazy_gettext(u'enable comments per default'))
    moderate_comments = config_field('moderate_comments',
                                     lazy_gettext(u'Comment Moderation'),
                                     widget=forms.RadioButtonGroup)
    comments_open_for = config_field('comments_open_for',
        label=lazy_gettext(u'Comments Open Period'))
    pings_enabled = config_field('pings_enabled',
        lazy_gettext(u'Pingbacks enabled'),
        help_text=lazy_gettext(u'enable pingbacks per default'))
    use_flat_comments = config_field('use_flat_comments',
        lazy_gettext(u'Use flat comments'),
        help_text=lazy_gettext(u'All comments are posted top-level'))
    default_parser = config_field('default_parser',
                                  lazy_gettext(u'Default parser'))
    comment_parser = config_field('comment_parser',
                                  lazy_gettext(u'Comment parser'))
    posts_per_page = config_field('posts_per_page',
                                  lazy_gettext(u'Posts per page'))

    def __init__(self, initial=None):
        _ConfigForm.__init__(self, initial)
        self.language.choices = list_languages()
        self.default_parser.choices = self.comment_parser.choices = \
            self.app.list_parsers()


class URLOptionsForm(_ConfigForm):
    """The form for url changes.  This form sends database queries, even
    though seems to only operate on the config.  Make sure to commit.
    """

    blog_url_prefix = config_field('blog_url_prefix',
                                   lazy_gettext(u'Blog URL prefix'))
    admin_url_prefix = config_field('admin_url_prefix',
                                    lazy_gettext(u'Admin URL prefix'))
    category_url_prefix = config_field('category_url_prefix',
                                       lazy_gettext(u'Category URL prefix'))
    tags_url_prefix = config_field('tags_url_prefix',
                                   lazy_gettext(u'Tag URL prefix'))
    profiles_url_prefix = config_field('profiles_url_prefix',
        lazy_gettext(u'Author Profiles URL prefix'))
    post_url_format = config_field('post_url_format',
        lazy_gettext(u'Post permalink URL format'))
    ascii_slugs = config_field('ascii_slugs',
                               lazy_gettext(u'Limit slugs to ASCII'))
    fixed_url_date_digits = config_field('fixed_url_date_digits',
                                     lazy_gettext(u'Use zero-padded dates'))
    force_https = config_field('force_https', lazy_gettext(u'Force HTTPS'))

    def _apply(self, t, skip):
        for key, value in self.data.iteritems():
            if key not in skip:
                old = t[key]
                if old != value:
                    if key == 'blog_url_prefix':
                        change_url_prefix(old, value)
                    t[key] = value

        # update the blog_url based on the force_https flag.
        blog_url = (t['force_https'] and 'https' or 'http') + \
                   ':' + t['blog_url'].split(':', 1)[1]
        if blog_url != t['blog_url']:
            t['blog_url'] = blog_url


class ThemeOptionsForm(_ConfigForm):
    """
    The form for theme changes.  This is mainly just a dummy,
    to get csrf protection working.
    """


class CacheOptionsForm(_ConfigForm):
    cache_system = config_field('cache_system', lazy_gettext(u'Cache system'))
    cache_timeout = config_field('cache_timeout',
                                 lazy_gettext(u'Default cache timeout'))
    enable_eager_caching = config_field('enable_eager_caching',
                                        lazy_gettext(u'Enable eager caching'),
                                        help_text=lazy_gettext(u'Enable'))
    memcached_servers = config_field('memcached_servers')
    filesystem_cache_path = config_field('filesystem_cache_path')

    def context_validate(self, data):
        if data['cache_system'] == 'memcached':
            if not data['memcached_servers']:
                raise ValidationError(_(u'You have to provide at least one '
                                        u'server to use memcached.'))
        elif data['cache_system'] == 'filesystem':
            if not data['filesystem_cache_path']:
                raise ValidationError(_(u'You have to provide cache folder to '
                                        u'use filesystem cache.'))


class MaintenanceModeForm(forms.Form):
    """yet a dummy form, but could be extended later."""


class WordPressImportForm(forms.Form):
    """This form is used in the WordPress importer."""
    download_url = forms.TextField(lazy_gettext(u'Dump Download URL'),
                                   validators=[is_valid_url()])


class FeedImportForm(forms.Form):
    """This form is used in the feed importer."""
    download_url = forms.TextField(lazy_gettext(u'Feed Download URL'),
                                   validators=[is_valid_url()])


class DeleteImportForm(forms.Form):
    """This form is used to delete a imported file."""


class ExportForm(forms.Form):
    """This form is used to implement the export dialog."""


def delete_comment(comment):
    """
    Deletes or marks for deletion the specified comment, depending on the
    comment's position in the comment thread. Comments are not pruned from
    the database until all their children are.
    """
    if comment.children:
        # We don't have to check if the children are also marked deleted or not
        # because if they still exist, it means somewhere down the tree is a
        # comment that is not deleted.
        comment.status = COMMENT_DELETED
        comment.text = u''
        comment.user = None
        comment._author = comment._email = comment._www = None
    else:
        parent = comment.parent
        #! plugins can use this to react to comment deletes.  They can't
        #! stop the deleting of the comment but they can delete information
        #! in their own tables so that the database is consistent
        #! afterwards.
        emit_event('before-comment-deleted', comment)
        db.delete(comment)
        while parent is not None and parent.is_deleted:
            if not parent.children:
                newparent = parent.parent
                emit_event('before-comment-deleted', parent)
                db.delete(parent)
                parent = newparent
            else:
                parent = None
    # XXX: one could probably optimize this by tracking the amount
    # of deleted comments
    comment.post.sync_comment_count()


def make_config_form():
    """Returns the form for the configuration editor."""
    app = get_application()
    fields = {}
    values = {}
    use_default_label = lazy_gettext(u'Use default value')

    for category in app.cfg.get_detail_list():
        items = {}
        values[category['name']] = category_values = {}
        for item in category['items']:
            items[item['name']] = forms.Mapping(
                value=item['field'],
                use_default=forms.BooleanField(use_default_label)
            )
            category_values[item['name']] = {
                'value':        item['value'],
                'use_default':  False
            }
        fields[category['name']] = forms.Mapping(**items)

    class _ConfigForm(forms.Form):
        values = forms.Mapping(**fields)
        cfg = app.cfg

        def apply(self):
            t = self.cfg.edit()
            for category, items in self.data['values'].iteritems():
                for key, d in items.iteritems():
                    if category != 'zine':
                        key = '%s/%s' % (category, key)
                    if d['use_default']:
                        t.revert_to_default(key)
                    else:
                        t[key] = d['value']
            t.commit()

    return _ConfigForm({'values': values})


def make_notification_form(user):
    """Creates a notification form."""
    app = get_application()
    fields = {}
    subscriptions = {}

    systems = [(s.key, s.name) for s in
               sorted(app.notification_manager.systems.values(),
                      key=lambda x: x.name.lower())]

    for obj in app.notification_manager.types(user):
        fields[obj.name] = forms.MultiChoiceField(choices=systems,
                                                  label=obj.description,
                                                  widget=forms.CheckboxGroup)

    for ns in user.notification_subscriptions:
        subscriptions.setdefault(ns.notification_id, []) \
            .append(ns.notification_system)

    class _NotificationForm(forms.Form):
        subscriptions = forms.Mapping(**fields)
        system_choices = systems

        def apply(self):
            user_subscriptions = {}
            for subscription in user.notification_subscriptions:
                user_subscriptions.setdefault(subscription.notification_id,
                    set()).add(subscription.notification_system)

            for key, active in self['subscriptions'].iteritems():
                currently_set = user_subscriptions.get(key, set())
                active = set(active)

                # remove outdated
                for system in currently_set.difference(active):
                    for subscription in user.notification_subscriptions \
                        .filter_by(notification_id=key,
                                   notification_system=system):
                        db.session.delete(subscription)

                # add new
                for system in active.difference(currently_set):
                    user.notification_subscriptions.append(
                        NotificationSubscription(user=user, notification_id=key,
                                                 notification_system=system))

    return _NotificationForm({'subscriptions': subscriptions})


def make_import_form(blog):
    user_choices = [('__zine_create_user', _(u'Create new user'))] + [
        (user.id, user.username)
        for user in User.query.order_by('username').all()
    ]

    _authors = dict((author.id, forms.ChoiceField(author.username,
                                                  choices=user_choices))
                    for author in blog.authors)
    _posts = dict((post.id, forms.BooleanField(help_text=post.title)) for post
                  in blog.posts)
    _comments = dict((post.id, forms.BooleanField()) for post
                     in blog.posts)

    class _ImportForm(forms.Form):
        title = forms.BooleanField(lazy_gettext(u'Blog title'),
                                   help_text=blog.title)
        description = forms.BooleanField(lazy_gettext(u'Blog description'),
                                         help_text=blog.description)
        authors = forms.Mapping(_authors)
        posts = forms.Mapping(_posts)
        comments = forms.Mapping(_comments)
        load_config = forms.BooleanField(lazy_gettext(u'Load config values'),
                                         help_text=lazy_gettext(
                                         u'Load the configuration values '
                                         u'from the import.'))

        def perform_import(self):
            from zine.importers import perform_import
            return perform_import(get_application(), blog, self.data,
                                  stream=True)

    _all_true = dict((x.id, True) for x in blog.posts)
    return _ImportForm({'posts': _all_true.copy(),
                        'comments': _all_true.copy()})
