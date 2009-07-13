# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8 et
# ==============================================================================
# Copyright © 2009 UfSoft.org - Pedro Algarvio <ufs@ufsoft.org>
#
# License: BSD - Please view the LICENSE file for additional information.
# ==============================================================================

from zine.database import db, metadata

fortunes = db.Table('eric_the_fish_fortunes', metadata,
    db.Column('id', db.Integer, primary_key=True),
    db.Column('text', db.Text, nullable=False)
)

class Fortune(object):
    query = db.query_property(db.Query)
    def __init__(self, text):
        self.text = text

db.mapper(Fortune, fortunes)
