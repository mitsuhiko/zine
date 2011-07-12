# -*- coding: utf-8 -*-
"""
    zine.plugins.example_remote_auth
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Sample remote authentication instead of Zine's built-in authentication.
"""

from zine.application import Request as RequestBase
from zine.database import db
from zine.utils import forms
from zine.models import User, Group

class Request(RequestBase):
    def get_user(self):
        # This overrides Zine's default session-based authentication
        # with a custom method that looks for environ["REMOTE_USER"]
        # and creates the appropriate user in the database if it doesn't
        # exist yet.  If there is no user logged in, this method should
        # return None.  The caller will handle the AnonymousUser creation
        # in that case.
        app = self.app
        username = self.environ.get("REMOTE_USER", None)
        if not username:
            return None
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username, None, "%s@example.com" % username)
            db.session.add(user)
            db.commit()
        return user

    def __init__(self, environ, app=None):
        RequestBase.__init__(self, environ)
        request_groups = set()
        current_user = self.user

        # We can add Group associations to the current user
        # by assigning its `transient_groups` property to
        # a list of Group objects.  Here we'll add one Group
        # if the user is authenticated, and a different one
        # if the user is anonymous; and we'll also give the
        # HTTP request a chance to add an additional group.
        # Note that the groups must exist in the database;
        # we create them here if they don't exist.
        if current_user.is_somebody:
            request_groups.add("Authenticated")
        else:
            request_groups.add("Anonymous")
        group = environ.get("HTTP_X_REMOTE_GROUP", None)
        if group:
            request_groups.add(group)
        _request_groups = []
        for group_name in request_groups:
            group = Group.query.filter_by(name=group_name).first()
            if group is None:
                group = Group(group_name)
                db.session.add(group)
            _request_groups.append(group)
        db.commit()
            
        self.user.transient_groups = _request_groups

def setup(app, plugin):
    # The `_request_class` attribute of the app is used to
    # create the Request objects; so we need to reassign it
    # to our Request subclass in order for our custom 
    # authentication and authorization logic to be active.
    # Note that we just assume that no other plugin is also
    # trying to override the default Request!
    app._request_class = Request
