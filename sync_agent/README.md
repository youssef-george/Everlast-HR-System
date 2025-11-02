# EverLast ERP - Local Attendance Sync Agent

This sync agent runs on your local network to connect to biometric devices and sync attendance logs to your cloud-deployed EverLast ERP application.

## Problem Solved

After deploying your Flask app to Coolify (or any cloud platform), the app can no longer directly connect to biometric devices on your local network (192.168.x.x IPs) because:

- Cloud servers are outside your internal LAN
- Private IP ranges are not accessible over the internet
- Direct device connections fail in production

## Solution

This sync agent runs locally and:
1. Connects to your ZKTeco biometric devices on the LAN
2. Fetches attendance logs every few minutes
3. Securely uploads them to your cloud app via API
4. Handles errors, retries, and logging

## Setup Instructions

### 1. Install Python Dependencies

```bash
cd sync_agent
pip install -r requirements.txt
```

### 2. Configure the Agent

```bash
# Copy example configuration
cp config.example.ini config.ini

# Edit configuration with your settings
nano config.ini
```

Update the configuration:
- `server.url`: Your deployed app URL (e.g., https://your-app.coolify.domain)
- `server.sync_secret`: Must match SYNC_SECRET in your Flask app
- Device sections: Add your biometric device IPs

### 3. Test Connection

```bash
# Test server connection
python attendance_sync_agent.py --test

# Run sync once to test
python attendance_sync_agent.py --once
```

### 4. Run Continuously

```bash
# Run with scheduler (recommended)
python attendance_sync_agent.py

# Or run in background
nohup python attendance_sync_agent.py > sync_agent.log 2>&1 &
```

## Configuration Options

### Server Settings
- `url`: Your deployed Flask app URL
- `sync_secret`: Authentication secret (must match Flask app)

### Sync Settings
- `interval_minutes`: How often to sync (default: 5 minutes)
- `batch_size`: Max logs per batch (default: 100)
- `max_retries`: Retry attempts for failed syncs (default: 3)

### Device Settings
Each device needs a `[device_NAME]` section:
- `name`: Display name for the device
- `ip`: Device IP address (e.g., 192.168.11.253)
- `port`: Device port (usually 4370)
- `timeout`: Connection timeout in seconds
- `password`: Device password (if required)
- `enabled`: true/false to enable/disable device

## Security

- Uses HMAC-SHA256 signatures for API authentication
- Sync secret must be kept secure and match between agent and server
- All communication is over HTTPS
- Failed authentication attempts are logged

## Monitoring

The agent logs all activities to:
- Console output (when running interactively)
- `sync_agent.log` file

Log levels include:
- INFO: Normal operations, sync results
- WARNING: Non-critical issues (device temporarily unavailable)
- ERROR: Serious issues (authentication failures, network errors)

## Troubleshooting

### Connection Issues
1. Check device IP addresses and network connectivity
2. Verify devices are powered on and accessible
3. Test with device management software first

### Authentication Issues
1. Verify sync_secret matches between agent and Flask app
2. Check server URL is correct and accessible
3. Ensure Flask app has the /api/sync_logs endpoint

### Sync Issues
1. Check logs for specific error messages
2. Verify user IDs exist in the Flask app database
3. Check timestamp formats are correct

## Running as a Service

### Linux (systemd)

Create `/etc/systemd/system/everlast-sync.service`:

```ini
[Unit]
Description=EverLast ERP Sync Agent
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/sync_agent
ExecStart=/usr/bin/python3 attendance_sync_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable everlast-sync
sudo systemctl start everlast-sync
sudo systemctl status everlast-sync
```

### Windows

Use Task Scheduler or install as a Windows service using tools like NSSM.

## Alternative: VPN Solution

If you prefer direct device access, you can set up a VPN:

1. **WireGuard VPN**: Create a VPN tunnel between your Coolify server and local network
2. **Site-to-Site VPN**: Connect your cloud provider to your office network
3. **Reverse Proxy**: Use tools like ngrok or Cloudflare Tunnel

However, the sync agent approach is more reliable and doesn't require complex networking.

## Support

For issues or questions:
1. Check the logs first (`sync_agent.log`)
2. Verify configuration settings
3. Test individual components (device connection, server connection)
4. Contact your system administrator
