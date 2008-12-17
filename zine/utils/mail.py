"""
    zine.utils.mail
    ~~~~~~~~~~~~~~~

    This module implements some email-related functions and classes.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: BSD
"""
import re
from email.MIMEText import MIMEText
from smtplib import SMTP, SMTPException
from urlparse import urlparse

from zine.utils import local
from zine.i18n import _
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
    """Send a mail using the `EMail` class."""
    e = EMail(subject, text, to_addrs)
    if quiet:
        return e.send_quiet()
    return e.send()


class EMail(object):
    """Represents one E-Mail message that can be sent."""

    def __init__(self, subject=None, text='', to_addrs=None):
        self.app = app = local.application
        self.subject = u' '.join(subject.splitlines())
        self.text = text
        from_addr = app.cfg['blog_email']
        if not from_addr:
            from_addr = 'noreply@' + urlparse(app.cfg['blog_url'])\
                    [1].split(':')[0]
        self.from_addr = u'%s <%s>' % (
            app.cfg['blog_title'],
            from_addr
        )
        self.to_addrs = []
        if isinstance(to_addrs, basestring):
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

    def send(self):
        """Send the message."""
        if not self.subject or not self.text or not self.to_addrs:
            raise RuntimeError("Not all mailing parameters filled in")
        try:
            smtp = SMTP(self.app.cfg['smtp_host'], self.app.cfg['smtp_port'])
        except SMTPException, e:
            raise RuntimeError(str(e))

        if self.app.cfg['smtp_use_tls']:
            #smtp.set_debuglevel(1)
            smtp.ehlo()
            if not smtp.esmtp_features.has_key('starttls'):
                raise RuntimeError(_("TLS enabled but server does not support "
                                     "TLS"))
            smtp.starttls()
            smtp.ehlo()

        if self.app.cfg['smtp_user']:
            try:
                smtp.login(self.app.cfg['smtp_user'],
                           self.app.cfg['smtp_password'])
            except SMTPException, e:
                raise RuntimeError(str(e))

        msg = MIMEText(self.text)
        msg['From'] = self.from_addr
        msg['To'] = ', '.join(self.to_addrs)
        msg['Subject'] = self.subject

        msgtext = msg.as_string()
        recrlf = re.compile("\r?\n")
        msgtext = '\r\n'.join(recrlf.split(msgtext.encode('utf-8')))

        try:
            try:
                return smtp.sendmail(self.from_addr, self.to_addrs,
                                     msgtext)
            except SMTPException, e:
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
