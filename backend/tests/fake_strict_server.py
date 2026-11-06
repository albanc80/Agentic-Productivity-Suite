"""An MCP stdio server that behaves like GitHub's (Go SDK) did on a slow first start: it takes a server/discover
probe as the start of its session, then refuses the initialize that follows with 'duplicate "initialize"
received'. Connectors must use the classic initialize handshake to work with it."""

import json
import sys

started = False


def reply(msg_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": msg_id}
    body.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(body) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    if not line.strip():
        continue
    msg = json.loads(line)
    method, msg_id = msg.get("method"), msg.get("id")
    if msg_id is None:  # a notification
        continue
    if method == "server/discover":
        started = True
        reply(msg_id, error={"code": -32601, "message": "method not found"})
    elif method == "initialize":
        if started:
            reply(msg_id, error={"code": 0, "message": 'duplicate "initialize" received'})
        else:
            started = True
            reply(msg_id, {"protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}},
                           "serverInfo": {"name": "strict", "version": "1.0"}})
    elif method == "tools/list":
        reply(msg_id, {"tools": [{"name": "get_repo", "description": "Get a repository.",
                                  "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}]})
    else:
        reply(msg_id, error={"code": -32601, "message": "method not found"})
