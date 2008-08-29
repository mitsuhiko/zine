:mod:`zine.api`
====================

.. module:: zine.api

This module contains all the classes and functions from the core system that
can be used by Zine plugins.


Event Handling
--------------

-   :func:`~zine.application.emit_event`
-   :func:`~zine.application.iter_listeners`

Request/Response
----------------
-   :func:`~zine.application.Response`
-   :func:`~zine.application.redirect`
-   :func:`~zine.application.get_request`
-   :func:`~zine.application.url_for`
-   :func:`~zine.application.add_link`
-   :func:`~zine.application.add_meta`
-   :func:`~zine.application.add_script`
-   :func:`~zine.application.add_header_snippet`

View Helpers
------------
-   :func:`~zine.application.require_role`

Templating
----------

-   :func:`~zine.application.render_template`
-   :func:`~zine.application.render_response`

Application
-----------

-   :func:`~zine.application.get_application`

Database
--------

-   :mod:`~zine.database.db`

Cache
-----

-   :mod:`~zine.cache`
