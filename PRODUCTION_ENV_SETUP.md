# Production Environment Setup for Coolify

## 🚨 CRITICAL: Your App Won't Work Without These Environment Variables

Your authentication is failing because Coolify doesn't have the required environment variables set.

## 📋 Environment Variables to Set in Coolify

**Go to: Coolify Dashboard → Your App → Environment Variables**

Copy and paste each of these variables:

### **Database Configuration**
```
DATABASE_URL=postgresql://postgres:levGakzw2E9IyxGS676Cm8VdIYbYmxRMV1TV6dWf6XkDxErMWXXfhGI543Ew1dPK@192.168.11.253:5444/postgresql-database-hr
```
**⚠️ IMPORTANT**: This uses your local PostgreSQL server. For production, consider using a cloud database accessible from internet.

### **Flask Configuration**
```
FLASK_ENV=production
SECRET_KEY=everlast-production-secret-key-2024-CHANGE-THIS
CSRF_SECRET=everlast-csrf-secret-key-2024-CHANGE-THIS
```

### **Server Configuration**
```
HOST=0.0.0.0
PORT=5000
DEBUG=False
```

### **Optional: Sync Agent (for biometric devices)**
```
SYNC_SECRET=everlast-sync-secret-key-2024
DEVICE_IP=192.168.11.253
DEVICE_PORT=4370
DEVICE_URL=http://192.168.11.253/
```

## 🗄️ Database Setup Options

### Option A: Create PostgreSQL in Coolify (Recommended)

1. **Coolify Dashboard** → **Services** → **Add Service**
2. Select **PostgreSQL**
3. Set database name: `everlast_erp`
4. Set username: `everlast_user`
5. Set password: `secure_password_123`
6. **Deploy the service**
7. **Copy the connection string** Coolify provides
8. **Use it as your DATABASE_URL**

Example connection string from Coolify:
```
DATABASE_URL=postgresql://everlast_user:secure_password_123@postgresql-service:5432/everlast_erp
```

### Option B: Use External Database

If you have AWS RDS, Google Cloud SQL, etc.:
```
DATABASE_URL=postgresql://user:pass@external-host:5432/dbname
```

## 🔧 Step-by-Step Fix

### 1. Set Environment Variables
- Go to **Coolify Dashboard**
- Click on your **EverLast ERP app**
- Go to **Environment Variables** tab
- Add each variable listed above
- Click **Save**

### 2. Create Database (if using Coolify PostgreSQL)
- Go to **Services** → **Add Service** → **PostgreSQL**
- Create the service
- Copy the connection string

### 3. Update DATABASE_URL
- Go back to your app's **Environment Variables**
- Update `DATABASE_URL` with the correct connection string
- **Save**

### 4. Redeploy
- Go to **Deployments** tab
- Click **Deploy** to restart with new environment variables

### 5. Test Login
- Visit your app URL
- Try login with: `admin@everlast.com` / `admin123`

## 🔍 Debugging

### Check App Logs
In Coolify Dashboard → Your App → **Logs**, look for:
- Database connection errors
- Missing environment variable warnings
- Authentication errors

### Test Health Endpoint
Visit: `https://your-app-domain/health`

Should show database connection status.

### Common Issues
- `connection refused` → Database not accessible
- `authentication failed` → Wrong database credentials
- `CSRF token missing` → CSRF_SECRET not set
- `Internal Server Error` → Check logs for details

## 🎯 Expected Result

After setting environment variables and redeploying:
1. ✅ App connects to database successfully
2. ✅ Login form processes correctly
3. ✅ Dashboard loads after authentication
4. ✅ No more loading loops

## 🔒 Security Notes

### Generate Strong Secrets
Replace the example secrets with strong values:
```bash
# Generate strong SECRET_KEY (run locally)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate strong CSRF_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Production Checklist
- [ ] Set strong SECRET_KEY and CSRF_SECRET
- [ ] Use cloud database (not local IP)
- [ ] Set FLASK_ENV=production
- [ ] Set DEBUG=False
- [ ] Test login functionality
- [ ] Verify /health endpoint works

## 🆘 Still Having Issues?

1. **Check Coolify app logs** for specific errors
2. **Verify all environment variables** are set correctly
3. **Test database connection** with /health endpoint
4. **Ensure database is accessible** from internet

Your app deployment is working perfectly - it just needs the environment variables to connect to a database and handle authentication properly!
