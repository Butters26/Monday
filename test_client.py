#!/usr/bin/env python3
import socket, struct, json, sys

SOCK="/tmp/thalamus.sock"
msg = {"type":"process_input","user_input":"hello there!"}

try:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCK)
    data = json.dumps(msg).encode('utf-8')
    sock.send(struct.pack('!I', len(data)) + data)
    length = sock.recv(4)
    if not length:
        print("No response")
        sys.exit(1)
    resp_len = struct.unpack('!I', length)[0]
    resp = b''
    while len(resp) < resp_len:
        chunk = sock.recv(min(resp_len - len(resp), 4096))
        if not chunk:
            break
        resp += chunk
    print("Thalamus reply:", json.loads(resp.decode('utf-8')))
    sock.close()
except Exception as e:
    print("Error:", e)

