import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# bind the socket to a public host, and a well-known port
s.bind((socket.gethostname(), 80))
# become a server socket
s.listen(5)

timeout=60## run 60 sec
s.settimeout(timeout)

while True: 
    clientsocket, address = s.accept()
    print(f"Connection from {address} has been established!")
    clientsocket.send(bytes("Welcome to the server!", 'utf-8'))
    clientsocket.close()

print("Exit!")