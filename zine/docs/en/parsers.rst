All About Parsers
=================

Zine supports multiple input formats you can choose from.  Out of the box
there are three so called parsers available:

-   `ZEML`, a HTML inspired extensible markup language
-   `HTML`, standard HTML for backwards compatibility with other blogging
    systems.
-   `Text`, a very simple parser that tries to render standard text into
    nicely looking HTML.  This is mainly intended for comments not for
    blog posts unless you're importing blog posts you've written for
    email.

There are other parsers shipped as part of Zine in plugins:

-   `reStructuredText`, is a lightweight markup format very popular in the
    Python community.
-   `Creole`, is a standardized wiki syntax used on some wiki engines on
    the web.

The plugins will need some additional libraries that have to be installed on
your server on order to use them.

You can choose the parser for comments and new blog posts in the comments or
override the parser for each post separately.  If you're not sure what markup
syntax to use have a look at the following comparison page.


ZEML
----

ZEML is the default parser and heavily inspired by good old HTML.  If you're
used to other blogging engines that are using HTML by default you should feel
right at home.

ZEML tries to follow older HTML versions in the sense that you don't have to
closed some of the tags in order to make things more simple.  You don't have
to worry to create invalid HTML because the ZEML parser will clean up after
you.

Example code::

    <intro><p>This is the intro text of the blog.  If you theme supports
    separate intro blocks this one will appear on the index page and will
    have a “follow me” link to read the full post.</intro>
    <p>This is the rest of the text in a paragraph.  Note that you don't
    have to close the paragraphs.
    <p>This is another paragraph.  Paragraphs are usually separated by
    a wider gap in the theme.
    <ul>
      <li>This is an unordered list.
      <li>Of multiple items.
    </ul>
    <p>ZEML also supports shorter end tags that omit the name.  For example
    if you want some <strong>strong text</> you can close it like I did
    here.
    <blockquote><p>This is a bockquote which is usually indented in some
    way or another.  This also depends on the theme.</blockquote>
    <p>And here finally an example for a plugin that extends ZEML for
    syntax highlighting:
    <sourcecode syntax=python>
    print "Hello World"
    </sourcecode>

reStructuredText
----------------

reStructuredText is a parser implemented in a separate plugin which requires
the `docutils <http://docutils.sourceforge.net/>`_ library.  Once you've
installed that library and enabled the reStructuredText parser plugin you
can use.  reStructuredText heavily depends on indentation in the text so you
probably want to use a text editor for blog post editing until the builtin
editor supports you on automatic indenting.

Example code::

    .. intro::

       This is the intro text of the blog.  If your theme supports
       separate intro blocks this one will appear on the index page
       and will have a “follow me” link to read the full post.

    This is the rest of the text in a paragraph.  Note that you don't
    have to close the paragraphs.

    This is another paragraph.  Paragraphs are usually separated by
    a wider gap in the theme.
    
    -   This is an unordered list.
    -   Of multiple items.

    ZEML also supports shorter end tags that omit the name.  For example
    if you want some **strong text** you can close it like I did
    here.

        This is a bockquote which is usually indented in some
        way or another.  This also depends on the theme.

    And here finally an example for a plugin that extends ZEML for
    syntax highlighting:

    .. sourcecode:: python

        print "Hello World"

For more information consult the `quick reference`_.

.. _quick reference: http://docutils.sourceforge.net/docs/user/rst/quickref.html

Creole
------

Example code::

    <<intro>>This is the intro text of the blog.  If your theme supports
    separate intro blocks this one will appear on the index page
    and will have a “follow me” link to read the full post.<</intro>>

    This is the rest of the text in a paragraph.  Note that you don't
    have to close the paragraphs.

    This is another paragraph.  Paragraphs are usually separated by
    a wider gap in the theme.
    
    * This is an unordered list.
    * Of multiple items.

    ZEML also supports shorter end tags that omit the name.  For example
    if you want some **strong text** you can close it like I did
    here.

    And here finally an example for a plugin that extends ZEML for
    syntax highlighting:

    <<sourcecode syntax=python>>
    print "Hello World"
    <</sourcecode>>

For more information have a look at the `cheatsheet`_.

.. _cheatsheet: http://purl.oclc.org/creoleparser/cheatsheet
