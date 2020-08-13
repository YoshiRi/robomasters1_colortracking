# server側
import socket
from contextlib import closing

# message to val
def get_reference(message):
    vals_= message.decode().split(',')
    newlist = []
    for val in vals:
        newlist.append(float(val))
    return newlist

def run_server():
    # parameter
    host = '127.0.0.1'
    port = 8888
    backlog = 5
    buf_size = 4096
    timeout = 60
    #init
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    with closing(sock):
        sock.bind((host, port))
        sock.listen(backlog)
        while True:
            clientsocket, address = sock.accept()
            with closing(clientsocket):
                msg = clientsocket.recv(buf_size)
                print(msg)
                print(get_reference(msg))
                clientsocket.send(msg)
    return

print("Exit!")