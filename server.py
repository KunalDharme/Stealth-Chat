import threading
import socket
import colorama
from colorama import Fore, Back, Style

# Initialize colorama for colored terminal output
colorama.init(autoreset=True)

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
                    with open('bans.txt', 'a') as f:
                        f.write(f'{name_to_ban}\n')
                    print(Fore.RED + f'{name_to_ban} was banned!')
                else:
                    client.send((Fore.YELLOW + 'Command was refused!').encode('ascii'))

            else:
                broadcast(msg.encode('ascii'))  # Broadcast received message to all clients

        except:
            if client in clients:
                index = clients.index(client)
                clients.remove(client)
                client.close()
                nickname = nicknames.pop(index)
                broadcast((Fore.YELLOW + f"{nickname} left the chat!").encode('ascii'))
                break

def receive():
    """Accept new client connections."""
    try:
        while True:
            client, address = server.accept()
            print(Fore.GREEN + f"Connected with {str(address)}")

            client.send('NICK'.encode('ascii'))
            nickname = client.recv(1024).decode('ascii')

            try:
                with open('bans.txt', 'r') as f:
                    bans = f.readlines()
            except FileNotFoundError:
                bans = []

            if nickname + '\n' in bans:
                client.send('BAN'.encode('ascii'))
                client.close()
                continue

            if nickname == 'admin':
                client.send('PASS'.encode('ascii'))
                password = client.recv(1024).decode('ascii')

                if password != 'password':
                    client.send('REFUSE'.encode('ascii'))
                    client.close()
                    continue

            nicknames.append(nickname)
            clients.append(client)

            print(Fore.BLUE + f"Nickname of the client is {nickname}!")
            broadcast((Fore.GREEN + f"{nickname} joined the chat!").encode('ascii'))
            client.send((Back.YELLOW + Fore.BLACK + "Connected to the server!").encode('ascii'))

            thread = threading.Thread(target=handle, args=(client,))
            thread.start()

    except KeyboardInterrupt:
        print(Fore.RED + "\nServer shutting down..")
        for client in clients:
            client.send("SERVER_SHUTDOWN".encode('ascii'))
            client.close()
        server.close()
        exit(0)

def kick_user(name):
    """Remove a user from the chat if they are kicked."""
    if name in nicknames:
        name_index = nicknames.index(name)
        client_to_kick = clients[name_index]
        clients.remove(client_to_kick)
        client_to_kick.send((Fore.BLACK + Back.LIGHTRED_EX +'You were kicked by an admin!').encode('ascii'))
        client_to_kick.close()
        nicknames.remove(name)
        broadcast((Fore.RED + f'{name} was kicked by an admin!').encode('ascii'))

print(Fore.GREEN + "Server is listening...")
receive()
