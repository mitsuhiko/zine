"""Signed cookie-backed sessions used by the Zine WSGI applications."""

from time import time

from itsdangerous import BadData, BadSignature, URLSafeSerializer


class SecureCookie(dict):
    """A small replacement for Werkzeug's removed ``SecureCookie``.

    The public methods mirror the subset of the old interface used by Zine.
    Session data is JSON-serialized and authenticated with itsdangerous.
    """

    salt = "zine-session"

    def __init__(self, data=None, secret_key=None):
        super().__init__(data or ())
        self.secret_key = secret_key
        self._modified = False

    @property
    def should_save(self):
        return self._modified

    def _mark_modified(self):
        self._modified = True

    def __setitem__(self, key, value):
        self._mark_modified()
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self._mark_modified()
        super().__delitem__(key)

    def clear(self):
        self._mark_modified()
        super().clear()

    def pop(self, key, *args):
        if key in self:
            self._mark_modified()
        return super().pop(key, *args)

    def popitem(self):
        self._mark_modified()
        return super().popitem()

    def setdefault(self, key, default=None):
        # Callers mutate lists returned by setdefault, so conservatively mark
        # the session even when the key already exists.
        self._mark_modified()
        return super().setdefault(key, default)

    def update(self, *args, **kwargs):
        if args or kwargs:
            self._mark_modified()
        super().update(*args, **kwargs)

    @classmethod
    def _serializer(cls, secret_key):
        return URLSafeSerializer(secret_key, salt=cls.salt)

    @classmethod
    def load_cookie(cls, request, key, secret_key):
        value = request.cookies.get(key)
        if not value:
            return cls(secret_key=secret_key)
        try:
            payload = cls._serializer(secret_key).loads(value)
            if not isinstance(payload, dict):
                raise BadSignature("invalid session payload")
            expires = payload.get("expires")
            if expires is not None and expires < time():
                return cls(secret_key=secret_key)
            data = payload.get("data", {})
            if not isinstance(data, dict):
                raise BadSignature("invalid session payload")
        except (BadData, TypeError, ValueError):
            data = {}
        return cls(data, secret_key)

    def save_cookie(
        self,
        response,
        key,
        max_age=None,
        expires=None,
        path="/",
        domain=None,
        secure=False,
        httponly=False,
        session_expires=None,
        samesite=None,
    ):
        payload = {"data": dict(self), "expires": session_expires}
        value = self._serializer(self.secret_key).dumps(payload)
        response.set_cookie(
            key,
            value,
            max_age=max_age,
            expires=expires,
            path=path,
            domain=domain,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
        )
        self._modified = False
