"""Command-line entry points for running and managing Zine instances."""

from code import interact
import os
from pathlib import Path
import sys
from optparse import OptionParser
from urllib.parse import urlparse


def find_instance(start=None):
    """Locate an instance below or above the current working directory."""
    current = Path(start or os.getcwd()).resolve()
    development_instance = current / "instance"
    if (development_instance / "zine.ini").is_file():
        return str(development_instance)
    for candidate in (current, *current.parents):
        if (candidate / "zine.ini").is_file():
            return str(candidate)
    return None


def _get_instance(parser, configured):
    instance = configured or find_instance()
    if instance is None:
        parser.error("instance not found. Specify a path with --instance")
    return os.path.abspath(instance)


def server_main(argv=None):
    """Run the Werkzeug development server."""
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.middleware.profiler import ProfilerMiddleware
    from werkzeug.serving import run_simple
    from werkzeug.wrappers import Response

    from zine import get_wsgi_app

    parser = OptionParser(usage="%prog [options]")
    parser.add_option("--hostname", "-a", default="127.0.0.1")
    parser.add_option("--port", "-p", type="int", default=4000)
    parser.add_option("--no-reloader", dest="reloader", action="store_false",
                      default=True, help="Disable the reloader")
    parser.add_option("--no-debugger", dest="debugger", action="store_false",
                      default=True, help="Disable the debugger")
    parser.add_option("--threaded", action="store_true", default=False,
                      help="Activate multithreading")
    parser.add_option("--profile", action="store_true",
                      help="Enable the profiler")
    parser.add_option("--mount", default="/", help="Mount below this URL path")
    parser.add_option("--instance", "-I", help="Use this Zine instance")
    options, args = parser.parse_args(argv)
    if args:
        parser.error("incorrect number of arguments")
    instance = _get_instance(parser, options.instance)

    app = get_wsgi_app(instance)
    if options.profile:
        app = ProfilerMiddleware(app, stream=sys.stderr)

    if options.mount != "/":
        mountpoint = options.mount.rstrip("/")
        if not mountpoint.startswith("/"):
            parser.error("mount point has to start with a slash")
        root_app = Response(
            "<!doctype html><title>Page Not Found</title>"
            "<h2>Page Not Found</h2>"
            f'<p>The blog is mounted at <a href="{mountpoint}">{mountpoint}</a>.',
            mimetype="text/html",
        )
        app = DispatcherMiddleware(root_app, {mountpoint: app})

    run_simple(
        options.hostname,
        options.port,
        app,
        threaded=options.threaded,
        use_reloader=options.reloader,
        use_debugger=options.debugger,
    )


def _shell_namespace(instance):
    from zine import setup

    app = setup(instance)
    from zine import models
    from zine.database import db

    return {
        "app": app,
        "db": db,
        "instance": instance,
        "models": models,
    }


def shell_main(argv=None):
    """Open an interactive shell with an initialized Zine application."""
    parser = OptionParser(usage="%prog [options]")
    parser.add_option("--no-ipython", action="store_true",
                      help="Do not launch IPython, even if installed")
    parser.add_option("--instance", "-I", help="Use this Zine instance")
    options, args = parser.parse_args(argv)
    if args:
        parser.error("incorrect number of arguments")
    instance = _get_instance(parser, options.instance)
    namespace = _shell_namespace(instance)
    banner = "Zine Shell [%s]" % instance

    if not options.no_ipython:
        try:
            from IPython import start_ipython
        except ImportError:
            pass
        else:
            start_ipython(argv=[], user_ns=namespace)
            return
    interact(banner=banner, local=namespace)


def reset_instance_main(argv=None):
    """Replace an instance with a new database and administrator account."""
    import shutil

    parser = OptionParser(usage="%prog [options] [path]")
    parser.add_option("--username", "-u", default="admin")
    parser.add_option("--password", "-p", default="default")
    parser.add_option("--blog-url", default="http://localhost:4000/")
    parser.add_option("--database", dest="database_uri",
                      default="sqlite://zine.db")
    parser.add_option("--language", dest="lang", default="en")
    parser.add_option("--keep-plugins", action="store_true", default=False)
    options, args = parser.parse_args(argv)
    if len(args) > 1:
        parser.error("incorrect number of arguments")
    if args:
        instance = os.path.abspath(args[0])
    else:
        instance = _get_instance(parser, None)

    print("Resetting instance", instance)
    if options.keep_plugins:
        os.makedirs(instance, exist_ok=True)
        for filename in os.listdir(instance):
            target = os.path.join(instance, filename)
            if os.path.isdir(target) and filename == "plugins":
                continue
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.unlink(target)
    else:
        shutil.rmtree(instance, ignore_errors=True)
        os.makedirs(instance)

    from zine.config import Configuration
    from zine.database import db, init_database
    from zine.utils.crypto import gen_secret_key

    engine = db.create_engine(options.database_uri, instance)
    init_database(engine)
    config = Configuration(os.path.join(instance, "zine.ini"))
    transaction = config.edit()
    transaction.update(
        maintenance_mode=False,
        blog_url=options.blog_url,
        secret_key=gen_secret_key(),
        database_uri=options.database_uri,
        language=options.lang,
        plugins="vessel_theme",
        theme="vessel",
    )
    transaction.commit()

    from zine import setup
    from zine.models import User
    from zine.privileges import BLOG_ADMIN

    setup(instance)
    user = User(options.username, options.password, "admin@localhost",
                is_author=True)
    user.own_privileges.add(BLOG_ADMIN)
    db.commit()
    print("All done.")


def create_apache_config_main(argv=None):
    """Print Apache aliases for an instance's static exports."""
    from zine import setup

    parser = OptionParser(usage="%prog [options]")
    parser.add_option("--instance", "-I", help="Use this Zine instance")
    options, args = parser.parse_args(argv)
    if args:
        parser.error("incorrect number of arguments")
    app = setup(_get_instance(parser, options.instance))
    prefix = urlparse(app.cfg["blog_url"]).path.rstrip("/")
    for alias, destination in app._shared_exports.items():
        destination = os.path.abspath(destination)
        if any(character.isspace() for character in destination):
            destination = '"%s"' % destination
        print("Alias %s%s %s" % (prefix, alias, destination))


def regenerate_post_uids_main(argv=None):
    """Regenerate feed tag URIs for all posts in an instance."""
    from zine import setup

    parser = OptionParser(usage="%prog [options]")
    parser.add_option("--instance", "-I", help="Use this Zine instance")
    options, args = parser.parse_args(argv)
    if args:
        parser.error("incorrect number of arguments")
    app = setup(_get_instance(parser, options.instance))

    from zine.database import db
    from zine.models import Post
    from zine.utils.text import build_tag_uri

    for post in Post.query.all():
        post.uid = build_tag_uri(app, post.pub_date, post.content_type, post.slug)
    db.commit()
    print("Done regenerating post uids.")
