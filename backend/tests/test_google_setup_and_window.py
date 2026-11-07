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

