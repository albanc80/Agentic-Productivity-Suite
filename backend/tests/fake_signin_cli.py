"""Stands in for a connector server's sign-in commands (shaped like @softeria/ms-365-mcp-server).

State lives in the JSON file named by FAKE_SIGNIN_STATE: {"accounts": [...], "approve": "<username>"}.
--login prints the device-code prompt, waits until the test writes "approve" (the person entering the
code), then signs that account in and prints a JSON result. FAKE_SIGNIN_FAIL makes the sign-in fail.
"""

import json
import os
import sys
import time

STATE = os.environ["FAKE_SIGNIN_STATE"]


def load() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"accounts": []}


def save(state: dict) -> None:
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def main() -> int:
    args = sys.argv[1:]
    if "--list-accounts" in args:
        print(json.dumps({"accounts": load()["accounts"]}))
        return 0
    if "--remove-account" in args:
        target = args[args.index("--remove-account") + 1]
        state = load()
        left = [a for a in state["accounts"] if a["id"] != target]
        if len(left) == len(state["accounts"]):
            print(json.dumps({"error": f"Account not found: {target}"}))
            return 1
        state["accounts"] = left
        save(state)
        print(json.dumps({"message": f"Removed account: {target}"}))
        return 0
    if "--login" in args:
        print("npm warn deprecated something@1.0.0: noise on stderr", file=sys.stderr)
        print("\nTo sign in, use a web browser to open the page https://login.microsoft.com/device and enter the code"
              " FAKE12345 to authenticate.\n", flush=True)
        if os.environ.get("FAKE_SIGNIN_FAIL"):
            print("AADSTS70016: the user declined the sign-in", file=sys.stderr)
            print(json.dumps({"success": False, "message": "Login failed: the user declined"}))
            return 0
        for _ in range(400):
            state = load()
            user = state.pop("approve", None)
            if user:
                if not any(a["username"] == user for a in state["accounts"]):
                    state["accounts"].append({"id": f"uid-{len(state['accounts']) + 1}.tid", "username": user,
                                              "name": user.split("@")[0], "selected": not state["accounts"]})
                save(state)
                print(json.dumps({"success": True, "message": "Login successful",
                                  "userData": {"displayName": user, "userPrincipalName": user.upper()}}))
                return 0
            time.sleep(0.05)
        return 1
    print("server mode is not faked", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
