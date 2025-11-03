# PostgreSQL as Primary Database - Setup Guide

## Overview
This document explains how the Everlast ERP system is now configured to use **PostgreSQL as the primary database** instead of SQLite.

## Configuration Changes

### 1. Environment Variables (.env)
```bash
# PostgreSQL as Primary Database
DATABASE_URL=postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require

# Optional (fallback if DATABASE_URL not set)
POSTGRES_DATABASE_URL=postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require

# Database sync is DISABLED (PostgreSQL is primary)
ENABLE_DB_SYNC=false
```

### 2. config.py Changes
- `SQLALCHEMY_DATABASE_URI` now points to PostgreSQL
- `DATABASE_URL` environment variable takes precedence
- SQLite is only used for migration purposes (backup)
- Database sync service is **disabled** (no longer needed)

### 3. app.py Changes
- Sync service initialization is **disabled**
- All database operations now go directly to PostgreSQL
- No dual-database logic

## Migration Steps

### Step 1: Run Migration Script
Migrate all existing data from SQLite to PostgreSQL:

```bash
python migrate_to_postgres_primary.py
```

This script will:
- Create all tables in PostgreSQL
- Migrate all data from SQLite to PostgreSQL
- Skip duplicates (using ON CONFLICT DO NOTHING)
- Verify record counts match
- Generate a detailed migration log

### Step 2: Verify Migration
After migration, verify data:

```bash
python check_data_sync.py
```

Or manually check in PostgreSQL:
```sql
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM attendance_logs;
SELECT COUNT(*) FROM daily_attendance;
-- etc.
```

### Step 3: Restart Application
After migration, restart your Flask application:

```bash
python run.py
```

Check logs to confirm:
- "Primary DB: PostgreSQL"
- Database connection is to PostgreSQL (not SQLite)

### Step 4: Test New Data
1. Create a new attendance log or user
2. Verify it appears in PostgreSQL:
   ```sql
   SELECT * FROM attendance_logs ORDER BY timestamp DESC LIMIT 5;
   ```
3. Confirm NO new data appears in SQLite

## Architecture

### Before (Dual Database)
```
SQLite (Primary) → Sync Service → PostgreSQL (Secondary)
```

### After (PostgreSQL Primary)
```
PostgreSQL (Primary) ← All Operations
```

## Key Benefits

1. **Single Source of Truth**: PostgreSQL is now the only database
2. **Real-Time Updates**: All changes appear immediately in PostgreSQL
3. **No Sync Overhead**: No sync service needed
4. **Better Performance**: PostgreSQL handles concurrent connections better
5. **Scalability**: PostgreSQL can handle larger datasets and more concurrent users

## Verification Checklist

- [ ] Migration script completed successfully
- [ ] Record counts match between SQLite and PostgreSQL
- [ ] Application starts and connects to PostgreSQL
- [ ] New records appear in PostgreSQL
- [ ] No new records appear in SQLite
- [ ] All routes/dashboards read from PostgreSQL
- [ ] Reports reflect PostgreSQL data
- [ ] Health check endpoint shows PostgreSQL connection

## Troubleshooting

### Issue: "No such table" errors
**Solution**: Run migration script to create tables:
```bash
python migrate_to_postgres_primary.py
```

### Issue: Connection refused
**Solution**: Check:
- PostgreSQL server is running
- Connection string is correct
- Network/firewall allows connection
- SSL settings are correct

### Issue: Migration fails for some tables
**Solution**: 
- Check migration log for details
- Fix schema issues (like boolean type mismatches)
- Re-run migration for specific tables

### Issue: Application still uses SQLite
**Solution**:
- Check `DATABASE_URL` environment variable
- Verify `config.py` uses `DATABASE_URL`
- Restart application
- Check logs for database connection info

## Rollback (if needed)

If you need to rollback to SQLite:
1. Restore old `config.py` (before PostgreSQL changes)
2. Set `SQLALCHEMY_DATABASE_URI` back to SQLite path
3. Restart application

## Support

For issues or questions:
1. Check application logs
2. Review migration log file
3. Verify environment variables
4. Test PostgreSQL connection: `python test_postgres_connection.py`

