import http.server
import threading


def start_canary_server(request_log: list[str]) -> http.server.HTTPServer:
    class LoggingHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request_log.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"canary page")

        def log_message(self, format: str, *arguments: object) -> None:  # noqa: A002 - mirrors the stdlib signature
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), LoggingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
