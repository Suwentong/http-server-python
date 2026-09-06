import socket  # noqa: F401

CRLF = "\r\n"


class HTTPResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def __str__(self):
        STATUS_CODE_STATUS = {
            200: "OK",
            404: "Not Found",
        }
        return f"HTTP/1.1 {self.status_code} {STATUS_CODE_STATUS[self.status_code]}{CRLF}{CRLF}"


def main():
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    while True:
        conn, addr = server_socket.accept()
        with conn:
            data = conn.recv(1024).decode("utf-8")
            path = data.splitlines()[0].split()[1]
            response = HTTPResponse(200) if path == "/" else HTTPResponse(404)
            conn.sendall(str(response).encode())


if __name__ == "__main__":
    main()
