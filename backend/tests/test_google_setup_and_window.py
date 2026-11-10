"""0.7.4: what the person sees when Google setup is incomplete, and a desktop window that never strands them on a
page outside the app."""

import importlib.util

from app.connectors import setup_hints
from tests.conftest import ROOT
from tests.test_connector_failures import client, manager, with_model

# Copied from workspace-mcp 2.3.0 (core/api_enablement.py, core/utils.py): its own message for APIs it maps,
# and Google's HttpError text for those it does not (People API).
WORKSPACE_MCP_GMAIL_OFF = ("API error in search_gmail_messages: Gmail API is not enabled for your project (637689955180)."
                           "\n\nEnable it here: https://console.cloud.google.com/flows/enableapi?apiid=gmail.googleapis.com"
                           "\n\nAfter enabling, wait 1-2 minutes for the change to propagate, then try again.")
GOOGLE_PEOPLE_OFF = ("API error in list_contacts: <HttpError 403 when requesting https://people.googleapis.com/v1/people/me"
                     "/connections returned \"People API has not been used in project 637689955180 before or it is disabled. "
                     "Enable it by visiting https://console.developers.google.com/apis/api/people.googleapis.com/overview"
                     "?project=637689955180 then retry.\". Details: \"[{'reason': 'accessNotConfigured'}]\">. The required "
                     "API is not enabled for your project.")


def test_an_api_that_is_off_is_named_with_the_link_that_turns_it_on():
    assert setup_hints(WORKSPACE_MCP_GMAIL_OFF) == [
        "Gmail API is switched off in Google Cloud project 637689955180. Whoever manages the OAuth client enables it "
        "once, then waits 2 minutes: https://console.cloud.google.com/apis/library/gmail.googleapis.com?project=637689955180"]
    assert setup_hints(GOOGLE_PEOPLE_OFF) == [
        "People API (contacts) is switched off in Google Cloud project 637689955180. Whoever manages the OAuth client "
        "enables it once, then waits 2 minutes: "
        "https://console.cloud.google.com/apis/library/people.googleapis.com?project=637689955180"]
    assert setup_hints("3 messages found") == [] and setup_hints("") == []


def test_chat_shows_the_link_when_a_google_api_is_off(tmp_path, monkeypatch):
    async def nothing(cfg):
        return None
    conns = manager(tmp_path, monkeypatch, nothing)

    async def call(cid, tool, arguments):
        return WORKSPACE_MCP_GMAIL_OFF, True
    monkeypatch.setattr(conns, "call", call)
    with client(conns, []) as c:
        with_model(c)
        chat = c.post("/api/chats", json={"agent_id": "critical-mentor", "data_class": "public"}).json()
        msg = c.post(f"/api/chats/{chat['id']}/messages", json={"content": "What is open in OPS?"}).json()
        hint = [w for w in msg["warnings"] if w.startswith("Gmail API is switched off")]
        assert hint and hint[0].endswith("gmail.googleapis.com?project=637689955180")
        assert msg["tool_calls"][0]["error"] is True


def load_launcher():
    spec = importlib.util.spec_from_file_location("launcher", ROOT / "desktop" / "launcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeWindow:
    def __init__(self, url):
        self.url, self.loaded = url, []

    def get_current_url(self):
        return self.url

    def load_url(self, url):
        self.loaded.append(url)


def test_a_page_outside_the_app_opens_in_the_browser_and_the_window_comes_back():
    keep_in_app = load_launcher().keep_in_app
    app, opened = "http://127.0.0.1:51234", []
    stray = FakeWindow("https://accounts.google.com/v3/signin/identifier?continue=https://console.cloud.google.com")
    assert keep_in_app(stray, app, opened.append)
    assert opened == [stray.url] and stray.loaded == [app]
    for own in (f"{app}/", f"{app}/#/chat", "about:blank", None):
        w = FakeWindow(own)
        assert not keep_in_app(w, app, opened.append) and w.loaded == []
    assert len(opened) == 1



def test_the_desktop_window_lets_people_select_and_copy_text(monkeypatch):
    """pywebview turns text selection off unless text_select=True: answers could not be selected and copied."""
    import sys
    import types
    made = {}
    fake = types.SimpleNamespace(settings={}, start=lambda **kw: None)

    def create_window(*args, **kwargs):
        made.update(kwargs)
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Handlers()))
    fake.create_window = create_window
    monkeypatch.setitem(sys.modules, "webview", fake)
    launcher = load_launcher()
    monkeypatch.setattr(launcher, "_has_linux_toolkit", lambda: True)  # run from source on a desktop with GTK
    assert launcher._open_window("http://127.0.0.1:1") is True
    assert made.get("text_select") is True


# ---------------------------------------------------------------- Linux: the window runs in the system's Python

def test_linux_package_without_a_toolkit_opens_the_window_with_the_system_python(monkeypatch):
    """The .deb has no GTK of its own: it used to fall back to the browser every time. Now it goes straight to the
    system Python (no in-process attempt, so no pywebview traceback in suite.log)."""
    import sys
    launcher = load_launcher()
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(launcher, "_has_linux_toolkit", lambda: False)
    monkeypatch.setattr(launcher, "_app_window", lambda: (_ for _ in ()).throw(AssertionError("no in-process try")))
    monkeypatch.setattr(launcher, "_system_window", lambda url, icon, check: calls.append((url, check)) or True)
    assert launcher._open_window("http://127.0.0.1:5", check=True) is True
    assert calls == [("http://127.0.0.1:5", True)]


def test_the_system_window_runs_the_helper_with_a_python_that_has_gtk(monkeypatch, tmp_path):
    launcher = load_launcher()
    (tmp_path / "desktop" / "pyweb").mkdir(parents=True)
    (tmp_path / "desktop" / "app_window.py").write_text("")
    (tmp_path / "desktop" / "assets").mkdir()
    monkeypatch.setattr(launcher, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "_system_pythons", lambda: ["/usr/bin/python3", "/usr/bin/python3.12", "/usr/bin/python3.10"])
    ran = []

    def run(cmd, **kw):
        ran.append(cmd)
        ok = cmd[0] == "/usr/bin/python3.12"  # python3 points at a version without the GTK bindings
        return type("R", (), {"returncode": 0 if ok else 1})()
    assert launcher._system_window("http://127.0.0.1:7", tmp_path / "desktop" / "assets" / "icon.png", True, run) is True
    probes, window = ran[:-1], ran[-1]
    assert [c[0] for c in probes] == ["/usr/bin/python3", "/usr/bin/python3.12"] and "WebKit2" in probes[0][-1]
    assert window == ["/usr/bin/python3.12", "-s", str(tmp_path / "desktop" / "app_window.py"),
                      "--libs", str(tmp_path / "desktop" / "pyweb"), "http://127.0.0.1:7", "--check"]
    # no system Python with GTK: False, so the launcher opens the browser
    assert launcher._system_window("http://127.0.0.1:7", tmp_path / "x.png", False,
                                   lambda cmd, **kw: type("R", (), {"returncode": 1})()) is False


def test_system_pythons_try_python3_then_newest_first(tmp_path):
    launcher = load_launcher()
    for name in ("python3", "python3.10", "python3.12", "python3.12-config", "python3.9"):
        (tmp_path / name).write_text("")
    assert launcher._system_pythons(str(tmp_path)) == [str(tmp_path / n) for n in ("python3", "python3.12", "python3.10", "python3.9")]


def test_the_system_python_does_not_inherit_the_bundles_libraries(monkeypatch):
    """PyInstaller points LD_LIBRARY_PATH at the bundle; a system Python loading those libraries can crash."""
    import sys
    launcher = load_launcher()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/productivity-suite/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/home/me/lib")
    monkeypatch.setenv("PYTHONHOME", "/opt/productivity-suite/_internal")
    env = launcher._system_env()
    assert env["LD_LIBRARY_PATH"] == "/home/me/lib" and "LD_LIBRARY_PATH_ORIG" not in env and "PYTHONHOME" not in env
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    assert "LD_LIBRARY_PATH" not in launcher._system_env()


def test_the_window_helper_says_when_no_native_window_can_open(monkeypatch, capsys):
    """Exit 3 (no GTK/WebKit or no display): the launcher then opens the browser instead."""
    import sys
    import types

    def start(**kw):
        raise RuntimeError("You must have either QT or GTK with Python extensions installed")
    fake = types.SimpleNamespace(settings={}, start=start,
                                 create_window=lambda *a, **k: types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Handlers())))
    monkeypatch.setitem(sys.modules, "webview", fake)
    sys.path.insert(0, str(ROOT / "desktop"))
    try:
        import app_window
    finally:
        sys.path.remove(str(ROOT / "desktop"))
    assert app_window.main(["http://127.0.0.1:9"]) == 3
    assert "Native window unavailable" in capsys.readouterr().err


class _Handlers(list):
    def __iadd__(self, fn):
        self.append(fn)
        return self
