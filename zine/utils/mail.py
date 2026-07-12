"""
    zine.utils.mail
    ~~~~~~~~~~~~~~~

    This module implements some email-related functions and classes.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import os
import re
from email.mime.text import MIMEText
from smtplib import SMTP, SMTPException
from urllib.parse import urlparse

from zine.utils.validators import is_valid_email, check


_mail_split_re = re.compile(r'^(.*?)(?:\s+<(.+)>)?$')


def split_email(s):
    """Split a mail address:

    >>> split_email("John Doe")
    ('John Doe', None)
    >>> split_email("John Doe <john@doe.com>")
    ('John Doe', 'john@doe.com')
    >>> split_email("john@doe.com")
    (None, 'john@doe.com')
    """
    p1, p2 = _mail_split_re.search(s).groups()
    if p2:
        return p1, p2
    elif check(is_valid_email, p1):
        return None, p1
    return p1, None


def send_email(subject, text, to_addrs, quiet=True):
    """Send a mail using the `EMail` class.  This will log the email instead
    if the application configuration wants to log email.
    """
    e = EMail(subject, text, to_addrs)
    if e.app.cfg['log_email_only']:
        return e.log()
    if quiet:
        return e.send_quiet()
    return e.send()


class EMail(object):
    """Represents one E-Mail message that can be sent."""

    def __init__(self, subject=None, text='', to_addrs=None):
        self.app = app = get_application()
        self.subject = u' '.join(subject.splitlines())
        self.text = text
        from_addr = app.cfg['blog_email']
        if not from_addr:
            from_addr = 'noreply@' + urlparse(app.cfg['blog_url']) \
                    [1].split(':')[0]
        self.from_addr = u'%s <%s>' % (
            app.cfg['blog_title'],
            from_addr
        )
        self.to_addrs = []
        if isinstance(to_addrs, str):
            self.add_addr(to_addrs)
        else:
            for addr in to_addrs:
                self.add_addr(addr)

    def add_addr(self, addr):
        """Add an mail address to the list of recipients"""
        lines = addr.splitlines()
        if len(lines) != 1:
            raise ValueError('invalid value for email address')
        self.to_addrs.append(lines[0])

    def as_message(self):
        """Return the email as MIMEText object."""
        if not self.subject or not self.text or not self.to_addrs:
            raise RuntimeError("Not all mailing parameters filled in")

        msg = MIMEText(str(self.text), 'plain', 'utf-8')
        msg['From'] = self.from_addr
        msg['To'] = ', '.join(self.to_addrs)
        msg['Subject'] = self.subject
        return msg

    def format(self, sep='\r\n'):
        """Format the message into a string."""
        return sep.join(self.as_message().as_string().splitlines())

    def log(self):
        """Logs the email"""
        f = open(
            os.path.join(self.app.instance_folder, 'mail.log'),
            'a',
            encoding='utf-8',
        )
        try:
            f.write('%s\n%s\n\n' % ('-' * 79, self.format('\n').rstrip()))
        finally:
            f.close()

    def send(self):
        """Send the message."""
        try:
            smtp = SMTP(self.app.cfg['smtp_host'], self.app.cfg['smtp_port'])
        except SMTPException as e:
            raise RuntimeError(str(e))

        if self.app.cfg['smtp_use_tls']:
            #smtp.set_debuglevel(1)
            smtp.ehlo()
            if 'starttls' not in smtp.esmtp_features:
                # XXX: untranslated because python exceptions do not support
                # unicode messages.
                raise RuntimeError('TLS enabled but server does not '
                                   'support TLS')
            smtp.starttls()
            smtp.ehlo()

        if self.app.cfg['smtp_user']:
            try:
                smtp.login(self.app.cfg['smtp_user'],
                           self.app.cfg['smtp_password'])
            except SMTPException as e:
                raise RuntimeError(str(e))

        msgtext = self.format()
        try:
            try:
                return smtp.sendmail(self.from_addr, self.to_addrs, msgtext)
            except SMTPException as e:
                raise RuntimeError(str(e))
        finally:
            if self.app.cfg['smtp_use_tls']:
                # avoid false failure detection when the server closes
                # the SMTP connection with TLS enabled
                import socket
                try:
                    smtp.quit()
                except socket.sslerror:
                    pass
            else:
                smtp.quit()

    def send_quiet(self):
        """Send the message, swallowing exceptions."""
        try:
            return self.send()
        except Exception:
            return


from zine.application import get_application
