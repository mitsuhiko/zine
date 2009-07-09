"""
    zine.utils.mail
    ~~~~~~~~~~~~~~~

    This module implements some email-related functions and classes.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import os
import re
try:
    from email.mime.text import MIMEText
except ImportError:
    from email.MIMEText import MIMEText
from smtplib import SMTP, SMTPException
from urlparse import urlparse

from zine.utils import local
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

    def as_message(self):
        """Return the email as MIMEText object."""
        if not self.subject or not self.text or not self.to_addrs:
            raise RuntimeError("Not all mailing parameters filled in")

        from_addr = self.from_addr.encode('utf-8')
        to_addrs = [x.encode('utf-8') for x in self.to_addrs]


        msg = MIMEText(self.text.encode('utf-8'))

        #: MIMEText sucks, it does not override the values on
        #: setitem, it appends them.  We get rid of some that
        #: are predefined under some versions of python
        del msg['Content-Transfer-Encoding']
        del msg['Content-Type']

        msg['From'] = from_addr.encode('utf-8')
        msg['To'] = ', '.join(x.encode('utf-8') for x in self.to_addrs)
        msg['Subject'] = self.subject.encode('utf-8')
        msg['Content-Transfer-Encoding'] = '8bit'
        msg['Content-Type'] = 'text/plain; charset=utf-8'
        return msg

    def format(self, sep='\r\n'):
        """Format the message into a string."""
        return sep.join(self.as_message().as_string().splitlines())

    def log(self):
        """Logs the email"""
        f = open(os.path.join(self.app.instance_folder, 'mail.log'), 'a')
        try:
            f.write('%s\n%s\n\n' % ('-' * 79, self.format('\n').rstrip()))
        finally:
            f.close()

    def send(self):
        """Send the message."""
        try:
            smtp = SMTP(self.app.cfg['smtp_host'], self.app.cfg['smtp_port'])
        except SMTPException, e:
            raise RuntimeError(str(e))

        if self.app.cfg['smtp_use_tls']:
            #smtp.set_debuglevel(1)
            smtp.ehlo()
            if not smtp.esmtp_features.has_key('starttls'):
                # XXX: untranlated because python exceptions do not support
                # unicode messages.
                raise RuntimeError('TLS enabled but server does not '
                                   'support TLS')
            smtp.starttls()
            smtp.ehlo()

        if self.app.cfg['smtp_user']:
            try:
                smtp.login(self.app.cfg['smtp_user'],
                           self.app.cfg['smtp_password'])
            except SMTPException, e:
                raise RuntimeError(str(e))

        msgtext = self.format()
        try:
            try:
                return smtp.sendmail(self.from_addr, self.to_addrs, msgtext)
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


from zine.application import get_application
