# Zine

Zine is a Python-powered blog engine originally developed by Armin Ronacher
and the Zine Team. This repository is a **revival of the historical Zine 0.2
codebase**, updated so that it can run on modern Python and current versions of
its dependencies.

The modernization was carried out with the assistance of a coding agent. It
was intentionally focused on porting and compatibility rather than redesigning
Zine or adding a new product roadmap.

## Project status

This revival makes the existing application runnable and testable, but it does
**not** restart Zine as a supported project:

- There is no user support or support policy.
- There is no official community, chat, forum, or help channel.
- There is no release schedule or feature roadmap.
- Issues and pull requests may not receive a response.
- The software is provided as-is and should be evaluated carefully before use.

The test matrix covers Python 3.12, 3.13, and 3.14. Only fresh databases are
supported; migration of historical Zine installations is outside the scope of
this revival.

## Original codebase

The final commit from the original project history is
[`6d289f7`](https://github.com/mitsuhiko/zine/commit/6d289f7). It is preserved
under the [`original` tag](https://github.com/mitsuhiko/zine/tree/original).
The README from that codebase is retained as [README_OLD.txt](README_OLD.txt).

## Historical feature set

Zine includes:

- Blog posts, pages, comments, categories, tags, and Atom/RSS feeds
- User, group, and permission management
- Themes and an extensible plugin system
- WordPress, Atom, Blogger, and Zine export/import support
- Multiple markup parsers and syntax highlighting
- A translatable administration and public interface
- WSGI, CGI, FastCGI, and development-server entry points

The revival ports the core application, bundled and external example plugins,
database layer, networking and feed protocols, command-line tools,
documentation builders, and deployment runners to their modern Python
counterparts.

## Quickstart

Install [uv](https://docs.astral.sh/uv/), then run from a source checkout:

```console
$ uv sync --all-extras
$ mkdir -p instance
$ uv run zine-server -I instance
```

Open <http://127.0.0.1:4000/> and complete the setup wizard to create a fresh
database and administrator account.

The built-in server is for development only. See [INSTALL](INSTALL) for the
standard `venv`/`pip` workflow, available commands, and WSGI deployment notes.

## Tests

Run the complete suite with:

```console
$ uv run pytest
```

Warnings are treated as errors, and CI runs the suite on Python 3.12–3.14.

## License and authors

Zine is released under the BSD 3-Clause license. See [LICENSE](LICENSE) and
[AUTHORS](AUTHORS) for the original copyright and contributor information.
