#!/usr/bin/env python3
"""Minimal local web UI for Monday — talks to the chat daemon. No Steve relay."""
from __future__ import annotations

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RUNTIME = Path(os.environ.get("MONDAY_RUNTIME_DIR", os.path.expanduser("~/.local/state/monday-chat")))
SOCK = RUNTIME / "chat.sock"
HOST, PORT = "127.0.0.1", 8765

HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Monday</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font:15px/1.45 system-ui,sans-serif; background:#0f1115; color:#e8eaed; }
  header { padding:14px 18px; border-bottom:1px solid #2a2f3a; display:flex; align-items:center; gap:10px; }
  header h1 { margin:0; font-size:18px; font-weight:600; }
  header .dot { width:8px; height:8px; border-radius:50%; background:#3dd68c; }
  #log { height: calc(100vh - 120px); overflow:auto; padding:16px 18px; display:flex; flex-direction:column; gap:10px; }
  .bubble { max-width:78%; padding:10px 12px; border-radius:12px; white-space:pre-wrap; }
  .me { align-self:flex-end; background:#2b5278; }
  .her { align-self:flex-start; background:#1c212b; border:1px solid #2a2f3a; }
  .her.unprompted { border-color:#3d7eff; }
  .meta { font-size:11px; opacity:.55; margin-bottom:4px; }
  form { display:flex; gap:8px; padding:12px 18px; border-top:1px solid #2a2f3a; }
  input { flex:1; background:#151922; border:1px solid #2a2f3a; color:inherit; border-radius:10px; padding:10px 12px; }
  button { background:#3d7eff; color:#fff; border:0; border-radius:10px; padding:10px 16px; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.5; }
</style></head><body>
<header><span class="dot"></span><h1>Monday</h1><span style="opacity:.5;font-size:13px">direct-call core · local · unprompted poll</span></header>
<div id="log"></div>
<form id="f"><input id="t" autocomplete="off" placeholder="Talk to Monday…" autofocus/><button id="b">Send</button></form>
<script>
const log = document.getElementById('log');
const f = document.getElementById('f');
const t = document.getElementById('t');
const b = document.getElementById('b');
function add(who, text, extraClass){
  const d=document.createElement('div');
  d.className='bubble '+(who==='me'?'me':'her')+(extraClass?' '+extraClass:'');
  const label = who==='me' ? 'You' : (extraClass==='unprompted' ? 'Monday (unprompted)' : 'Monday');
  d.innerHTML='<div class="meta">'+label+'</div>'+text.replace(/[&<>]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;' }[c]));
  log.appendChild(d); log.scrollTop=log.scrollHeight;
}
function showUnprompted(list){
  if(!Array.isArray(list)) return;
  for(const u of list){
    if(typeof u==='string' && u.trim()) add('her', u, 'unprompted');
  }
}
f.onsubmit=async (e)=>{
  e.preventDefault();
  const text=t.value.trim(); if(!text) return;
  t.value=''; add('me', text); b.disabled=true;
  try{
    const r=await fetch('/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,user_id:'matthew'})});
    const j=await r.json();
    if(j.ok){
      showUnprompted(j.unprompted);
      add('her', j.reply);
    } else {
      add('her','(error) '+(j.error||r.statusText));
    }
  }catch(err){ add('her','(error) '+err); }
  b.disabled=false; t.focus();
};
async function pollPending(){
  try{
    const r=await fetch('/pending?user_id=matthew');
    const j=await r.json();
    if(j.ok) showUnprompted(j.pending);
  }catch(_e){}
}
setInterval(pollPending, 3000);
pollPending();
</script></body></html>
"""


def monday_request(payload: dict) -> dict:
    if not SOCK.exists():
        raise RuntimeError(f"chat daemon not running ({SOCK})")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(SOCK))
        s.sendall((json.dumps(payload) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    data = json.loads(buf.decode() or "{}")
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Monday error")
    return data


def monday_say(text: str, user_id: str = "matthew") -> dict:
    return monday_request({"text": text, "user_id": user_id})


def monday_poll(user_id: str = "matthew") -> dict:
    return monday_request({"type": "poll", "user_id": user_id})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, obj: dict):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/pending":
            qs = parse_qs(parsed.query or "")
            user_id = (qs.get("user_id") or ["matthew"])[0]
            try:
                data = monday_poll(user_id)
                self._json(200, {"ok": True, "pending": data.get("pending") or []})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e), "pending": []})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/say":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw.decode() or "{}")
            data = monday_say(str(req.get("text") or ""), str(req.get("user_id") or "matthew"))
            self._json(
                200,
                {
                    "ok": True,
                    "reply": data.get("reply"),
                    "unprompted": data.get("unprompted") or [],
                },
            )
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Monday web chat http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
