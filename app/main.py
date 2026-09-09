import socket
import threading

CRLF = "\r\n"


class HTTPResponse:
    def __init__(
        self,
        status_code: int,
        body: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}

    def __str__(self):
        status_code_status = {
            200: "OK",
            404: "Not Found",
        }
        status_line = (
            f"HTTP/1.1 {self.status_code} {status_code_status[self.status_code]}{CRLF}"
        )
        headers = "".join(
            f"{name}: {value}{CRLF}" for name, value in self.headers.items()
        )
        return f"{status_line}{headers}{CRLF}{self.body}"


def handle_connection(conn: socket.socket):
    with conn:
        data = conn.recv(1024).decode("utf-8")
        if not data:
            return
        path = data.splitlines()[0].split()[1]
        headers = {}
        for line in data.split(CRLF)[1:]:
            if not line:
                break
            name, separator, value = line.partition(":")
            if separator:
                headers[name.lower()] = value.strip(" \t")
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
        else:
            response = HTTPResponse(404)
        conn.sendall(str(response).encode())


def main():
    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    with server_socket:
        while True:
            conn, _ = server_socket.accept()
            threading.Thread(
                target=handle_connection, args=(conn,), daemon=True
            ).start()


if __name__ == "__main__":
    main()
