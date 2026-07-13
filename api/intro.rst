Introduction
============

Zine development requires Python 3.12, 3.13, or 3.14.  The supported source
checkout and command-line tools work on macOS, Linux, and other POSIX systems.

Checking out the Code
---------------------

Clone the Git repository from GitHub::

    $ git clone https://github.com/mitsuhiko/zine.git
    $ cd zine

Creating a Development Environment
----------------------------------

The project uses standard ``pyproject.toml`` packaging.  With uv, create and
synchronize a development environment with::

    $ uv sync --all-extras

Alternatively, use the standard library's virtual environment support and
install an editable checkout::

    $ python3 -m venv .venv
    $ .venv/bin/python -m pip install -e '.[test,docs]'

Run the regression suite before and after making changes::

    $ uv run --extra test pytest

The source-checkout commands under ``scripts/`` and the installed ``zine-*``
commands use the same application entry points.
