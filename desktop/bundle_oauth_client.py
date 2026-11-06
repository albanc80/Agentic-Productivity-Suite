"""Build step: put the Google OAuth client into the installers, from the GOOGLE_OAUTH_CLIENT_JSON secret.

The secret holds the JSON file Google Cloud downloads for a Desktop app client. It is written to
config/google-oauth-client.json, which the PyInstaller spec bundles with the rest of config/ and which git
ignores. Without the secret the installers ship without a built-in client and people enter their own in
Settings. The file's contents are never printed. A secret that is not a usable client fails the build.
"""

import json
import os
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "config" / "google-oauth-client.json"


def main() -> int:
    raw = os.environ.get("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    if not raw:
        print("No GOOGLE_OAUTH_CLIENT_JSON secret: the installers have no built-in Google client.")
        return 0
    try:
        data = json.loads(raw)
        body = data.get("installed") or data.get("web")
        ok = isinstance(body, dict) and body.get("client_id") and body.get("client_secret")
    except (ValueError, AttributeError):
        ok = False
    if not ok:
        print("GOOGLE_OAUTH_CLIENT_JSON is not a Google OAuth client file "
              '({"installed": {"client_id": ..., "client_secret": ...}}). Download it again from Google Cloud.',
              file=sys.stderr)
        return 1
    TARGET.write_text(json.dumps(data), encoding="utf-8")
    kind = "Desktop app" if "installed" in data else "Web application"
    print(f"Built-in Google client written ({kind} client).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
