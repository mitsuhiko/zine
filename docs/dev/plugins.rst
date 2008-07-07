Writing Plugins
===============

TextPress makes developing plugins easy and straightforward.  TextPress takes
advantage of Python's modular nature.  Each plugin is simple Python package
that exports a single `setup()` function that is called on plugin
initialization.

In addition to that, every plugin has to have a `metadata.txt` file with
general information about the plugin such as the human readable name, the
author, download URL, version and description.


“Hello TextPress!”
------------------

Let's get started with a very simple plugin that just say's “Hello World”
when the visitor visits a specific URL.

There are two locations where TextPress looks for plugins: the `plugins`
folder in the `textpress` package as well as the `plugins` folder in the
instance folder.  If the latter does not exist by now, you can create it
yourself.

For plugin development however it's encouraged to create a separate folder
with version control outside of the `textpress` package and the instance
folder and create the plugin there.  While it's perfectly okay to create
a plugin in the instance folder you may want to recreate the instance during
development for testing purposes and accidentally delete the plugin that
is still in development.  Additionally you may want to put the plugin
into version control and add a README file next to it.

For our example plugin we create our plugin in separate folder and add it
to the plugin load path.  Additionally we'll use mercurial for version
control.

So let's create a folder first and initialize hg::

    $ mkdir HelloWorldPlugin
    $ cd !$
    $ hg init

Now we have to create the Python package for our plugin.  Remember, a Python
**package** is a folder with an `__init__.py` file.  Just a Python module
won't do the trick::

    $ mkdir hello_world

Put the following contents into the `__init__.py` file::

    def setup(app, plugin):
        pass

That's the absolute minimum required for a TextPress plugin that does
nothing.  Now the only thing we have to add is a `metadata.txt` file
with the meta data::

    Name: Hello World
    Author: Your Name <your-email@example.com>
    Author URL: http://yourname.example.com/
    License: GNU GPL
    Version: 0.1
    Description: A simple Hello-World plugin

That's it, we can now load the plugin.  But first we have to tell TextPress
that it has to look for plugins in our new `HelloWorldPlugin` folder.  Open
the `textpress.ini` file and add the following line into the `textpress`
section::

    plugin_searchpath = /home/yourusername/dev/HelloWorldPlugin

(Or where the `HelloWorldPlugin` folder is).

If there is already an entry for `plugin_searchpath` add the path into the
already existing line, separated by a comma (``,``).  You can now go to the
admin panel and enable the plugin.  It should now appear in the list.  If it
does not, make sure the load path is correct and the name of the metadata
file is correct.

After loading `TextPress` will give you an success message and nothing else
happens.  You have successfully created your first empty plugin.

Now let's add some logic.


Doing Stuff™
------------

All the magic happens in the `setup` function.  This function is called
when the `TextPress` application is started up.  This is the chance for your
plugin to connect to events and inform TextPress about additional
functionality.

For our very simple example we will add a handler that listens on a URL
and returns "Hello World".

First of all we have to write the function that prints the message.  For that
we need the `Response` object from the :mod:`~textpress.api` module.  We can
savely import everything from there, it's designed for that::

    from textpress.api import *

Now we can create the function that writes the message.  It's called with the
incoming request as first argument::

    def say_hello(request):
        return Response('Hello World!', mimetype='text/plain')

And now we can register the function::

    def setup(app, plugin):
        app.add_url_rule('/hello', endpoint='hello_world/hello',
                         view=say_hello)

You can now go to ``http://localhost:4000/hello`` and TextPress should happily
great you.


How things work
---------------

Especially for more important plugins it's important to know how things
actually work.  The `hello_world` package you've created isn't actually
importable as `hello_world`.  Instead it's called
`textpress.plugins.hello_world` with the full name.  This is important if you
have multiple submodules and want to import them.  Don't ever use relative
imports there, always specify the full target.

For example if you have a complex plugin that implements an importing
machanism that requires a second module called `feedparser` you can import
stuff from that module into your `__init__` module with this code::

    from textpress.plugins.your_plugin.feedparser import FeedParser

Every instance of TextPress (even multiple TextPress instances in the same
Python interpreter) are importing the plugins separately.  That allows plugins
to savely use the global namespace to store application bound information.


Warnings for the Professionals
------------------------------

TextPress separates multiple instances in the interpreter as good as it cans.
That you can still interact with different instances is the nature of Python.
But just because you can you shouldn't do that.  Actually you are not allowed
to do that because TextPress supports reloading of plugins at runtime which
requires that a plugin can shut down without leaving traces behind.  A plugin
must never do monkey patching because that cannot be undone savely again.

There is no callback that is called on plugin unloading, what TextPress does
is dropping all references it has to the plugins and waits for Python to
deallocate the memory.  As plugin developer you have no chance to execute
code before unloading.
