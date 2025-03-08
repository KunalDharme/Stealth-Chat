import socket
import threading
import colorama
from colorama import Fore, Back, Style

# Initialize colorama for colored console output
colorama.init(autoreset=True)

# Get user's nickname
nickname = input(Fore.BLUE + "Choose a nickname: ")
password = None

# If the user is 'admin', prompt for a password
if nickname == 'admin':
    password = input("Enter password for admin: ")

# Create a client socket and connect to the server
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('127.0.0.1', 54321))

stop_thread = False  # Flag to stop threads when needed

def receive():
    """Function to receive messages from the server."""
    global stop_thread
    try:
        while True:
            if stop_thread:
                break
            try:
                message = client.recv(1024).decode('ascii')

                # Handle server authentication requests
                if message == 'NICK':
                    client.send(nickname.encode('ascii'))
                    next_message = client.recv(1024).decode('ascii')

                    if next_message == 'PASS':
                        client.send(password.encode('ascii'))
                        if client.recv(1024).decode('ascii') == 'REFUSE':
                            print(Fore.RED + "Connection was refused! Wrong password.")
                            stop_thread = True

                    elif next_message == 'BAN':
                        print(Fore.RED + "Connection refused because you are banned!")
                        client.close()
                        stop_thread = True

                else:
                    print(message)  # Print received messages
            except:
                print(Fore.RED + "An error occurred!")
                stop_thread = True
                client.close()
                break
    except KeyboardInterrupt:
        print(Fore.RED + "\nExiting chat...")
        stop_thread = True
        client.close()
        exit()

def write():
    """Function to send messages to the server."""
    global stop_thread
    try:
        while True:
            if stop_thread:
                break
            try:
                message = input("")     # Get user input
            except EOFError:
                print(Fore.RED + "\nExiting chat due to EOFError...")
                client.send("EXIT".encode('ascii'))
                stop_thread = True
                client.close()
                break

            # Handle exit command
            if message == "/exit":
                print(Fore.YELLOW + "You have left the chat.")
                client.send("EXIT".encode('ascii'))
                stop_thread = True
                client.close()
                break   #exit the write loop

            formatted_message = f'{Fore.GREEN}{nickname}{Style.RESET_ALL}: {Fore.CYAN}{message}{Style.RESET_ALL}'

            if message.startswith('/'):
                # Admin-only commands
                if nickname == 'admin':
                    if message.startswith('/kick '):
                        client.send(f'KICK {message[6:]}'.encode('ascii'))
                    elif message.startswith('/ban '):
                        client.send(f'BAN {message[5:]}'.encode('ascii'))
                else:
                    print(Fore.YELLOW + "Commands can only be executed by the admin!")
            else:
                client.send(formatted_message.encode('ascii'))        
    except KeyboardInterrupt:
        print(Fore.RED + "\nExiting chat...")
        client.send("EXIT".encode('ascii'))
        stop_thread = True
        client.close()
        exit(0)

# Start the receiving and writing threads
receive_thread = threading.Thread(target=receive)
receive_thread.start()

write_thread = threading.Thread(target=write)
write_thread.start()
