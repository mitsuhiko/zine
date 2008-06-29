# -*- coding: utf-8 -*-
"""
Compile translations from JavaScript files into one catalog.
"""
from __future__ import with_statement
from os import listdir, path
from babel.messages.pofile import read_po
from simplejson import dump

domains = ['messages']


root = path.abspath(path.dirname(__file__))
for domain in domains:
    for lang in listdir(root):
        folder = path.join(root, lang, 'LC_MESSAGES')
        translations = path.join(folder, domain + '.po')
        if path.isfile(translations):
            print 'Compiling JavaScript translations for %r' % lang
            jscatalog = {}
            with file(translations) as f:
                catalog = read_po(f, locale=lang, domain=domain)
                pluralexpr = catalog.plural_expr
                for message in catalog:
                    if any(x[0].endswith('.js') for x in message.locations):
                        msgid = message.id
                        if isinstance(msgid, (list, tuple)):
                            msgid = msgid[0]
                        jscatalog[msgid] = message.string
            with file(path.join(folder, domain + '.js'), 'w') as f:
                f.write('babel.Translations.load(');
                dump(dict(
                    messages=jscatalog,
                    plural_expr=catalog.plural_expr,
                    locale=str(catalog.locale),
                    domain=catalog.domain
                ), f)
                f.write(').install();')
