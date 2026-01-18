import socket

class FreeCivClient:
    socket: socket.socket

    def connect(self, host: str, port: int) -> bool:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        return True

    def disconnect(self) -> bool:
        self.socket.close()
        return True
