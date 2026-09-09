import argparse
import socket
import threading
from pathlib import Path

CRLF = "\r\n"


class HTTPResponse:
    def __init__(
        self,
        status_code: int,
        body: str | bytes = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}

    def __bytes__(self):
        status_code_status = {
            200: "OK",
            201: "Created",
            400: "Bad Request",
            404: "Not Found",
        }
        status_line = (
            f"HTTP/1.1 {self.status_code} {status_code_status[self.status_code]}{CRLF}"
        )
        headers = "".join(
            f"{name}: {value}{CRLF}" for name, value in self.headers.items()
        )
        body = self.body.encode("utf-8") if isinstance(self.body, str) else self.body
        return f"{status_line}{headers}{CRLF}".encode("utf-8") + body


def handle_connection(conn: socket.socket, directory: Path | None = None):
    with conn:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data.extend(chunk)
        head, body = data.split(b"\r\n\r\n", 1)
        lines = head.decode("iso-8859-1").split(CRLF)
        method, path, _ = lines[0].split()
        headers = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if separator:
                headers[name.lower()] = value.strip(" \t")
        try:
            content_length = int(headers.get("content-length", "0"))
            if content_length < 0:
                raise ValueError
        except ValueError:
            conn.sendall(bytes(HTTPResponse(400)))
            return
        while len(body) < content_length:
            chunk = conn.recv(min(4096, content_length - len(body)))
            if not chunk:
                conn.sendall(bytes(HTTPResponse(400)))
                return
            body.extend(chunk)
        body = bytes(body[:content_length])
        if path == "/":
            response = HTTPResponse(200)
        elif path.startswith("/echo/") or path == "/user-agent":
            body = (
                headers.get("user-agent", "")
                if path == "/user-agent"
                else path.removeprefix("/echo/")
            )
            response = HTTPResponse(
                200,
                body=body,
                headers={
                    "Content-Type": "text/plain",
                    "Content-Length": str(len(body.encode("utf-8"))),
                },
            )
        elif path.startswith("/files/") and directory is not None:
            try:
                file_path = (directory / path.removeprefix("/files/")).resolve()
                if not file_path.is_relative_to(directory):
                    response = HTTPResponse(404)
                elif method == "POST":
                    file_path.write_bytes(body)
                    response = HTTPResponse(201)
                else:
                    body = file_path.read_bytes()
                    response = HTTPResponse(
                        200,
                        body=body,
                        headers={
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(len(body)),
                        },
                    )
            except (OSError, ValueError):
                response = HTTPResponse(404)
        else:
            response = HTTPResponse(404)
        conn.sendall(bytes(response))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve() if args.directory is not None else None
    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    with server_socket:
        while True:
            conn, _ = server_socket.accept()
            threading.Thread(
                target=handle_connection, args=(conn, directory), daemon=True
            ).start()


if __name__ == "__main__":
    main()
