# Dual Database Setup Guide

This guide explains how to set up and use the dual database system with SQLite (primary) and PostgreSQL (sync target) for your Flask ERP application.

## Overview

The dual database setup provides:
- **SQLite** as the primary database for fast local operations
- **PostgreSQL** as the secondary database for production/cloud deployment
- **Real-time synchronization** between both databases
- **Automatic migration** tools to move data from SQLite to PostgreSQL
- **Seamless transition** from development to production

## Prerequisites

1. **Python packages** (add to requirements.txt):
```txt
psycopg2-binary>=2.9.0
sqlalchemy>=1.4.0
flask-sqlalchemy>=3.0.0
```

2. **PostgreSQL database** (already set up on Coolify):
- Host: `196.219.160.253`
- Port: `5444`
- Database: `postgres`
- Username: `postgres`
- Password: `1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq`

## Configuration

### 1. Environment Variables

Create or update your `.env` file:

```env
# Primary Database (SQLite)
SQLITE_DATABASE_URL=sqlite:///instance/everlast.db

# PostgreSQL Database (Coolify)
POSTGRES_DATABASE_URL=postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require

# Sync Configuration
ENABLE_DB_SYNC=true
SYNC_BATCH_SIZE=100
SYNC_RETRY_ATTEMPTS=3
SYNC_RETRY_DELAY=5

# Flask Configuration
SECRET_KEY=your-secret-key-here
CSRF_SECRET=your-csrf-secret-here
```

### 2. Updated Configuration Files

The following files have been updated:

- **`config.py`**: Dual database configuration
- **`app.py`**: Sync service initialization
- **`sync_service.py`**: Real-time synchronization service
- **`db_helpers.py`**: Helper functions for database operations
- **`migrate_sqlite_to_postgres.py`**: Migration script

## Installation Steps

### 1. Install Required Packages

```bash
pip install psycopg2-binary
```

### 2. Test Database Connections

```bash
python test_dual_database_setup.py
```

This will test:
- SQLite connection
- PostgreSQL connection
- Sync service functionality
- CRUD operations with sync

### 3. Run Initial Migration

```bash
# Test migration (dry run)
python migrate_sqlite_to_postgres.py --dry-run

# Run full migration
python migrate_sqlite_to_postgres.py --batch-size 1000

# Run migration with cleanup (CAUTION: deletes existing PostgreSQL data)
python migrate_sqlite_to_postgres.py --cleanup --batch-size 1000
```

### 4. Start Your Flask Application

```bash
python app.py
```

The application will now use SQLite as primary and sync to PostgreSQL automatically.

## Usage Examples

### Basic Operations with Sync

```python
from db_helpers import DatabaseManager, create_user, create_attendance_record

# Create a user (automatically synced to PostgreSQL)
user = create_user(
    first_name="John",
    last_name="Doe",
    email="john@example.com",
    password_hash="hashed_password",
    role="employee"
)

# Create attendance record (automatically synced)
attendance = create_attendance_record(
    employee_id=str(user.id),
    timestamp=datetime.now(),
    status="check_in",
    device_id="DEVICE_001"
)

# Update user (automatically synced)
from db_helpers import update_user
update_user(user, phone_number="123-456-7890")
```

### Batch Operations (Without Sync)

```python
from db_helpers import BatchOperationContext, DatabaseManager
from models import User

# Batch create without triggering sync for each record
with BatchOperationContext():
    users_data = [
        {"first_name": "Alice", "last_name": "Smith", "email": "alice@example.com", "password_hash": "hash1", "role": "employee"},
        {"first_name": "Bob", "last_name": "Johnson", "email": "bob@example.com", "password_hash": "hash2", "role": "manager"}
    ]
    
    created_users = DatabaseManager.bulk_create_records(User, users_data)
    print(f"Created {len(created_users)} users in batch")

# Sync will be re-enabled automatically after the context
```

### Manual Sync Control

```python
from db_helpers import DatabaseManager

# Check sync status
status = DatabaseManager.get_sync_status()
print(f"Sync enabled: {status['sync_enabled']}")

# Temporarily disable sync
DatabaseManager.disable_sync()

# Perform operations without sync
user = create_user(first_name="Test", last_name="User", email="test@example.com")

# Re-enable sync
DatabaseManager.enable_sync()

# Manually sync a record
from sync_service import sync_model_to_postgres
sync_model_to_postgres(user, 'insert')
```

## Monitoring and Health Checks

### Health Check Endpoint

Visit `http://localhost:5000/health` to check:
- Primary database connection
- PostgreSQL connection status
- Sync service status
- Connection pool information

### Log Monitoring

Check application logs for sync status:
```bash
tail -f flask_error.log | grep -i sync
```

## Migration Process

### Phase 1: Dual Database Setup (Current)
- SQLite remains primary database
- PostgreSQL receives real-time sync
- Both databases stay in sync

### Phase 2: Verification Period
- Monitor sync for stability
- Verify data consistency
- Test PostgreSQL performance

### Phase 3: Production Switch
- Update `config.py` to use PostgreSQL as primary
- Disable sync service
- Remove SQLite dependency

## Troubleshooting

### Common Issues

1. **PostgreSQL Connection Failed**
   ```bash
   # Test connection manually
   python -c "
   import psycopg2
   conn = psycopg2.connect('postgresql://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require')
   print('Connection successful')
   conn.close()
   "
   ```

2. **Sync Not Working**
   - Check `ENABLE_DB_SYNC` environment variable
   - Verify PostgreSQL connection
   - Check application logs for sync errors

3. **Migration Errors**
   - Check table dependencies
   - Verify data types compatibility
   - Use `--batch-size` parameter for large datasets

### Debug Commands

```bash
# Test connections only
python migrate_sqlite_to_postgres.py --dry-run

# Run comprehensive tests
python test_dual_database_setup.py

# Check sync service status
python -c "
from app import create_app
from sync_service import sync_service
app = create_app()
with app.app_context():
    print('Sync enabled:', sync_service.sync_enabled)
    print('PostgreSQL connected:', sync_service.test_postgres_connection())
"
```

## Performance Considerations

1. **Sync Performance**
   - Batch operations use `BatchOperationContext` to avoid individual syncs
   - Sync happens asynchronously after SQLite commit
   - Failed syncs are retried with exponential backoff

2. **Connection Pooling**
   - PostgreSQL uses connection pooling for efficiency
   - SQLite uses file-based connection with timeout handling

3. **Error Handling**
   - Sync failures don't affect primary operations
   - Failed syncs are logged for manual recovery
   - Retry mechanism handles temporary connection issues

## Security Notes

1. **Database Credentials**
   - Store PostgreSQL credentials in environment variables
   - Use SSL connections (`sslmode=require`)
   - Rotate passwords regularly

2. **Network Security**
   - PostgreSQL connection uses SSL encryption
   - Consider VPN for additional security in production

## Next Steps

1. **Test the setup** using the provided test script
2. **Run the migration** to copy existing data
3. **Monitor sync performance** during normal operations
4. **Plan the production switch** after verification period

## Support Files

- `config.py` - Database configuration
- `sync_service.py` - Synchronization service
- `db_helpers.py` - Helper functions
- `migrate_sqlite_to_postgres.py` - Migration script
- `test_dual_database_setup.py` - Test suite
- `enhanced_sync_service.py` - Advanced sync features

For questions or issues, check the application logs and use the provided test scripts to diagnose problems.

