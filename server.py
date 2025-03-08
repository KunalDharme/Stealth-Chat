import threading
import ssl
import socket
import colorama
import logging
import os
from colorama import Fore, Back, Style

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Get script directory
BANS_FILE = os.path.join(BASE_DIR, "data", "bans.txt")

CERTS_DIR = os.path.join(BASE_DIR, "certs")
CERT_FILE = os.path.join(CERTS_DIR, "server.crt")
KEY_FILE = os.path.join(CERTS_DIR, "server.key")

logging.basicConfig(level=logging.INFO)

# Initialize colorama for colored terminal output
colorama.init(autoreset=True)

SERVER_CERT = os.path.join(CERTS_DIR, "server.crt")
SERVER_KEY = os.path.join(CERTS_DIR, "server.key")   #server private key
SERVER_CONTEXT = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
SERVER_CONTEXT.load_cert_chain(certfile=SERVER_CERT, keyfile=SERVER_KEY)

# Define server host and port
host = '127.0.0.1'  # localhost
port = 54321

# Create and configure server socket
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen()

# Lists to store connected clients and their nicknames
clients = []
nicknames = []

def broadcast(message):
    """Send a message to all connected clients."""
    for client in clients:
        try:
            client.send(message)
        except:
            client.close()
            clients.remove(client)

def handle(client):
    """Handle messages from a specific client."""
    while True:
        try:
            msg = client.recv(1024).decode('ascii')
            if msg == 'EXIT':   # Client wants to exit
                if client in clients:
                    index = clients.index(client)
                    nickname = nicknames[index]
                    clients.remove(client)
                    nicknames.pop(index)
                    broadcast((Fore.YELLOW + f"{nickname} left the chat!" + Style.RESET_ALL).encode('ascii'))
                    print(Fore.YELLOW + f"{nickname} disconnected.")
                client.close()
                break # exit the loop

            elif msg.startswith('KICK '):
                if nicknames[clients.index(client)] == 'admin':
                    name_to_kick = msg[5:]
                    kick_user(name_to_kick)
                else:
                    client.send((Fore.YELLOW + 'Command was refused!').encode('ascii'))
            elif msg.startswith('BAN '):
                if nicknames[clients.index(client)] == 'admin':
                    name_to_ban = msg[4:]
                    kick_user(name_to_ban)
                    with open(BANS_FILE, 'a') as f:
                        f.write(f'{name_to_ban}\n')
                    print(Fore.RED + f'{name_to_ban} was banned!')
                else:
                    client.send((Fore.YELLOW + 'Command was refused!').encode('ascii'))

            else:
                broadcast(msg.encode('ascii'))  # Broadcast received message to all clients

        except:
            if client in clients:
                try:
                    index = clients.index(client)
                    clients.remove(client)
                    client.close()
                    nickname = nicknames.pop(index)
                    broadcast((Fore.YELLOW + f"{nickname} left the chat!").encode('ascii'))
                except ValueError:
                    pass #client was already removed

def receive():
    """Accept new client connections."""
    try:
        while True:
            client, address = server.accept()
            secure_client = SERVER_CONTEXT.wrap_socket(client, server_side=True)

            print(Fore.GREEN + f"Connected with {str(address)}")

            secure_client.send('NICK'.encode('ascii'))
            nickname = secure_client.recv(1024).decode('ascii')

            try:
                with open(BANS_FILE, 'r') as f:
                    bans = f.readlines()
            except FileNotFoundError:
                bans = []

            if nickname in [ban.strip() for ban in bans]:
                secure_client.send('BAN'.encode('ascii'))
                secure_client.close()
                continue

            if nickname == 'admin':
                secure_client.send('PASS'.encode('ascii'))
                password = secure_client.recv(1024).decode('ascii')

                if password != 'password':
                    secure_client.send('REFUSE'.encode('ascii'))
                    secure_client.close()
                    continue

            nicknames.append(nickname)
            clients.append(secure_client)

            print(Fore.BLUE + f"Nickname of the client is {nickname}!")
            broadcast((Fore.GREEN + f"{nickname} joined the chat!").encode('ascii'))
            secure_client.send((Back.YELLOW + Fore.BLACK + "Connected to the server!").encode('ascii'))

            thread = threading.Thread(target=handle, args=(secure_client,), daemon=True)
            thread.start()

    except KeyboardInterrupt:
        print(Fore.RED + "\nServer shutting down..")
        logging.info("server is shutting down...")

        for client in clients[:]:   #Iterate over a copy to prevent modification issues
            try:
                client.send(Fore.RED + "SERVER_SHUTDOWN".encode('ascii'))
            except:
                pass    #ignore errors if the client is already disconnected
            client.close()
        server.close()
        logging.info("Server successfully shut down.")
        exit(0)

def kick_user(name):
    """Remove a user from the chat if they are kicked."""
    if name in nicknames:
        name_index = nicknames.index(name)
        client_to_kick = clients[name_index]
        clients.remove(client_to_kick)
        nicknames.remove(name)

        try:
            client_to_kick.send((Fore.BLACK + Back.LIGHTRED_EX +'You were kicked by an admin!').encode('ascii'))
            client_to_kick.close()
        except:
            pass    #ignore if already disconnected

        broadcast((Fore.RED + f'{name} was kicked by an admin!').encode('ascii'))
    else:
        print(Fore.YELLOW + f"Attemped to kick {name}, but they are not in the chat.")

print(Fore.GREEN + "Server is listening...")
receive()
