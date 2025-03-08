# Stealth-Chat
# Author : Kunal Dharme

Stealth-Chat is a secure, SSL/TLS-encrypted chat application that enables multiple users to communicate privately. The application consists of a server and multiple clients, with additional administrative controls such as banning and kicking users.

## Features
- **Secure Communication**: Uses SSL/TLS encryption for secure message transmission.
- **Admin Controls**: Admin can kick or ban users.
- **User Authentication**: Admin authentication with a password.
- **Ban System**: Banned users are prevented from reconnecting.

## Project Structure
```
Stealth-Chat/
│── certs/                  # Contains SSL/TLS certificates and keys
│   ├── server.crt          # Server certificate
│   ├── server.key          # Server private key
│── data/                   # Contains banned users list
│   ├── bans.txt            # List of banned users
│── client.py               # Client-side script
│── server.py               # Server-side script
│── requirements.txt        # Required dependencies
│── README.md               # Documentation
|── PUBLIC_SERVER_SETUP.md  # Guide to deploy on a public server
```

## Prerequisites
Ensure you have Python installed (version 3.x or higher recommended). 
Install required dependencies using:
```sh
pip install -r requirements.txt
```

## Running the Server
Start the server using:
```sh
python server.py
```
The server listens on `127.0.0.1:54321` by default.

## Running the Client
Start the client using:
```sh
python client.py
```
Upon connection, the client will prompt for a nickname. If the nickname is `admin`, a password will be required. The default admin password is `password`.

## Admin Commands
Admin users can execute the following commands in the chat:
- `/kick <nickname>` - Remove a user from the chat.
- `/ban <nickname>` - Remove and ban a user from reconnecting.
- `/exit` - Disconnect from the server.
- `/` - Commands must start with a forward slash (`/`).

## Security Considerations
- **SSL/TLS Encryption**: Ensures all communication is secure.
- **Admin Authentication**: Prevents unauthorized access to admin functions.
- **Ban List**: Prevents banned users from reconnecting.

## License
This project is licensed under the MIT License.

## Author
Developed by Kunal Dharme.

