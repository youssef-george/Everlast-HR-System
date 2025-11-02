# EverLast ERP - Deployment Guide for Biometric Device Sync

## Problem Overview

After deploying your Flask HR attendance app to Coolify (or any cloud platform), biometric devices (ZKTeco) can no longer connect because:

- **Cloud servers are outside your internal LAN network**
- **Private IP ranges (192.168.x.x, 10.x.x.x, 172.x.x.x) are not accessible over the internet**
- **The Flask app in Coolify cannot directly reach local device IPs**

## Solution Architecture

```
Local Network (192.168.11.x)          Cloud (Coolify)
┌─────────────────────────┐           ┌──────────────────┐
│  ZKTeco Device          │           │                  │
│  192.168.11.253:4370    │           │  Flask App       │
│                         │           │  (PostgreSQL)    │
│  ZKTeco Device          │    HTTPS  │                  │
│  192.168.11.254:4370    │◄─────────►│  /api/sync_logs  │
│                         │           │                  │
│  Sync Agent (Python)    │           │                  │
│  - Connects to devices  │           │                  │
│  - Fetches logs         │           │                  │
│  - Uploads via API      │           │                  │
└─────────────────────────┘           └──────────────────┘
```

## Deployment Steps

### Step 1: Deploy Flask App to Coolify

1. **Push your code** to GitHub (already done)
2. **Deploy to Coolify** with these environment variables:

```env
# Database
DATABASE_URL=postgresql://postgres:your-password@host:port/database

# Flask
SECRET_KEY=your-production-secret-key
CSRF_SECRET=your-production-csrf-secret
FLASK_ENV=production

# Sync Agent Authentication
SYNC_SECRET=everlast-sync-secret-key-2024-change-in-production

# Disable direct device connections in production
ENABLE_DIRECT_DEVICE_SYNC=false
```

3. **Verify deployment** - your app should be accessible at your Coolify domain

### Step 2: Set Up Local Sync Agent

1. **On a computer in your office network** (same LAN as biometric devices):

```bash
# Clone the repository
git clone https://github.com/youssef-george/Everlast-HR-System.git
cd Everlast-HR-System/sync_agent

# Install Python dependencies
pip install -r requirements.txt

# Copy and configure
cp config.example.ini config.ini
```

2. **Edit `config.ini`** with your settings:

```ini
[server]
url = https://your-everlast-app.coolify.domain
sync_secret = everlast-sync-secret-key-2024-change-in-production

[sync]
interval_minutes = 5
batch_size = 100
max_retries = 3

[device_ground_floor]
name = Ground Floor Device
ip = 192.168.11.253
port = 4370
enabled = true

[device_upper_floor]
name = Upper Floor Device
ip = 192.168.11.254
port = 4370
enabled = true
```

3. **Test the setup**:

```bash
# Test server connection
python attendance_sync_agent.py --test

# Run sync once
python attendance_sync_agent.py --once
```

4. **Run continuously**:

```bash
# Run with scheduler
python attendance_sync_agent.py

# Or run in background
nohup python attendance_sync_agent.py > sync_agent.log 2>&1 &
```

### Step 3: Verify Everything Works

1. **Check sync agent logs**:
```bash
tail -f sync_agent.log
```

2. **Check Flask app logs** in Coolify dashboard

3. **Test attendance** - have someone use the biometric device and verify it appears in your web dashboard within 5 minutes

## Security Considerations

### HMAC Authentication
- All API requests are signed with HMAC-SHA256
- Sync secret must match between agent and server
- Invalid signatures are rejected and logged

### Network Security
- Agent only makes outbound HTTPS connections
- No inbound ports need to be opened
- Biometric devices remain on local network only

### Data Protection
- Attendance logs are encrypted in transit (HTTPS)
- PostgreSQL database is password protected
- Sensitive configuration in environment variables

## Monitoring & Maintenance

### Log Monitoring
- **Sync Agent**: `sync_agent.log` on local computer
- **Flask App**: Coolify dashboard logs
- **Database**: PostgreSQL logs (if needed)

### Health Checks
- Agent tests server connection on startup
- Failed syncs are retried automatically
- Errors are logged with details

### Regular Maintenance
- Monitor disk space for log files
- Update sync agent if needed
- Backup PostgreSQL database regularly

## Troubleshooting

### Common Issues

**1. "Connection failed" to devices**
```bash
# Test device connectivity
ping 192.168.11.253
telnet 192.168.11.253 4370
```

**2. "Invalid signature" errors**
- Verify SYNC_SECRET matches in both agent config and Flask app environment
- Check for extra spaces or characters in the secret

**3. "User not found" errors**
- Ensure user IDs from devices match user IDs in your database
- Check device user enrollment

**4. Sync agent stops running**
- Check `sync_agent.log` for error messages
- Restart the agent: `python attendance_sync_agent.py`
- Consider running as a system service

### Testing Individual Components

**Test device connection:**
```python
from zk import ZK
zk = ZK('192.168.11.253', port=4370, timeout=30)
conn = zk.connect()
print("Connected successfully!")
conn.disconnect()
```

**Test server API:**
```bash
curl -X POST https://your-app.coolify.domain/api/sync_logs \
  -H "Content-Type: application/json" \
  -H "X-Sync-Signature: test" \
  -d '{"test": true}'
```

## Alternative Solutions

### Option 1: VPN Tunnel
Set up WireGuard VPN between Coolify server and your office:
- More complex setup
- Requires VPN configuration on both ends
- Direct device access from cloud

### Option 2: Reverse Proxy
Use ngrok or Cloudflare Tunnel:
- Exposes local devices to internet
- Security concerns
- Additional service dependency

### Option 3: Hybrid Approach
Keep some processing local, sync summaries only:
- Process attendance locally
- Send daily summaries to cloud
- Reduced real-time visibility

## Recommended: Sync Agent Approach

The sync agent approach is recommended because:
- ✅ Simple setup and maintenance
- ✅ Secure (no inbound connections)
- ✅ Reliable (handles network issues)
- ✅ Scalable (easy to add more devices)
- ✅ No complex networking required

## Support

For deployment assistance:
1. Check logs first (both agent and Flask app)
2. Verify network connectivity to devices
3. Test API authentication
4. Contact system administrator if needed

---

**Next Steps:**
1. Deploy Flask app to Coolify with proper environment variables
2. Set up sync agent on local network computer
3. Test end-to-end functionality
4. Set up monitoring and alerts
5. Document any customizations for your environment
