:mod:`textpress.application`
============================

.. automodule:: textpress.application


Factories
---------

The factory functions provide different ways to create the central
:class:`TextPress` object.  Depending on the execution context (shell script,
web application) :func:`make_app` or :func:`make_textpress` is more suitable.

.. autofunction:: make_app

.. autofunction:: make_textpress


.. _dispatchers:

Dispatchers
-----------

These dispatchers are returned by :func:`make_app`.  The existance of these
dispatchers is not guaranteed, always use the factory function to create them.

.. autoclass:: StaticDispatcher

.. autoclass:: DynamicDispatcher


Core Objects
------------

.. autoclass:: TextPress
   :members:

.. autoclass:: Theme
   :members:

.. autoexception:: InstanceNotInitialized

Request and Response
--------------------

The request and response classes are subclasses of the Werkzeug classes with
the same names.  For more details have a look at the Werkzeug documentation.

.. autoclass:: Request
   :members:
   :inherited-members:

.. autoclass:: Response
   :members:
   :inherited-members:


Context Helpers
---------------

These functions interact with the :ref:`context system <contexts`.

.. autofunction:: get_request

.. autofunction:: get_application

URLs
----

.. autofunction:: url_for

.. autofunction:: redirect

Events
------

.. autofunction:: emit_event

.. autofunction:: iter_listeners

.. autofunction:: add_link

.. autofunction:: add_meta

.. autofunction:: add_script

.. autofunction:: add_header_snippet

Templating
----------

.. autofunction:: render_template

.. autofunction:: render_response

Decorators
----------

.. autofunction:: require_role
