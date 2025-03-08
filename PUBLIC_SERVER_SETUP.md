# Deploying Stealth-Chat to a Public Server

This guide explains how to modify your Stealth-Chat application to work over the public internet instead of localhost.

## 1. Configure the Server for Public Access
By default, the server listens on `127.0.0.1` (localhost), which only allows local connections. To allow public connections:

- Open `server.py`
- Change the `host` variable from `127.0.0.1` to `0.0.0.0`:

```python
host = '0.0.0.0'  # Allow external connections
port = 54321
```

This makes the server listen on all available network interfaces.

## 2. Set Up a Public IP or Domain
If running on a cloud service (e.g., AWS, DigitalOcean, or a VPS):
- Obtain the public IP address assigned to your server.
- (Optional) Set up a domain name and configure DNS to point to your server's IP.

## 3. Configure Firewall and Port Forwarding
Ensure port `54321` is open for incoming connections:

- **Linux (UFW Firewall)**:
  ```sh
  sudo ufw allow 54321/tcp
  ```
- **Windows Firewall**:
  - Open `Windows Defender Firewall`
  - Add a new inbound rule to allow connections on port `54321`.
- **Router Port Forwarding** (for home-hosted servers):
  - Log into your router settings.
  - Forward TCP port `54321` to your local server's private IP address.

## 4. Update the Client to Connect to the Public Server
In `client.py`, change:
```python
secure_client.connect(('127.0.0.1', 54321))
```
To:
```python
secure_client.connect(('your-public-ip-or-domain', 54321))
```
Replace `your-public-ip-or-domain` with your server’s public IP or domain.

## 5. Use a Valid SSL Certificate
The current setup uses self-signed certificates, which may cause security warnings. For public deployment, get a certificate from [Let's Encrypt](https://letsencrypt.org/):
```sh
sudo apt install certbot
sudo certbot certonly --standalone -d yourdomain.com
```
Update `server.py` to use the new certificate and key files.

## 6. Run the Server Permanently
Use `tmux` or `screen` to keep the server running in the background:
```sh
nohup python server.py &
```
Or create a systemd service for automatic startup.

## 7. Secure the Server
- Use strong passwords.
- Regularly update the system (`sudo apt update && sudo apt upgrade`).
- Restrict access using firewall rules.

Now your chat server is accessible over the internet!