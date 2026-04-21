#!/bin/bash
# Complete Database Backup Script for TimescaleDB
# This script creates a full backup including all hypertable chunks

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/ubuntu/mqtt_dashboard/backups"
DB_NAME="mqtt_dashboard"
DB_USER="postgres"
DB_HOST="localhost"
export PGPASSWORD='campDashSQL'

echo "======================================================"
echo "Starting Complete Database Backup: $TIMESTAMP"
echo "======================================================"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup 1: Schema and data (including chunks) in plain SQL format
echo "Creating SQL backup (schema + data + chunks)..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-acl \
    --file="$BACKUP_DIR/mqtt_dashboard_complete_${TIMESTAMP}.sql"

# Backup 2: Metadata tables separately (ensure we have configuration data)
echo "Backing up critical metadata tables..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-acl \
    --table=timestream_tables \
    --table=timestream_measurements \
    --table=users \
    --table=groups \
    --table=permissions \
    --table=weather_data \
    --file="$BACKUP_DIR/mqtt_dashboard_metadata_${TIMESTAMP}.sql"

# Backup 3: Create a summary report
echo "Creating backup summary..."
cat > "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt" << EOF
Database Backup Summary
=======================
Date: $(date)
Database: $DB_NAME
Host: $DB_HOST

Backup Files:
-------------
1. Complete backup: mqtt_dashboard_complete_${TIMESTAMP}.sql
2. Metadata backup: mqtt_dashboard_metadata_${TIMESTAMP}.sql

Database Statistics:
--------------------
EOF

# Add table counts to summary
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT 
    'timestream_tables: ' || COUNT(*) || ' topics' 
FROM timestream_tables
UNION ALL
SELECT 
    'timestream_measurements: ' || COUNT(*) || ' measurements' 
FROM timestream_measurements
UNION ALL
SELECT 
    'users: ' || COUNT(*) || ' users' 
FROM users
UNION ALL
SELECT 
    'groups: ' || COUNT(*) || ' groups' 
FROM groups;
" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"

# Add file sizes
echo "" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
echo "Backup File Sizes:" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
echo "-------------------" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
ls -lh "$BACKUP_DIR/mqtt_dashboard_complete_${TIMESTAMP}.sql" | awk '{print "Complete: " $5}' >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
ls -lh "$BACKUP_DIR/mqtt_dashboard_metadata_${TIMESTAMP}.sql" | awk '{print "Metadata: " $5}' >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"

# Compress backups to save space
echo "Compressing backups..."
gzip -f "$BACKUP_DIR/mqtt_dashboard_complete_${TIMESTAMP}.sql"
gzip -f "$BACKUP_DIR/mqtt_dashboard_metadata_${TIMESTAMP}.sql"

echo "" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
echo "Compressed Sizes:" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
echo "------------------" >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
ls -lh "$BACKUP_DIR/mqtt_dashboard_complete_${TIMESTAMP}.sql.gz" | awk '{print "Complete: " $5}' >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
ls -lh "$BACKUP_DIR/mqtt_dashboard_metadata_${TIMESTAMP}.sql.gz" | awk '{print "Metadata: " $5}' >> "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"

# Display summary
echo ""
echo "======================================================"
echo "Backup Complete!"
echo "======================================================"
cat "$BACKUP_DIR/backup_summary_${TIMESTAMP}.txt"
echo ""
echo "Restore Instructions:"
echo "--------------------"
echo "To restore the complete database:"
echo "  gunzip mqtt_dashboard_complete_${TIMESTAMP}.sql.gz"
echo "  psql -h localhost -U postgres -d mqtt_dashboard < mqtt_dashboard_complete_${TIMESTAMP}.sql"
echo ""
echo "To restore only metadata:"
echo "  gunzip mqtt_dashboard_metadata_${TIMESTAMP}.sql.gz"
echo "  psql -h localhost -U postgres -d mqtt_dashboard < mqtt_dashboard_metadata_${TIMESTAMP}.sql"
echo "======================================================"
