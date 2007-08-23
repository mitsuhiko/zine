# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage.models
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Database models for the webpage.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from os import path, makedirs
from datetime import datetime
from urlparse import urljoin
from urllib import quote

from textpress.api import *
from textpress.utils import gen_pwhash, check_pwhash, gen_activation_key, \
     send_email, escape
from textpress.plugins.textpress_webpage.database import plugins, \
     plugin_versions, developers


class Plugin(object):

    def __init__(self, name, developer):
        if isinstance(developer, Developer):
            self.developer = developer
        else:
            self.developer_id = developer
        self.name = name

    @staticmethod
    def get_or_create(name, developer):
        plugin = Plugin.get_by(name=name)
        if plugin is None:
            plugin = Plugin(name, developer)
        elif plugin.developer != developer:
            return
        return plugin

    @property
    def latest(self):
        return self.versions[0]

    @property
    def old_versions(self):
        return self.versions[1:]

    def add_version(self, **kwargs):
        version = kwargs['version']
        if self.plugin_id is not None:
            old_version = PluginVersion.selectfirst(
                (PluginVersion.c.plugin_id == self.plugin_id) &
                (PluginVersion.c.version == version)
            )
            if old_version is not None:
                return
        version = PluginVersion(self, **kwargs)
        self.versions.append(version)
        return version

    def get_url_values(self):
        return 'textpress_webpage/show_plugin', {
            'name':     self.name
        }


class PluginVersion(object):

    def __init__(self, plugin, display_name, license, description, version,
                 author, author_email=None, author_url=None, plugin_url=None,
                 pub_date=None):
        if isinstance(plugin, (int, long)):
            self.plugin_id = plugin
        else:
            self.plugin = plugin
        self.display_name = display_name
        self.license = license
        self.description = description
        self.version = version
        self.author = author
        self.author_email = author_email
        self.author_url = author_url
        self._plugin_url = plugin_url
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date

    def write_package(self, data):
        try:
            makedirs(path.dirname(self.package_filename))
        except (OSError, IOError):
            pass
        f = file(self.package_filename, 'wb')
        try:
            f.write(data)
        finally:
            f.close()

    @property
    def package_filename(self):
        app = get_application()
        return path.join(app.instance_folder,
           app.cfg['textpress_webpage/plugin_folder'],
           self.plugin.name[0].lower(),
           self.plugin.name,
           '%s-%s.plugin' % (
               quote(self.display_name),
               quote(self.version)
        ))

    @property
    def download_url(self):
        app = get_application()
        return urljoin(
            app.cfg['textpress_webpage/plugin_url'],
            '/'.join([
                self.plugin.name[0].lower(),
                self.plugin.name,
                '%s-%s.plugin' % (
                    self.display_name,
                    self.version
                )
            ])
        )

    @property
    def plugin_url(self):
        online_url = url_for(self.plugin)
        if online_url.rstrip('/') != self._plugin_url.rstrip('/'):
            return self._plugin_url

    @property
    def html_author(self):
        if self.author_url:
            return u'<a href="%s">%s</a>' % (
                escape(self.author_url),
                escape(self.author)
            )
        return escape(self.author)


class Developer(object):

    def __init__(self, email, password):
        self.email = email
        self.set_password(password)
        self.activation_key = gen_activation_key()

    @property
    def active(self):
        return not self.activation_key

    def set_password(self, password):
        self.pw_hash = gen_pwhash(password)

    def check_password(self, password):
        return check_pwhash(self.pw_hash, password)

    def send_activation_mail(self):
        body = render_template('textpress_webpage/mails/activation.txt',
                               developer=self)
        send_email('Developer Account Activation', body, self.email)


db.mapper(PluginVersion, plugin_versions, {
    '_plugin_url':  plugin_versions.c.plugin_url
})
db.mapper(Plugin, plugins, {
    'versions': db.relation(PluginVersion, backref='plugin',
                            order_by=[db.desc(plugin_versions.c.pub_date)])
}, order_by=[db.asc(plugins.c.name)])
db.mapper(Developer, developers, {
    'plugins':  db.relation(Plugin, backref='developer',
                            order_by=[db.asc(plugins.c.name)])
})
