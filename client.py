import socket
import ssl
import threading
import colorama
import os
from colorama import Fore, Back, Style

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERTS_DIR = os.path.join(BASE_DIR, "certs")
CERT_FILE = os.path.join(CERTS_DIR, "server.crt")

# Initialize colorama for colored console output
colorama.init(autoreset=True)

SERVER_CERT = os.path.join(CERTS_DIR, "server.crt") #Server certificate to verify authenticity
CLIENT_CONTEXT = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
CLIENT_CONTEXT.load_verify_locations(SERVER_CERT)

# Get user's nickname
nickname = input(Fore.BLUE + "Choose a nickname: ")
password = None

# If the user is 'admin', prompt for a password
if nickname == 'admin':
    password = input("Enter password for admin: ")

# Create a client socket and connect to the server
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
secure_client = CLIENT_CONTEXT.wrap_socket(client, server_hostname='127.0.0.1')
secure_client.connect(('127.0.0.1', 54321))

stop_thread = False  # Flag to stop threads when needed

def receive():
    """Function to receive messages from the server."""
    global stop_thread
    try:
        while True:
            if stop_thread:
                break
            try:
                message = secure_client.recv(1024).decode('ascii')

                # Handle server authentication requests
                if message == 'NICK':
                    secure_client.send(nickname.encode('ascii'))
                    next_message = secure_client.recv(1024).decode('ascii')

                    if next_message == 'PASS' and password:
                        secure_client.send(password.encode('ascii'))
                        if secure_client.recv(1024).decode('ascii') == 'REFUSE':
                            print(Fore.RED + "Connection was refused! Wrong password.")
                            stop_thread = True

                    elif next_message == 'BAN':
                        print(Fore.RED + "Connection refused because you are banned!")
                        secure_client.close()
                        stop_thread = True
                        exit()
                else:
                    print(message)  # Print received messages
            except Exception as e:
                print(Fore.RED + f"An error occurred!: {e}")
                stop_thread = True
                secure_client.close()
                break
    except KeyboardInterrupt:
        print(Fore.RED + "\nExiting chat...")
        stop_thread = True
        secure_client.close()
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
                secure_client.send("EXIT".encode('ascii'))
                stop_thread = True
                secure_client.close()
                break

            # Handle exit command
            if message == "/exit":
                print(Fore.YELLOW + "You have left the chat.")
                secure_client.send("EXIT".encode('ascii'))
                stop_thread = True
                secure_client.close()
                break   #exit the write loop

            formatted_message = f'{Fore.GREEN}{nickname}{Style.RESET_ALL}: {Fore.CYAN}{message}{Style.RESET_ALL}'

            if message.startswith('/'):
                # Admin-only commands
                if nickname == 'admin':
                    if message.startswith('/kick '):
                        secure_client.send(f'KICK {message[6:]}'.encode('ascii'))
                    elif message.startswith('/ban '):
                        secure_client.send(f'BAN {message[5:]}'.encode('ascii'))
                    else:
                        print(Fore.YELLOW + "Unknown command!")
                else:
                    print(Fore.YELLOW + "Commands can only be executed by the admin!")
            else:
                secure_client.send(formatted_message.encode('ascii'))        
    except KeyboardInterrupt:
        print(Fore.RED + "\nExiting chat...")
        secure_client.send("EXIT".encode('ascii'))
        stop_thread = True
        secure_client.close()
        exit(0)

# Start the receiving and writing threads
receive_thread = threading.Thread(target=receive)
receive_thread.start()

write_thread = threading.Thread(target=write)
write_thread.start()

receive_thread.join()
write_thread.join()