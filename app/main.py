import socket  # noqa: F401

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


def main():
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    while True:
        conn, addr = server_socket.accept()
        with conn:
            data = conn.recv(1024).decode("utf-8")
            path = data.splitlines()[0].split()[1]
            if path == "/":
                response = HTTPResponse(200)
            elif path.startswith("/echo/"):
                body = path.removeprefix("/echo/")
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


if __name__ == "__main__":
    main()
