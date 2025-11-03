# PostgreSQL Sync Guarantee

## Overview
This document explains how the sync service ensures **ALL changes** (inserts, updates, and deletes) are synchronized from SQLite to PostgreSQL.

## What Gets Synced

### ✅ **Inserts** (New Records)
- All new records created through `db.session.add()` and `db.session.commit()`
- Captured in `before_flush` event listener
- Synced to PostgreSQL in `after_commit` event listener
- Automatic handling of duplicate keys (updates instead)

### ✅ **Updates** (Modified Records)
- All records modified through attribute changes and `db.session.commit()`
- Captured as "dirty" records in `before_flush` event listener
- Only changed fields are updated in PostgreSQL
- If record doesn't exist in PostgreSQL, it's inserted instead

### ✅ **Deletes** (Removed Records)
- All records deleted through `db.session.delete()` and `db.session.commit()`
- Captured in `before_flush` event listener
- Deleted from PostgreSQL in proper order (before updates/inserts to avoid foreign key issues)

## How It Works

### 1. **Event Listeners**
The sync service uses SQLAlchemy event listeners:
- `before_flush`: Captures all changes (new, dirty, deleted) before they're committed to SQLite
- `after_commit`: Syncs captured changes to PostgreSQL after successful SQLite commit
- `after_rollback`: Clears pending changes if SQLite transaction rolls back

### 2. **Change Order**
Changes are processed in the correct order:
1. **Deletes first** - Avoids foreign key constraint violations
2. **Updates second** - Ensures parent records exist before child records
3. **Inserts last** - All dependencies are in place

### 3. **Error Handling**
- Individual record sync failures don't stop the entire sync
- Errors are logged but sync continues for other records
- Detailed error messages help identify issues

### 4. **Commit Guarantee**
- All changes are committed in a single PostgreSQL transaction
- If any change fails, the entire sync is rolled back and retried
- Dual commit ensures both databases are consistent

## Verification

### Check Sync Status
Run the diagnostic script:
```bash
python diagnose_sync_issue.py
```

### Check Application Logs
Look for messages like:
- `"Captured new [table] record for sync"`
- `"Syncing X changes to PostgreSQL: Y inserts, Z updates, W deletes"`
- `"Successfully synced X changes to PostgreSQL"`

### Verify in PostgreSQL
```python
# Count records
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM departments;
# etc.
```

## Important Notes

1. **Sync is Automatic**: No manual intervention needed - all changes sync automatically
2. **Transaction Safety**: Changes only sync if SQLite commit succeeds
3. **Idempotent**: Sync can be safely repeated (handles duplicates)
4. **Thread-Safe**: Multiple concurrent changes are properly synchronized

## Troubleshooting

If records aren't syncing:

1. **Check sync is enabled**:
   - Environment variable: `ENABLE_DB_SYNC=true`
   - Or check logs: `"Sync Enabled: True"`

2. **Check PostgreSQL connection**:
   - Environment variable: `POSTGRES_DATABASE_URL`
   - Test connection: `python test_postgres_connection.py`

3. **Check application logs** for sync errors:
   - Look for `"Failed to sync"` messages
   - Check for connection errors

4. **Verify tables exist in PostgreSQL**:
   - Run: `python diagnose_sync_issue.py`
   - If tables are missing, run: `python migrate_sqlite_to_postgres.py`

## Performance

- Sync happens **asynchronously** after SQLite commit (doesn't slow down your app)
- Batch processing ensures efficient syncing
- Connection pooling minimizes overhead

