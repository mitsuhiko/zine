import ast
import importlib.util
import runpy
import sys
from email import message_from_string, policy
from pathlib import Path
from urllib.parse import urlsplit
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


def _load_module(monkeypatch, name, relative_path, stubs=()):
    for stub_name, attributes in stubs:
        module = ModuleType(stub_name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, stub_name, module)
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _load_functions(relative_path, *names):
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(alias.name == "ast" for alias in node.names)
        or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    namespace = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return [namespace[name] for name in names]


def test_password_hash_formats_accept_text_and_bytes():
    crypto = runpy.run_path(str(ROOT / "zine/utils/crypto.py"))

    generated = crypto["gen_pwhash"]("pässword")
    assert generated.startswith("sha$")
    assert crypto["check_pwhash"](generated, "pässword")
    assert crypto["check_pwhash"](generated.encode("ascii"), "pässword".encode())
    assert crypto["check_pwhash"]("plain$$default", "default")
    assert crypto["check_pwhash"](
        "md5$xyz$bcc27016b4fdceb2bd1b369d5dc46c3f", "example"
    )
    assert not crypto["check_pwhash"](generated, "wrong")


def test_configuration_text_quoting_round_trip():
    quote_value, unquote_value = _load_functions(
        "zine/config.py", "quote_value", "unquote_value"
    )

    for value in ("simple", " Grüß dich ", "line one\nline two", 'a "quote"'):
        assert unquote_value(quote_value(value)) == value
    assert unquote_value("Grüße".encode()) == "Grüße"


def test_configuration_file_round_trip(monkeypatch, tmp_path):
    class Field:
        def __init__(self, *args, default="", **kwargs):
            self.default = default

        def __call__(self, value):
            return value

        def get_default(self):
            return self.default() if callable(self.default) else self.default

        def to_primitive(self, value):
            return str(value)

    log = ModuleType("log")
    log.error = lambda *args, **kwargs: None
    log.LEVELS = {"warning": 3}
    field_types = {
        name: Field
        for name in (
            "TextField",
            "IntegerField",
            "BooleanField",
            "ChoiceField",
            "CommaSeparated",
        )
    }
    config = _load_module(
        monkeypatch,
        "_zine_test_config",
        "zine/config.py",
        stubs=(
            ("zine.environment", {"MODE": "production"}),
            (
                "zine.i18n",
                {
                    "lazy_gettext": lambda value: value,
                    "_": lambda value: value,
                    "list_timezones": lambda: [],
                    "list_languages": lambda *args, **kwargs: [],
                },
            ),
            ("zine.utils", {"log": log}),
            ("zine.utils.forms", field_types),
            (
                "zine.utils.validators",
                {
                    "ValidationError": ValueError,
                    "is_valid_url_prefix": lambda: lambda value: True,
                    "is_valid_url_format": lambda: lambda value: True,
                    "is_netaddr": lambda: lambda value: True,
                    "is_valid_email": lambda: lambda value: True,
                },
            ),
            ("zine.application", {"InternalError": RuntimeError}),
        ),
    )

    filename = tmp_path / "zine.ini"
    filename.write_text('[zine]\nblog_title = "Grüße"\n', encoding="utf-8")
    cfg = config.Configuration(str(filename))
    cfg.config_vars = {"blog_title": Field(default="")}
    assert cfg["blog_title"] == "Grüße"
    assert cfg.items() == [("blog_title", "Grüße")]

    transaction = cfg.edit()
    transaction["blog_title"] = " neue Überschrift "
    transaction.commit()

    reloaded = config.Configuration(str(filename))
    reloaded.config_vars = {"blog_title": Field(default="")}
    assert reloaded["blog_title"] == " neue Überschrift "


def test_zeml_binary_serialization_round_trip(monkeypatch):
    datastructures = runpy.run_path(str(ROOT / "zine/utils/datastructures.py"))
    zeml = _load_module(
        monkeypatch,
        "_zine_test_zeml",
        "zine/utils/zeml.py",
        stubs=(
            ("werkzeug", {"escape": lambda value: value}),
            ("zine.i18n", {"_": lambda value: value}),
            ("zine.utils", {"log": ModuleType("log")}),
            ("zine.utils.text", {"wrap": lambda value, width: value}),
            (
                "zine.utils.datastructures",
                {"OrderedDict": datastructures["OrderedDict"]},
            ),
        ),
    )
    zeml.log.exception = lambda *args, **kwargs: None

    value = [None, 42, "Grüße", ["nested"]]
    serialized = zeml.dumps(value)
    assert isinstance(serialized, bytes)
    assert zeml.loads(serialized) == value

    root = zeml.RootElement()
    root.text = "vorher"
    child = zeml.Element("p")
    child.text = "Grüße"
    child.attributes["class"] = "intro"
    child.parent = root
    root.children.append(child)
    restored = zeml.loads(zeml.dumps(root))
    assert restored == root
    assert restored.children[0].parent is restored

    parser_data = {"example": [1, "zwei"]}
    serialized = zeml.dump_parser_data(parser_data)
    assert isinstance(serialized, bytes)
    assert zeml.load_parser_data(memoryview(serialized)) == parser_data


def test_logger_writes_and_reads_utf8_text(monkeypatch, tmp_path):
    io_helpers = runpy.run_path(str(ROOT / "zine/utils/io.py"))
    log = _load_module(
        monkeypatch,
        "_zine_test_log",
        "zine/utils/log.py",
        stubs=(
            ("zine.i18n", {"gettext": lambda value: value}),
            ("zine.application", {"get_application": lambda: None}),
            ("zine.utils.io", {"tail": io_helpers["tail"]}),
            (
                "zine.utils.dates",
                {
                    "format_iso8601": lambda value: value.isoformat(),
                    "parse_iso8601": __import__("datetime").datetime.fromisoformat,
                },
            ),
        ),
    )

    filename = tmp_path / "zine.log"
    logger = log.Logger(str(filename), "debug")
    logger.log("info", "Grüße\nzweite Zeile", "tests")
    page = logger.view().get_page(1)

    assert filename.read_text(encoding="utf-8").endswith("zweite Zeile\n")
    assert page.items[0].text == "Grüße\nzweite Zeile"


def test_http_handler_writes_bytes_to_socket(monkeypatch):
    class Response:
        def __init__(self, *args, **kwargs):
            self.response = args[0] if args else []

        def close(self):
            pass

    class Socket:
        def __init__(self):
            self.chunks = []

        def sendall(self, value):
            assert isinstance(value, bytes)
            self.chunks.append(value)

    net = _load_module(
        monkeypatch,
        "_zine_test_net",
        "zine/utils/net.py",
        stubs=(
            (
                "zine.application",
                {"Response": Response, "get_application": lambda: None},
            ),
            ("zine.utils.exceptions", {"ZineException": Exception}),
        ),
    )

    handler = net.HTTPHandler(urlsplit("http://example.com/submit"), method="POST")
    socket = Socket()
    handler._socket = socket
    handler.headers["Host"] = "example.com"
    handler.send_request("Grüße")

    assert b"POST /submit HTTP/1.1" in socket.chunks[0]
    assert socket.chunks[-1] == "Grüße".encode("utf-8")


def test_email_message_uses_unicode_headers_and_utf8_body(monkeypatch):
    mail = _load_module(
        monkeypatch,
        "_zine_test_mail",
        "zine/utils/mail.py",
        stubs=(
            (
                "zine.utils.validators",
                {"is_valid_email": lambda value: True, "check": lambda *args: True},
            ),
            ("zine.application", {"get_application": lambda: None}),
        ),
    )
    email = object.__new__(mail.EMail)
    email.subject = "Eine Überschrift"
    email.text = "Grüße aus Zine"
    email.from_addr = "Zine <zine@example.com>"
    email.to_addrs = ["user@example.com"]

    parsed = message_from_string(email.format("\n"), policy=policy.default)
    assert parsed["Subject"] == "Eine Überschrift"
    assert parsed.get_payload(decode=True).decode("utf-8") == "Grüße aus Zine"
