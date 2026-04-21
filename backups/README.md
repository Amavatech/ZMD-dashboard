# Database Backup

## Current Backup

**Created:** February 5, 2026 19:24:05 UTC
**Database:** mqtt_dashboard
**Format:** PostgreSQL SQL dump (compressed)

### Backup Files

1. **`mqtt_dashboard_complete_20260205_192405.sql.gz`** (9.8 MB)
   - Complete database backup including:
     - All schemas and table structures
     - All TimescaleDB hypertables and chunks
     - All data in all tables
     - Users, groups, permissions
     - Timestream tables and measurements
     - All weather data
   
2. **`mqtt_dashboard_metadata_20260205_192405.sql.gz`** (114 KB)
   - Configuration tables only:
     - timestream_tables (333 topics)
     - timestream_measurements (17,807 measurements)
     - users (56 users)
     - groups (6 groups)
     - permissions
     - weather_data

### Database Contents

- **Topics:** 333 timestream tables
- **Measurements:** 17,807 time series measurements
- **Users:** 56 user accounts
- **Groups:** 6 permission groups
- **Data Tables:** 60+ hypertables with chunks

### What's Included

✅ **Schema:** All table definitions, indexes, constraints
✅ **TimescaleDB:** Hypertable configurations and chunk data
✅ **Data:** All historical weather data
✅ **Users:** User accounts and authentication
✅ **Configuration:** Topics, measurements, permissions
✅ **Grafana Links:** Dashboard UIDs and settings

## Restore Instructions

### Full Database Restore

To restore the complete database (WARNING: This will overwrite existing data):

```bash
cd /home/ubuntu/mqtt_dashboard/backups

# 1. Uncompress the backup
gunzip mqtt_dashboard_complete_20260205_192405.sql.gz

# 2. Drop existing database (optional, if you want clean restore)
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS mqtt_dashboard;"
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -c "CREATE DATABASE mqtt_dashboard;"

# 3. Restore the backup
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard < mqtt_dashboard_complete_20260205_192405.sql

# 4. Restart services
sudo systemctl restart mqtt_dashboard.service
sudo systemctl restart grafana-server.service
```

### Metadata Only Restore

To restore only configuration (topics, measurements, users) without data:

```bash
cd /home/ubuntu/mqtt_dashboard/backups

# 1. Uncompress the metadata backup
gunzip mqtt_dashboard_metadata_20260205_192405.sql.gz

# 2. Restore metadata tables
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard < mqtt_dashboard_metadata_20260205_192405.sql
```

### Selective Table Restore

To restore a specific table from the complete backup:

```bash
cd /home/ubuntu/mqtt_dashboard/backups

# 1. Uncompress if needed
gunzip mqtt_dashboard_complete_20260205_192405.sql.gz

# 2. Extract specific table (example: timestream_tables)
grep -A 10000 "COPY public.timestream_tables" mqtt_dashboard_complete_20260205_192405.sql | \
  awk '/^\\\./{exit} {print}' | \
  PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard

# Re-compress after
gzip mqtt_dashboard_complete_20260205_192405.sql
```

## Backup Script

The backup script is located at:
```
/home/ubuntu/mqtt_dashboard/backups/create_complete_backup.sh
```

### Create a New Backup

```bash
cd /home/ubuntu/mqtt_dashboard/backups
./create_complete_backup.sh
```

This will create:
- Timestamped SQL backup files
- Compressed archives (.gz)
- Summary report

### Automated Backups

To schedule automatic daily backups, add to crontab:

```bash
# Edit crontab
crontab -e

# Add this line for daily backup at 2 AM
0 2 * * * /home/ubuntu/mqtt_dashboard/backups/create_complete_backup.sh >> /home/ubuntu/mqtt_dashboard/backups/backup.log 2>&1
```

## Verification

### Verify Backup Integrity

Check if backup contains data:

```bash
cd /home/ubuntu/mqtt_dashboard/backups

# Count COPY statements (should be 300+)
zgrep -c "COPY.*FROM stdin" mqtt_dashboard_complete_20260205_192405.sql.gz

# Check for chunk data (should show hyper_ tables)
zgrep "COPY.*_hyper_" mqtt_dashboard_complete_20260205_192405.sql.gz | wc -l

# Check backup size (should be ~10MB compressed)
ls -lh mqtt_dashboard_complete_20260205_192405.sql.gz
```

### Test Restore (Dry Run)

Test restore to a temporary database:

```bash
# Create test database
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -c "CREATE DATABASE mqtt_dashboard_test;"

# Restore to test
cd /home/ubuntu/mqtt_dashboard/backups
gunzip -c mqtt_dashboard_complete_20260205_192405.sql.gz | \
  PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard_test

# Verify data
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard_test -c "
SELECT COUNT(*) FROM timestream_tables;
SELECT COUNT(*) FROM timestream_measurements;
SELECT COUNT(*) FROM cs_v1_data_cr1000x_46556_synop;
"

# Drop test database
PGPASSWORD='campDashSQL' psql -h localhost -U postgres -c "DROP DATABASE mqtt_dashboard_test;"
```

## Important Notes

### TimescaleDB Warnings

During backup, you may see NOTICE messages like:
```
pg_dump: NOTICE:  hypertable data are in the chunks, no data will be copied
```

**These are normal!** The data IS being backed up from the chunks. pg_dump backs up the `_hyper_*` chunk tables which contain all the actual data. The NOTICE just means the parent hypertable itself doesn't contain data (which is correct for TimescaleDB).

### Circular Foreign Keys

You may see warnings about circular foreign keys in TimescaleDB metadata. This is normal and the backup includes instructions to handle these during restore.

### Storage Requirements

- **Uncompressed:** ~101 MB
- **Compressed:** ~10 MB
- **Restore time:** 30-60 seconds
- **Disk space needed:** 200+ MB (temporary space during restore)

## Backup History

Keep multiple backups for safety. Recommended retention:

- **Daily:** Last 7 days
- **Weekly:** Last 4 weeks
- **Monthly:** Last 6 months

### Clean Old Backups

Remove backups older than 30 days:

```bash
find /home/ubuntu/mqtt_dashboard/backups -name "*.sql.gz" -mtime +30 -delete
find /home/ubuntu/mqtt_dashboard/backups -name "backup_summary_*.txt" -mtime +30 -delete
```

## Recovery Scenarios

### Scenario 1: Accidental Data Deletion

If you accidentally delete data but database structure is intact:

```bash
# 1. Stop services
sudo systemctl stop mqtt_dashboard.service

# 2. Restore complete backup
cd /home/ubuntu/mqtt_dashboard/backups
gunzip -c mqtt_dashboard_complete_20260205_192405.sql.gz | \
  PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard 2>&1 | \
  grep -i error

# 3. Restart services
sudo systemctl start mqtt_dashboard.service
```

### Scenario 2: Corrupted Measurements

If only measurements are corrupted:

```bash
# Restore metadata only
cd /home/ubuntu/mqtt_dashboard/backups
gunzip -c mqtt_dashboard_metadata_20260205_192405.sql.gz | \
  PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard
```

### Scenario 3: Complete Database Restore

If database is completely lost or corrupted:

```bash
# 1. Recreate database
PGPASSWORD='campDashSQL' psql -h localhost -U postgres << 'EOF'
DROP DATABASE IF EXISTS mqtt_dashboard;
CREATE DATABASE mqtt_dashboard;
\c mqtt_dashboard
CREATE EXTENSION IF NOT EXISTS timescaledb;
EOF

# 2. Restore complete backup
cd /home/ubuntu/mqtt_dashboard/backups
gunzip -c mqtt_dashboard_complete_20260205_192405.sql.gz | \
  PGPASSWORD='campDashSQL' psql -h localhost -U postgres -d mqtt_dashboard

# 3. Restart services
sudo systemctl restart mqtt_dashboard.service
sudo systemctl restart grafana-server.service
```

## Contact & Support

For backup-related issues:

1. Check backup integrity first (see Verification section)
2. Review backup.log if automated backups fail
3. Ensure sufficient disk space (at least 200MB free)
4. Verify PostgreSQL is running: `systemctl status postgresql`

## Related Documentation

- [Dashboard Setup Guide](../DASHBOARD_SETUP_GUIDE.md)
- [Import Script Documentation](../wiz2box_forward/README_IMPORT.md)
- [Main README](../README.md)
