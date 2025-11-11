# EverLast ERP - Local Network Deployment Guide

This guide will help you deploy the EverLast ERP application on your local network so it can be accessed from all devices on the same network.

## Quick Start

### Option 1: Using the Deployment Script (Recommended)

1. **Run the deployment script:**
   ```bash
   python deploy_local_network.py
   ```

2. The script will:
   - Show your local IP address(es)
   - Display network access URLs
   - Optionally configure Windows Firewall
   - Start the server

### Option 2: Manual Deployment

1. **Start the application:**
   ```bash
   python app.py
   ```
   or
   ```bash
   python run.py
   ```

2. **Find your local IP address:**
   - Windows: Open Command Prompt and run `ipconfig`
   - Look for "IPv4 Address" under your active network adapter
   - Usually something like `192.168.x.x` or `10.x.x.x`

3. **Access from other devices:**
   - On the same network, open a browser and go to:
     ```
     http://YOUR_IP_ADDRESS:5000
     ```
   - Replace `YOUR_IP_ADDRESS` with the IP address you found

## Configuration

### Port Configuration

The default port is **5000**. You can change it by:

1. **Using environment variable:**
   ```bash
   set PORT=8080
   python app.py
   ```

2. **Or modify `config.py`:**
   ```python
   PORT = 8080  # Change to your desired port
   ```

### Host Configuration

The app is already configured to listen on `0.0.0.0`, which means it accepts connections from all network interfaces. This is set in:
- `app.py` line 499: `app.run(debug=True, host='0.0.0.0', port=port)`
- `run.py` line 22: `host='0.0.0.0'`

## Firewall Configuration

### Windows Firewall

#### Automatic Configuration (Requires Admin)
Run the deployment script as Administrator:
```bash
# Right-click Command Prompt/PowerShell and select "Run as Administrator"
python deploy_local_network.py
```

#### Manual Configuration

1. **Open Windows Firewall:**
   - Press `Win + R`
   - Type `wf.msc` and press Enter

2. **Add Inbound Rule:**
   - Click "Inbound Rules" → "New Rule"
   - Select "Port" → Next
   - Select "TCP" and enter port `5000` (or your custom port)
   - Select "Allow the connection" → Next
   - Check all profiles (Domain, Private, Public) → Next
   - Name it "EverLast ERP" → Finish

3. **Or use Command Prompt (as Administrator):**
   ```cmd
   netsh advfirewall firewall add rule name="EverLast ERP" dir=in action=allow protocol=TCP localport=5000
   ```

### Linux Firewall (iptables)

```bash
sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
sudo iptables-save
```

### macOS Firewall

1. System Preferences → Security & Privacy → Firewall
2. Click "Firewall Options"
3. Click "+" and add Python or Terminal
4. Allow incoming connections

## Network Requirements

1. **Same Network:**
   - All devices must be on the same local network (same router/switch)
   - Devices can be connected via WiFi or Ethernet

2. **No VPN:**
   - Disable VPN on the server machine if it's interfering

3. **Router Configuration:**
   - Usually no configuration needed
   - Some routers may block local network traffic (rare)

## Troubleshooting

### Cannot Access from Other Devices

1. **Check Firewall:**
   - Ensure Windows Firewall allows port 5000
   - Try temporarily disabling firewall to test

2. **Verify IP Address:**
   - Make sure you're using the correct local IP
   - Run `ipconfig` (Windows) or `ifconfig` (Linux/Mac) to verify

3. **Check Network:**
   - Ensure all devices are on the same network
   - Try pinging the server IP from another device:
     ```bash
     ping YOUR_SERVER_IP
     ```

4. **Verify Server is Running:**
   - Check that the server is actually running
   - Look for "Running on http://0.0.0.0:5000" in the console

5. **Check Port:**
   - Verify the port is not blocked by another application
   - Try changing to a different port (e.g., 8080)

### Connection Timeout

- Check if antivirus is blocking the connection
- Verify the server machine's network adapter is active
- Try accessing from the server machine itself first: `http://localhost:5000`

### "Connection Refused" Error

- Server might not be running
- Wrong IP address
- Port is blocked by firewall
- Server is only listening on localhost (should be 0.0.0.0)

## Security Considerations

⚠️ **Important:** When deploying on a local network:

1. **Development Mode:**
   - The app runs in debug mode (`debug=True`)
   - This is fine for local network testing
   - **Do NOT expose to the internet** without proper security

2. **Production Deployment:**
   - For production, use a proper WSGI server (Gunicorn, uWSGI)
   - Set `debug=False`
   - Use HTTPS with SSL certificates
   - Implement proper authentication and authorization

3. **Network Security:**
   - Ensure your local network is secure
   - Use strong passwords for user accounts
   - Consider VPN for remote access instead of exposing to internet

## Testing Network Access

1. **From Server Machine:**
   ```
   http://localhost:5000
   http://127.0.0.1:5000
   ```

2. **From Other Devices:**
   ```
   http://SERVER_IP_ADDRESS:5000
   ```

3. **Find Server IP:**
   - Windows: `ipconfig` → Look for IPv4 Address
   - Linux/Mac: `ifconfig` or `ip addr`

## Example Network Setup

```
Router (192.168.1.1)
  ├── Server PC (192.168.1.100) ← Running EverLast ERP
  ├── Laptop (192.168.1.101) ← Can access http://192.168.1.100:5000
  ├── Phone (192.168.1.102) ← Can access http://192.168.1.100:5000
  └── Tablet (192.168.1.103) ← Can access http://192.168.1.100:5000
```

## Production Deployment

For production use, consider:

1. **Use a Production WSGI Server:**
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

2. **Use a Reverse Proxy (Nginx):**
   - Better performance and security
   - SSL/TLS termination
   - Load balancing

3. **Environment Variables:**
   - Set `FLASK_ENV=production`
   - Use proper secret keys
   - Configure database properly

## Support

If you encounter issues:
1. Check the server console for error messages
2. Verify firewall settings
3. Test network connectivity with `ping`
4. Check that the port is not in use by another application

---

**Note:** This deployment is for local network access only. For internet access, you need proper security measures, domain name, and SSL certificates.
