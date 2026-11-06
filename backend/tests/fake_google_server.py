"""Stands in for workspace-mcp's sign-in tool: start_google_auth answers with a sign-in address, the way the
real server does in stdio mode. The test plays Google's callback by writing the account's credentials file.
FAKE_GOOGLE_FAIL makes the tool answer with the error the real server gives when it has no OAuth client.
FAKE_GOOGLE_CALLBACK ("ok:<address>" or "error") logs what the server logs when Google's answer arrives."""

import os
import sys
import threading
import time

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("fake-google")


def _callback(outcome: str) -> None:
    """What the real server logs (to stderr) when Google's answer reaches its local callback."""
    time.sleep(0.4)
    if outcome.startswith("ok:"):
        print(f"\x1b[32m2026-11-06 - auth.oauth_callback_server - INFO - OAuth callback: Successfully authenticated "
              f"user: {outcome[3:]}.\x1b[0m", file=sys.stderr, flush=True)  # coloured, like the real server
    else:
        print("\x1b[31m2026-11-06 - auth.oauth_callback_server - ERROR - Authentication failed: Google returned an "
              "error: access_denied.\x1b[0m", file=sys.stderr, flush=True)


@server.tool(annotations=ToolAnnotations(read_only_hint=False))
def start_google_auth(service_name: str, user_google_email: str = "") -> str:
    """Manually initiate Google OAuth authentication flow."""
    if os.environ.get("FAKE_GOOGLE_CALLBACK"):
        threading.Thread(target=_callback, args=(os.environ["FAKE_GOOGLE_CALLBACK"],), daemon=True).start()
    if os.environ.get("FAKE_GOOGLE_FAIL"):
        return "**Authentication Error:** OAuth client credentials not found. Set GOOGLE_OAUTH_CLIENT_ID."
    return ("**ACTION REQUIRED: Google Authentication Needed for " + service_name + "**\n\n"
            "1. Open this URL in your browser to authorize access using all required permissions:\n"
            "   Authorization URL: https://accounts.google.com/o/oauth2/auth?client_id=" +
            os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "") + "&login_hint=" + user_google_email + "&state=abc\n"
            "2. After successful authorization, **retry their original command**.")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def search_gmail_messages(query: str, user_google_email: str = "") -> str:
    """Search Gmail."""
    return f"1 message for {user_google_email}"


if __name__ == "__main__":
    server.run("stdio")
