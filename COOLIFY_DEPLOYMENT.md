# EverLast ERP - Coolify Deployment Guide

## 🚨 Login Loading Issue - SOLUTION

### **Root Cause**
Your login page loads but gets stuck because:
1. **Database connection fails** (local IP not accessible from cloud)
2. **Missing production environment variables**
3. **No users in database**

## 🔧 **IMMEDIATE FIX**

### **Step 1: Set Environment Variables in Coolify**

Go to your Coolify dashboard → Your App → Environment Variables and set:

```env
# CRITICAL: Database Connection (MUST CHANGE)
DATABASE_URL=postgresql://username:password@your-cloud-db-host:5432/database-name

# Flask Production Configuration
FLASK_ENV=production
SECRET_KEY=your-super-secure-secret-key-change-this-now
CSRF_SECRET=your-csrf-secret-key-change-this-now

# Server Configuration
HOST=0.0.0.0
PORT=5000

# Optional: Sync Agent
SYNC_SECRET=everlast-sync-secret-key-2024
```

### **Step 2: Database Options**

**Option A: Use Coolify's PostgreSQL Service**
1. In Coolify dashboard → Add Service → PostgreSQL
2. Create database named `everlast-erp`
3. Use the connection string Coolify provides

**Option B: Use External PostgreSQL**
If you have a cloud PostgreSQL service (AWS RDS, Google Cloud SQL, etc.):
```env
DATABASE_URL=postgresql://user:pass@your-cloud-host:5432/dbname
```

**Option C: Use Your Local PostgreSQL (NOT RECOMMENDED for production)**
If you must use your local server, you'd need to:
- Set up VPN or port forwarding
- Make your local PostgreSQL accessible from internet
- Use your public IP instead of 192.168.11.253

### **Step 3: Create Database Tables**

After setting the correct DATABASE_URL, your app needs to create tables:

**Option A: Add this to your deployment script**
```bash
flask db upgrade
```

**Option B: Create tables on first run**
The app will auto-create tables when it starts.

### **Step 4: Create Admin User**

Add this to your app startup or run once:
```python
# This creates: admin@everlast.com / admin123
python check_users.py
```

## 🔍 **Debugging Steps**

### **1. Check Coolify Logs**
In Coolify dashboard → Your App → Logs, look for:
- Database connection errors
- Missing environment variable warnings
- Login attempt logs

### **2. Test Database Connection**
Add this health check endpoint (already exists):
```
https://your-app.coolify.domain/health
```

### **3. Common Error Messages**
- `connection refused` → Database not accessible
- `authentication failed` → Wrong database credentials
- `CSRF token missing` → CSRF configuration issue
- `Internal Server Error` → Check Coolify logs

## 🎯 **Quick Test**

1. **Set environment variables** in Coolify
2. **Redeploy** your app
3. **Check logs** for database connection success
4. **Try login** with:
   - Email: `admin@everlast.com`
   - Password: `admin123`

## 🔒 **Security Notes**

### **IMPORTANT: Change Default Credentials**
After first login, immediately:
1. Change admin password
2. Update SECRET_KEY and CSRF_SECRET
3. Create proper user accounts

### **Production Environment Variables**
```env
# Generate strong secrets
SECRET_KEY=your-256-bit-secret-key-here
CSRF_SECRET=your-csrf-secret-key-here

# Use production database
DATABASE_URL=postgresql://user:pass@cloud-host:5432/db

# Production settings
FLASK_ENV=production
DEBUG=False
```

## 📋 **Deployment Checklist**

- [ ] Set DATABASE_URL to accessible cloud database
- [ ] Set FLASK_ENV=production
- [ ] Set strong SECRET_KEY and CSRF_SECRET
- [ ] Set HOST=0.0.0.0
- [ ] Create database tables
- [ ] Create admin user
- [ ] Test login functionality
- [ ] Check application logs
- [ ] Verify /health endpoint

## 🆘 **Still Having Issues?**

1. **Check Coolify logs** first
2. **Verify database connection** with /health endpoint
3. **Test with curl**:
   ```bash
   curl -X POST https://your-app.coolify.domain/auth/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "email=admin@everlast.com&password=admin123"
   ```

## 📞 **Support**

If login still fails after following this guide:
1. Share Coolify application logs
2. Confirm environment variables are set
3. Test /health endpoint response
4. Check database accessibility

---

**Next Steps After Login Works:**
1. Set up proper user accounts
2. Configure sync agent for biometric devices
3. Import existing data if needed
4. Set up monitoring and backups
