#!/usr/bin/env python3
"""Minimal webhook agent for AGENT=webhook.

POST JSON:
  {"repo_url": "...", "instructions": "...", "verify_target": "https://..."}

Response JSON:
  {"text": "one sentence for the caller or diagnosis body", "ok": true}

Set AGENT_COMMAND to a shell command that reads instructions on stdin and prints text.
Example:
  export AGENT_COMMAND='claude -p'
  python3 examples/agent_webhook.py
  export AGENT_WEBHOOK_URL=http://127.0.0.1:9000/run
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {"/run", "/"}:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode())
        instructions = str(body.get("instructions") or "")
        cmd = os.environ.get("AGENT_COMMAND", "").strip()
        if not cmd:
            text = (
                "Webhook received instructions. Set AGENT_COMMAND to run your agent."
            )
            ok = False
        else:
            proc = subprocess.run(
                cmd,
                shell=True,
                input=instructions,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("AGENT_TIMEOUT", "600")),
            )
            text = (proc.stdout or proc.stderr or "").strip()
            ok = proc.returncode == 0 and bool(text)
        payload = {"text": text or "No output from agent.", "ok": ok}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def main() -> None:
    port = int(os.environ.get("PORT", "9000"))
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Listening on http://127.0.0.1:{port}/run", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
