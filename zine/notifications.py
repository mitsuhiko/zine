# -*- coding: utf-8 -*-
"""
    zine.notifications
    ~~~~~~~~~~~~~~~~~~

    This module implements an extensible notification system.  Plugins can
    provide different kinds of notification systems (like email, jabber etc.)

    Each user can subscribe to different kinds of events.  The general design
    is inspired by Growl.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from datetime import datetime
from urlparse import urlsplit

from werkzeug import url_unquote

from zine.models import NotificationSubscription
from zine.application import get_application, get_request, render_template
from zine.privileges import BLOG_ADMIN, ENTER_ACCOUNT_PANEL, MODERATE_COMMENTS,\
     MODERATE_OWN_PAGES, MODERATE_OWN_ENTRIES
from zine.utils.zeml import parse_zeml
from zine.utils.mail import send_email
from zine.i18n import lazy_gettext


__all__ = ['DEFAULT_NOTIFICATION_TYPES', 'NotificationType']

DEFAULT_NOTIFICATION_TYPES = {}


def send_notification(type, message, user=Ellipsis):
    """Convenience function.  Get the application object and deliver the
    notification to it's NotificationManager.

    The message must be a valid ZEML formatted message.  The following
    top-level elements are available for marking up the message:

    title
        The title of the notification.  Some systems may only transmit this
        part of the message.

    summary
        An optional quick summary.  If the text is short enough it can be
        omitted and the system will try to transmit the longtext in that
        case.  The upper limit for the summary should be around 100 chars.

    details
        If given this may either contain a paragraph with textual information
        or an ordered or unordered list of text or links.  The general markup
        rules apply.

    longtext
        The full text of this notification.  May contain some formattings.

    actions
        If given this may contain an unordered list of action links.  These
        links may be transmitted together with the notification.

    Additionally if there is an associated page with the notification,
    somewhere should be a link element with a "selflink" class.  This can be
    embedded in the longtext or actions (but any other element too).

    Example markup::

        <title>New comment on "Foo bar baz"</title>
        <summary>Mr. Miracle wrote a new comment: "This is awesome."</summary>
        <details>
          <ul>
            <li><a href="http://miracle.invalid/">Mr. Miracle</a>
            <li><a href="mailto:mr@miracle.invalid">E-Mail</a>
          </ul>
        </details>
        <longtext>
          <p>This is awesome.  Keep it up!
          <p>Love your work
        </longtext>
        <actions>
          <ul>
            <li><a href="http://.../link" class="selflink">all comments</a>
            <li><a href="http://.../?action=delete">delete it</a>
            <li><a href="http://.../?action=approve">approve it</a>
          </ul>
        </actions>

    Example plaintext rendering (e-mail)::

        Subject: New comment on "Foo bar baz"

        Mr. Miracle             http://miracle.invalid/
        E-Mail                  mr@mircale.invalid

        > This is awesome.   Keep it up!
        > Love your work.

        Actions:
          - delete it           http://.../?action=delete
          - approve it          http://.../?action=approve

    Example IM notification rendering (jabber)::

        New comment on "Foo bar baz."  Mr. Miracle wrote anew comment:
        "This is awesome".  http://.../link
    """
    get_application().notification_manager.send(
        Notification(type, message, user)
    )


def send_notification_template(type, template_name, user=Ellipsis, **context):
    """Like `send_notification` but renders a template instead."""
    notification = render_template(template_name, **context)
    send_notification(type, notification, user)


class NotificationType(object):
    """There are different kinds of notifications. E.g. you want to
    send a special type of notification after a comment is saved.
    """

    def __init__(self, name, description, privileges):
        self.name = name
        self.description = description
        self.privileges = privileges

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.name)


class Notification(object):
    """A notification that can be sent to a user. It contains a message.
    The message is a zeml construct.
    """

    def __init__(self, id, message, user=Ellipsis):
        self.message = parse_zeml(message, 'system')
        self.id = id
        self.sent_date = datetime.utcnow()
        if user is Ellipsis:
            self.user = get_request().user
        else:
            self.user = user

    @property
    def self_link(self):
        link = self.message.query('a[class~=selflink]').first
        if link is not None:
            return link.attributes.get('href')

    title = property(lambda x: x.message.query('/title').first)
    details = property(lambda x: x.message.query('/details').first)
    actions = property(lambda x: x.message.query('/actions').first)
    summary = property(lambda x: x.message.query('/summary').first)
    longtext = property(lambda x: x.message.query('/longtext').first)


class NotificationSystem(object):
    """Use this as a base class for specific notification systems such as
    `JabberNotificationSystem` or `EmailNotificationSystem`.

    The class must implement a method `send` that receives a notification
    object and a user object as parameter and then sends the message via
    the specific system.  The plugin is itself responsible for extracting the
    information necessary to send the message from the user object.  (Like
    extracting the email address).
    """

    def __init__(self, app):
        self.app = app

    #: subclasses have to overrides this as class attributes.
    name = None
    key = None

    def send(self, user, notification):
        raise NotImplementedError()


class EMailNotificationSystem(NotificationSystem):
    """Sends notifications to user via E-Mail."""

    key = 'email'
    name = lazy_gettext(u'E-Mail')

    def send(self, user, notification):
        title = u'[%s] %s' % (
            self.app.cfg['blog_title'],
            notification.title.to_text()
        )
        text = self.mail_from_notification(notification)
        send_email(title, text, [user.email])

    def unquote_link(self, link):
        """Unquotes some kinds of links.  For example mailto:foo links are
        stripped and properly unquoted because the mails we write are in
        plain text and nobody is interested in URLs there.
        """
        scheme, netloc, path = urlsplit(link)[:3]
        if scheme == 'mailto':
            return url_unquote(path)
        return link

    def collect_list_details(self, container):
        """Returns the information collected from a single detail list item."""
        for item in container.children:
            if len(item.children) == 1 and item.children[0].name == 'a':
                link = item.children[0]
                href = link.attributes.get('href')
                yield dict(text=link.to_text(simple=True),
                           link=self.unquote_link(href), is_textual=False)
            else:
                yield dict(text=item.to_text(multiline=False),
                           link=None, is_textual=True)


    def find_details(self, container):
        # no container given, nothing can be found
        if container is None or not container.children:
            return []

        result = []
        for child in container.children:
            if child.name in ('ul', 'ol'):
                result.extend(self.collect_list_details(child))
            elif child.name == 'p':
                result.extend(dict(text=child.to_text(),
                                   link=None, is_textual=True))
        return result

    def find_actions(self, container):
        if not container:
            return []
        ul = container.query('/ul').first
        if not ul:
            return []
        return list(self.collect_list_details(ul))

    def mail_from_notification(self, message):
        title = message.title.to_text()
        details = self.find_details(message.details)
        longtext = message.longtext.to_text(collect_urls=True,
                                            initial_indent=2)
        actions = self.find_actions(message.actions)
        return render_template('notifications/email.txt', title=title,
                               details=details, longtext=longtext,
                               actions=actions)


class NotificationManager(object):
    """The NotificationManager is informed about new notifications by the
    send_notification function. It then decides to which notification
    plugins the notification is handed over by looking up a database table
    in the form:

        user_id  | notification_system | notification id
        ---------+---------------------+--------------------------
        1        | jabber              | NEW_COMMENT
        1        | email               | ZINE_UPGRADE_AVAILABLE
        1        | sms                 | SERVER_EXPLODED

    The NotificationManager also assures that only users interested in
    a particular type of notifications receive a message.
    """

    def __init__(self):
        self.systems = {}
        self.notification_types = DEFAULT_NOTIFICATION_TYPES.copy()

    def send(self, notification):
        # given the type of the notification, check what users want that
        # notification; via what system and call the according
        # notification system in order to finally deliver the message
        subscriptions = NotificationSubscription.query.filter_by(
            notification_id=notification.id.name
        )
        if notification.user:
            subscriptions = subscriptions.filter(
                NotificationSubscription.user!=notification.user
            )

        for subscription in subscriptions.all():
            system = self.systems.get(subscription.notification_system)
            if system is not None:
                system.send(subscription.user, notification)

    def types(self, user=None):
        if not user:
            user = get_request().user
        for notification in self.notification_types.itervalues():
            if user.has_privilege(notification.privileges):
                yield notification

    def add_notification_type(self, notification):
        self.notification_types[type.name] = type


def _register(name, description, privileges=ENTER_ACCOUNT_PANEL):
    """Register a new builtin type of notifications."""
    nottype = NotificationType(name, description, privileges)
    DEFAULT_NOTIFICATION_TYPES[name] = nottype
    globals()[name] = nottype
    __all__.append(name)


_register('NEW_COMMENT',
          lazy_gettext(u'When a new comment is received.'))
_register('COMMENT_REQUIRES_MODERATION',
          lazy_gettext(u'When a comment requires moderation.'),
          (MODERATE_OWN_PAGES | MODERATE_OWN_ENTRIES | MODERATE_COMMENTS))
_register('SECURITY_ALERT',
          lazy_gettext(u'When Zine found an urgent security alarm.'),
          BLOG_ADMIN)
_register('ZINE_ERROR', lazy_gettext(u'When Zine throws errors.'), BLOG_ADMIN)


DEFAULT_NOTIFICATION_SYSTEMS = [EMailNotificationSystem]
del _register
