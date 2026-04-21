#!/usr/bin/env python3
"""
Migrate schema from mqtt_dashboard to public.
- Timestream data tables: recreate empty structure only (no data)
- Metadata tables: move with data
"""
import sys
import os
import psycopg2
from psycopg2 import sql

# Add the utility directory to sys.path
utility_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mqtt_subscriber_timestream_output'))
sys.path.insert(0, utility_path)

import configUtil as config
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

# Tables that should be moved WITH data (metadata tables only)
METADATA_TABLES = [
    'timestream_tables',
    'timestream_measurements',
    'brokers',
    'permissions'
]

# Row count threshold - tables with more rows will have schema only migrated
MAX_ROWS_FOR_DATA_MIGRATION = 100000

def get_connection():
    return psycopg2.connect(
        dbname=config.timescale.database,
        user=config.timescale.username,
        password=config.timescale.password,
        host=config.timescale.host,
        port=config.timescale.port,
    )

def get_row_count(cur, schema, table):
    """Get row count for a table (uses estimate for large tables)"""
    try:
        # Try fast estimate first
        cur.execute("""
            SELECT n_live_tup 
            FROM pg_stat_user_tables 
            WHERE schemaname = %s AND relname = %s
        """, (schema, table))
        result = cur.fetchone()
        if result and result[0] is not None:
            estimate = result[0]
            # If estimate is very small or 0, do exact count
            if estimate < 1000:
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    sql.Identifier(schema),
                    sql.Identifier(table)
                ))
                return cur.fetchone()[0]
            return estimate
        else:
            # Fall back to exact count
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(schema),
                sql.Identifier(table)
            ))
            return cur.fetchone()[0]
    except Exception as e:
        print(f"    Warning: Could not count rows: {e}")
        return 0

def table_exists(cur, schema, table):
    """Check if table exists"""
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = %s
        )
    """, (schema, table))
    return cur.fetchone()[0]

def get_create_table_sql(cur, schema, table):
    """Get the CREATE TABLE statement for a table"""
    # Get column definitions
    cur.execute("""
        SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (schema, table))
    
    columns = cur.fetchall()
    col_defs = []
    for col_name, data_type, char_len, nullable, default in columns:
        col_def = f'"{col_name}" '
        if data_type == 'character varying' and char_len:
            col_def += f'VARCHAR({char_len})'
        elif data_type == 'timestamp with time zone':
            col_def += 'TIMESTAMPTZ'
        elif data_type == 'double precision':
            col_def += 'DOUBLE PRECISION'
        else:
            col_def += data_type.upper()
        
        if nullable == 'NO':
            col_def += ' NOT NULL'
        if default:
            col_def += f' DEFAULT {default}'
        
        col_defs.append(col_def)
    
    return f"CREATE TABLE IF NOT EXISTS public.\"{table}\" (\n  " + ",\n  ".join(col_defs) + "\n)"

def recreate_empty_table(cur, schema, table):
    """Recreate table structure in public schema without data"""
    # Get the CREATE TABLE statement
    create_sql = get_create_table_sql(cur, schema, table)
    
    # Drop if exists
    cur.execute(sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE").format(sql.Identifier(table)))
    
    # Create new table
    cur.execute(create_sql)
    
    # Recreate indexes
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s AND tablename = %s
    """, (schema, table))
    
    for idx_name, idx_def in cur.fetchall():
        # Replace schema name in index definition
        new_idx_def = idx_def.replace(f'{schema}.', 'public.')
        try:
            cur.execute(new_idx_def)
        except:
            pass  # Index might already exist or have constraints

def migrate_tables():
    conn = get_connection()
    conn.autocommit = True
    
    print("="*70)
    print("Schema Migration: mqtt_dashboard -> public")
    print("="*70)
    
    try:
        with conn.cursor() as cur:
            # Get all tables in mqtt_dashboard schema
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'mqtt_dashboard' 
                AND table_type = 'BASE TABLE'
                AND table_name NOT LIKE '_hyper_%'
                ORDER BY table_name
            """)
            
            tables = cur.fetchall()
            total = len(tables)
            
            if not tables:
                print("\n✓ No tables found in mqtt_dashboard schema. Migration may already be complete.")
                return
            
            print(f"\nFound {total} tables to migrate")
            print("-"*70)
            
            moved_with_data = 0
            recreated_empty = 0
            skipped = 0
            failed = 0
            moved_with_data = 0
            recreated_empty = 0
            skipped = 0
            failed = 0
            
            for idx, (table_name,) in enumerate(tables, 1):
                try:
                    print(f"\n[{idx}/{total}] {table_name}")
                    print("-" * 70)
                    
                    # Get source row count (with progress indicator)
                    print(f"  → Checking row count...")
                    source_count = get_row_count(cur, 'mqtt_dashboard', table_name)
                    if source_count < 1000:
                        print(f"  Rows: {source_count:,} (exact)")
                    else:
                        print(f"  Rows: ~{source_count:,} (estimate)")
                    
                    # Determine migration strategy
                    is_metadata = table_name in METADATA_TABLES
                    is_large_table = source_count > MAX_ROWS_FOR_DATA_MIGRATION
                    
                    if is_metadata and not is_large_table:
                        migration_type = "MOVE_WITH_DATA"
                        print(f"  Strategy: Move WITH data (metadata table, {source_count:,} rows)")
                    elif is_large_table:
                        migration_type = "RECREATE_EMPTY"
                        print(f"  Strategy: Recreate EMPTY (>{MAX_ROWS_FOR_DATA_MIGRATION:,} rows, too large)")
                    else:
                        migration_type = "RECREATE_EMPTY"
                        print(f"  Strategy: Recreate EMPTY (data table)")
                    
                    # Check if table already exists in public schema
                    if table_exists(cur, 'public', table_name):
                        target_count = get_row_count(cur, 'public', table_name)
                        print(f"  ⚠ Already exists in public with {target_count:,} rows")
                        print(f"  ⊘ SKIPPED (keeping existing public version)")
                        skipped += 1
                        continue
                    
                    if migration_type == "MOVE_WITH_DATA":
                        # Copy table data instead of moving (avoids lock issues)
                        print(f"  → Creating table structure in public...")
                        recreate_empty_table(cur, 'mqtt_dashboard', table_name)
                        
                        print(f"  → Copying {source_count:,} rows...")
                        cur.execute(sql.SQL(
                            "INSERT INTO public.{} SELECT * FROM mqtt_dashboard.{}"
                        ).format(
                            sql.Identifier(table_name),
                            sql.Identifier(table_name)
                        ))
                        
                        new_count = get_row_count(cur, 'public', table_name)
                        print(f"  ✓ COPIED successfully ({new_count:,} rows)")
                        
                        # Drop the old table
                        print(f"  → Dropping old table from mqtt_dashboard...")
                        cur.execute(sql.SQL("DROP TABLE IF EXISTS mqtt_dashboard.{} CASCADE").format(
                            sql.Identifier(table_name)
                        ))
                        
                        moved_with_data += 1
                    else:
                        # Recreate table structure only (no data)
                        print(f"  → Creating empty table structure in public...")
                        recreate_empty_table(cur, 'mqtt_dashboard', table_name)
                        
                        # Check if this is a hypertable and convert
                        cur.execute("""
                            SELECT EXISTS (
                                SELECT 1 FROM timescaledb_information.hypertables 
                                WHERE hypertable_schema = 'mqtt_dashboard' 
                                AND hypertable_name = %s
                            )
                        """, (table_name,))
                        
                        is_hypertable = cur.fetchone()[0]
                        if is_hypertable:
                            try:
                                cur.execute(
                                    "SELECT create_hypertable(%s, %s, if_not_exists => TRUE, migrate_data => FALSE);",
                                    (f"public.{table_name}", "time")
                                )
                                print(f"    (converted to hypertable)")
                            except Exception as e:
                                if "already a hypertable" not in str(e):
                                    print(f"    Note: {e}")
                        
                        # Drop the old table
                        print(f"  → Dropping old table from mqtt_dashboard...")
                        cur.execute(sql.SQL("DROP TABLE IF EXISTS mqtt_dashboard.{} CASCADE").format(
                            sql.Identifier(table_name)
                        ))
                        
                        print(f"  ✓ RECREATED empty (schema only, {source_count:,} rows NOT migrated)")
                        recreated_empty += 1
                        
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    failed += 1
                    
            print("\n" + "="*70)
            print("Migration Summary")
            print("="*70)
            print(f"Total tables: {total}")
            print(f"  ✓ Moved with data:     {moved_with_data}")
            print(f"  ✓ Recreated empty:     {recreated_empty}")
            print(f"  ⊘ Skipped:             {skipped}")
            print(f"  ✗ Failed:              {failed}")
            
            # Check remaining objects
            cur.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'mqtt_dashboard'
                AND table_name NOT LIKE '_hyper_%'
            """)
            remaining = cur.fetchone()[0]
            
            print(f"\nRemaining tables in mqtt_dashboard: {remaining}")
            
            if failed == 0:
                print("\n✓ Migration completed successfully!")
                print(f"\nNote: Tables with >{MAX_ROWS_FOR_DATA_MIGRATION:,} rows were recreated empty.")
                print("You can now populate them using the import script.")
            else:
                print(f"\n⚠ Migration completed with {failed} errors")
                
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_tables()
