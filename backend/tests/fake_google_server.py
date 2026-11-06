"""Stands in for workspace-mcp's sign-in tool: start_google_auth answers with a sign-in address, the way the
real server does in stdio mode. The test plays Google's callback by writing the account's credentials file.
FAKE_GOOGLE_FAIL makes the tool answer with the error the real server gives when it has no OAuth client."""

import os

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("fake-google")


@server.tool(annotations=ToolAnnotations(read_only_hint=False))
def start_google_auth(service_name: str, user_google_email: str = "") -> str:
    """Manually initiate Google OAuth authentication flow."""
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
