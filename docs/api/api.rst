:mod:`textpress.api`
====================

.. module:: textpress.api

This module contains all the classes and functions from the core system that
can be used by TextPress plugins.


Event Handling
--------------

-   :func:`~textpress.application.emit_event`
-   :func:`~textpress.application.iter_listeners`

Request/Response
----------------
-   :func:`~textpress.application.Response`
-   :func:`~textpress.application.redirect`
-   :func:`~textpress.application.get_request`
-   :func:`~textpress.application.url_for`
-   :func:`~textpress.application.add_link`
-   :func:`~textpress.application.add_meta`
-   :func:`~textpress.application.add_script`
-   :func:`~textpress.application.add_header_snippet`

View Helpers
------------
-   :func:`~textpress.application.require_role`

Templating
----------

-   :func:`~textpress.application.render_template`
-   :func:`~textpress.application.render_response`

Application
-----------

-   :func:`~textpress.application.get_application`

Database
--------

-   :data:`~textpress.database.db`

Cache
-----

-   :mod:`~textpress.cache`
