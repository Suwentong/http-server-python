import argparse
import gzip
import socket
# [Stage 5: Concurrent connections] Each connection runs in its own thread.
import threading
from pathlib import Path

CRLF = "\r\n"


def client_requests_close(headers: dict[str, str]) -> bool:
    # [Stage 12: Persistent connections]
    # [Stage 14: Connection close]
    # HTTP/1.1 stays open unless the client lists "close" in the Connection header.
    tokens = [part.strip().lower() for part in headers.get("connection", "").split(",")]
    return "close" in tokens


def accepts_gzip(accept_encoding: str) -> bool:
    # [Stage 10: Multiple compression schemes]
    # Accept-Encoding may be one coding or a comma-separated list, such as
    # "encoding-1, gzip, encoding-2". Stage 9 uses the same check for a single "gzip".
    # Parameters such as ";q=1.0" are ignored. The server only supports gzip.
    for coding in accept_encoding.split(","):
        if coding.split(";", 1)[0].strip().lower() == "gzip":
            return True
    return False


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
            201: "Created",  # Stage 7: successful POST /files/{filename}.
            400: "Bad Request",
            404: "Not Found",
        }
        # [Stage 2: Extract the URL path]
        # Shared status writer: formats 200 OK or 404 Not Found for this stage.
        status_line = (
            f"HTTP/1.1 {self.status_code} {status_code_status[self.status_code]}{CRLF}"
        )
        # [Stage 9: Accept-Encoding and Content-Encoding]
        # Shared response writer: also emits Content-Encoding when it is set.
        headers = "".join(
            f"{name}: {value}{CRLF}" for name, value in self.headers.items()
        )
        # [Stage 3: Respond with a body — /echo/{str}]
        # Encode text as bytes and separate the headers from the body with a blank line.
        # Stage 11 passes an already gzip-compressed body when Content-Encoding is gzip.
        body = self.body.encode("utf-8") if isinstance(self.body, str) else self.body
        return f"{status_line}{headers}{CRLF}".encode("utf-8") + body


def handle_connection(conn: socket.socket, directory: Path | None = None):
    with conn:
        # [Stage 12: Persistent connections]
        # [Stage 13: Concurrent persistent connections]
        # This buffer belongs to one connection. Another client has its own thread and buffer.
        pending = bytearray()
        while True:
            while b"\r\n\r\n" not in pending:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                pending.extend(chunk)
            # [Stage 2: Extract the URL path]
            # Separate the headers from the body, then split the head into CRLF lines.
            head, rest = pending.split(b"\r\n\r\n", 1)
            lines = head.decode("iso-8859-1").split(CRLF)
            # Request line: "GET /index.html HTTP/1.1" -> path = "/index.html".
            # Stage 7 also uses the extracted method to identify POST requests.
            method, path, _ = lines[0].split()
            # [Stage 9: Accept-Encoding and Content-Encoding]
            # Shared header parser: stores Accept-Encoding as headers["accept-encoding"].
            # [Stage 4: Read a header — /user-agent]
            # Also stores User-Agent as headers["user-agent"], trimming surrounding whitespace.
            headers = {}
            for line in lines[1:]:
                name, separator, value = line.partition(":")
                if separator:
                    headers[name.lower()] = value.strip(" \t")
            # [Stage 7: Read a request body — POST /files/{filename}]
            # Content-Length tells us how many body bytes to read; reject invalid lengths.
            try:
                content_length = int(headers.get("content-length", "0"))
                if content_length < 0:
                    raise ValueError
            except ValueError:
                conn.sendall(bytes(HTTPResponse(400)))
                return
            # The initial receive may contain only part of the body; read the rest.
            while len(rest) < content_length:
                chunk = conn.recv(min(4096, content_length - len(rest)))
                if not chunk:
                    conn.sendall(bytes(HTTPResponse(400)))
                    return
                rest.extend(chunk)
            # Keep exactly the declared number of bytes for writing to the file.
            # Any bytes after that belong to the next request on this connection.
            body = bytes(rest[:content_length])
            pending = rest[content_length:]
            # [Stage 2: Extract the URL path]
            # The root path returns 200 OK; later stages add the routes below.
            if path == "/":
                response = HTTPResponse(200)
            elif path.startswith("/echo/") or path == "/user-agent":
                # [Stage 3: Respond with a body — /echo/{str}]
                # The echo route extracts "abc" from "/echo/abc" using removeprefix.
                # [Stage 4: Read a header — /user-agent]
                # For /user-agent, use the parsed User-Agent value as the response body.
                body = (
                    headers.get("user-agent", "")
                    if path == "/user-agent"
                    else path.removeprefix("/echo/")
                )
                # Stages 3 and 4 share this 200 response with the selected string as its body.
                body_bytes = body.encode("utf-8")
                response_headers = {
                    # Stages 3 and 4: identify plain text. Content-Length is set after compression.
                    "Content-Type": "text/plain",
                }
                # [Stage 9: Accept-Encoding and Content-Encoding]
                # [Stage 10: Multiple compression schemes]
                # [Stage 11: Gzip compression]
                # Compress the body when gzip is one of the client's codings.
                if accepts_gzip(headers.get("accept-encoding", "")):
                    body_bytes = gzip.compress(body_bytes)
                    response_headers["Content-Encoding"] = "gzip"
                response_headers["Content-Length"] = str(len(body_bytes))
                response = HTTPResponse(200, body=body_bytes, headers=response_headers)
            elif path.startswith("/files/") and directory is not None:
                # [Stage 6: Return a file — /files/{filename}]
                # Resolve the requested filename under the directory supplied by --directory.
                try:
                    file_path = (directory / path.removeprefix("/files/")).resolve()
                    # Keep file requests inside that directory.
                    if not file_path.is_relative_to(directory):
                        response = HTTPResponse(404)
                    elif method == "POST":
                        # [Stage 7: Read a request body — POST /files/{filename}]
                        # Save the body to the resolved filename and return 201 Created.
                        file_path.write_bytes(body)
                        response = HTTPResponse(201)
                    else:
                        # Stage 6: read the file as bytes and return 200 with its contents.
                        body = file_path.read_bytes()
                        response = HTTPResponse(
                            200,
                            body=body,
                            headers={
                                # Stage 6: binary content type and file size in bytes.
                                "Content-Type": "application/octet-stream",
                                "Content-Length": str(len(body)),
                            },
                        )
                except (OSError, ValueError):
                    # Stage 6: a missing file (or another file access error) returns 404.
                    response = HTTPResponse(404)
            else:
                # [Stage 2: Extract the URL path]
                # Any path not matched by a supported route returns 404 Not Found.
                response = HTTPResponse(404)
            # [Stage 12: Persistent connections]
            # [Stage 14: Connection close]
            # Echo Connection: close, then close the socket after this response.
            if client_requests_close(headers):
                response.headers["Connection"] = "close"
            conn.sendall(bytes(response))
            if client_requests_close(headers):
                return


def main():
    # [Stage 6: Return a file — /files/{filename}]
    # Read --directory and resolve the root used for file requests.
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve() if args.directory is not None else None
    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    with server_socket:
        while True:
            conn, _ = server_socket.accept()
            # [Stage 5: Concurrent connections]
            # [Stage 13: Concurrent persistent connections]
            # Each worker keeps its own socket open across requests, so clients do not block each other.
            threading.Thread(
                target=handle_connection, args=(conn, directory), daemon=True
            ).start()


if __name__ == "__main__":
    main()
