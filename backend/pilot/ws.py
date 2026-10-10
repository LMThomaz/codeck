"""WebSocket mínimo (RFC 6455) sobre o BaseHTTPRequestHandler — só a biblioteca padrão.

Serve os terminais: o navegador fala WebSocket com o servidor local; cada conexão roda na thread do próprio pedido
(ThreadingHTTPServer). Suporta texto/binário, ping/pong, close e mensagens fragmentadas. Sem extensões (deflate).

O navegador não manda cabeçalhos próprios no WebSocket, então a chave da execução vem no subprotocolo
("commitdeck.<token>") — nunca na URL, que pode parar em log.
"""
import base64
import hashlib
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TEXT, BINARY, CLOSE, PING, PONG = 0x1, 0x2, 0x8, 0x9, 0xA


class Closed(Exception):
    pass


class WebSocket:
    def __init__(self, handler):
        self.h = handler
        self.rfile, self.wfile = handler.rfile, handler.wfile
        self._send_lock = threading.Lock()
        self.closed = False

    @staticmethod
    def offered_protocols(handler):
        return [p.strip() for p in (handler.headers.get("Sec-WebSocket-Protocol") or "").split(",") if p.strip()]

    @classmethod
    def accept(cls, handler, protocol=None):
        key = handler.headers.get("Sec-WebSocket-Key")
        if not key or (handler.headers.get("Upgrade") or "").lower() != "websocket":
            raise ValueError("não é um pedido de WebSocket")
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        handler.send_response(101, "Switching Protocols")
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept)
        if protocol:
            handler.send_header("Sec-WebSocket-Protocol", protocol)
        handler.end_headers()
        handler.close_connection = True   # depois do WebSocket, a conexão não volta a ser HTTP
        return cls(handler)

    # ------------------------------------------------------------ envio
    def _frame(self, opcode, payload):
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([n])
        elif n < 65536:
            head += bytes([126]) + struct.pack("!H", n)
        else:
            head += bytes([127]) + struct.pack("!Q", n)
        with self._send_lock:
            if self.closed:
                raise Closed()
            try:
                self.wfile.write(head + payload)
                self.wfile.flush()
            except OSError:
                self.closed = True
                raise Closed() from None

    def send_text(self, text):
        self._frame(TEXT, text.encode("utf-8"))

    def send_bytes(self, data):
        self._frame(BINARY, bytes(data))

    def close(self, code=1000):
        try:
            self._frame(CLOSE, struct.pack("!H", code))
        except Closed:
            pass
        self.closed = True

    # ------------------------------------------------------------ recepção
    def _read(self, n):
        data = self.rfile.read(n)
        if len(data) < n:
            raise Closed()
        return data

    def recv(self):
        """Próxima mensagem completa: (opcode, bytes). Responde ping sozinho; levanta Closed no fim."""
        parts, first_op = [], None
        while True:
            b1, b2 = self._read(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            if n > 16 * 1024 * 1024:
                raise Closed()   # mensagem absurda: derruba a conexão
            mask = self._read(4) if b2 & 0x80 else None
            payload = bytearray(self._read(n))
            if mask:
                for i in range(n):
                    payload[i] ^= mask[i % 4]
            if op == CLOSE:
                self.close()
                raise Closed()
            if op == PING:
                self._frame(PONG, bytes(payload))
                continue
            if op == PONG:
                continue
            if op != 0:
                first_op = op
            parts.append(bytes(payload))
            if fin:
                return first_op or TEXT, b"".join(parts)
