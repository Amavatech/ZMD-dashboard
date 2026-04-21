"""
Rebuild all Grafana dashboards for every timestream_table entry.

Run from the project root:
  python3 rebuild_dashboards.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mqtt_dashboard import create_app, db
from mqtt_dashboard import models
from mqtt_dashboard import grafana_helpers

app = create_app()

with app.app_context():
    tables = db.session.query(models.timestream_table).all()
    print(f"Rebuilding dashboards for {len(tables)} table(s)...")
    for i, t in enumerate(tables, 1):
        try:
            grafana_helpers.create_dashboard_table(t)
            print(f"  [{i}/{len(tables)}] OK  {t.topic}  uid={t.db_uid}")
        except Exception as exc:
            print(f"  [{i}/{len(tables)}] FAIL  {t.topic}  error={exc}")
    db.session.commit()
    print("Done.")
