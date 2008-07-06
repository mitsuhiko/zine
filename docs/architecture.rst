TextPress Architecture
======================

TextPress has a modular design that allows plugins to extend nearly every
part of the system.  There are some design decisions that are important to
know because they have a huge impact on the application code and explain
some behavior.


Code is not Data
    TextPress keeps code and data apart from each other.  This means that
    the code is installed once on the system and you can run multiple
    separate TextPress installations and upgrade them in one go.  Every
    TextPress installation has an so called "instance" folder where the
    configuration, additional plugins and binary data goes.

    As a matter of fact all code has to assume that the instance folder
    is where the application configured it, and not necessarily called
    ``instance`` and live next to the textpress folder like it is 
    usually during development.

One application per thread
    There can be exactly one TextPress application per thread.  This is
    important because TextPress itself accesses the active request and
    application object by thread-local variables in various situations.

Designed for persistent enviroments
    TextPress is designed for webserver interfaces that keep the process
    alive for multiple request.  This is the case for nearly everything
    except of CGI.  As a consequence of that, the application is devided
    into multiple stages where code behaves slightly different.


Stages
------

TextPress is divided into multiple stages:

Setup Stage
    This stage initializes a TextPress instance and all the plugins.  Only
    in this stage plugins can safely connect to events and register callbacks.
    During the setup stage the instance that is set up has an exclusive setup
    lock.  It can safely assume that the application is bound to the active
    thread.

Request Stage
    When a request comes in and the TextPress instance is properly configured
    the regular dispatch handling kicks in.  The application and the current
    request are bound to the active thread, so until the end of the request
    all code will be able to get a reference to the request and application
    objects by using the :func:`~textpress.application.get_request` and
    :func:`~textpress.application.get_application` functions.

Request-unbound Stage
    When working with the TextPress API from a script or the command line, the
    code won't be able to access the current request because there is none.
    The :func:`~textpress.application.get_request` function will return
    `None`, however the application is bound to the thread.  As a matter of
    fact scripts will have a hard time working with two applications at once.


Application Setup
-----------------

There are two ways to create a TextPress application.  Scripts and the
interactive shell usually create TextPress by using the
:func:`~textpress.application.make_textpress` function whereas the application
for the actual web application is created by the
:func:`~textpress.application.make_app` function.  The behavior of those
two functions is explained in detail in the API documentation, however the
concept of the application setup stage is outlined here.

The :func:`~textpress.application.make_app` function does not return a
TextPress application object but a dispatcher WSGI application.  This
dispatcher checks every request if the TextPress instance is initialized or
if the configuration was changed and if the application should be reloaded.
If the instance is not yet initialized the dispatcher will hook in an
interactive web setup application.


.. _contexts:

Contexts
--------

The most important aspect of TextPress is the context system.  You will notice
when working with the API that TextPress automatically knows the active request
and application.  This works because TextPress only supports one request and
one active application per thread.

When a request comes in TextPress binds the request and the application to the
current thread and all the code until the end of the request can automatically
access the active request and application.

The :func:`~textpress.application.get_request` function returns the active
request object if possible or `None` if the function was called from outside
a request context (for example a shell script).
:func:`~textpress.application.get_application` on the other hand returns the
application that is bound to the active thread and should always succeed unless
you forgot to bind the application.

The application is bound on application creation automatically but can be
explicitly set by calling :meth:`~textpress.application.TextPress.bind_to_thread`.
