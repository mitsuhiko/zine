Installation Instructions
=========================

TextPress is not released yet and the following instructions are only valid
for the development version.  Read this carefully before starting working
with TextPress.

TextPress uses `mercurial`_ as source control system.  After installing
mercurial you can check out the development sources with the following
command::

    hg clone http://dev.pocoo.org/hg/textpress-main textpress

After that you have a folder called ``textpress`` with your own checkout of
the sourcecode.  You can check in changes normally and either push if you are
a core developer or create bundles or patches if you want to contribute
patches.

In order for TextPress to work properly you need quite a few extension
libraries.  Make sure you install the following libraries:

-   Python 2.4 or higher
-   Jinja2
-   Werkzeug
-   SQLAlchemy 0.4.x
-   pytz
-   Babel
-   simplejson

And at least one database driver.  For development sqlite is recommended.
You can install all libraries using ``easy_install``.

.. _mercurial: http://selenic.com/mercurial/


Updating the Source Code
------------------------

To update the code you can use the ``hg pull -u`` command mercurial provides.
If you are creating changes locally make sure to ``hg ci`` first.  If you have
local changes and an upstream developer made a change that requires merging
use ``hg merge && hg ci``.

For more information about that process consult the mercurial wiki.


Creating a Development Instance
-------------------------------

TextPress contains a script that is used during development for some
tasks such as running the development server and getting a shell.  This
script assumes that your instance folder is called `instance` inside the
checkout folder.  To finish setting up the development environment open
a shell and go to the folder you just checked out and create a folder
called `instance`::

    mkdir instance

After that you can run the development server and follow the websetup::

    python textpress-management.py runserver
