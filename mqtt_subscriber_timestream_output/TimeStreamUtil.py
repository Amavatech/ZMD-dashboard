"""Deprecated AWS Timestream helper.

This project now writes to PostgreSQL TimescaleDB hypertables via
`timescaleUtil.py`. This module remains as a stub to avoid confusion if it is
imported accidentally.
"""

def _deprecated(*_args, **_kwargs):
    raise RuntimeError("AWS Timestream support has been removed. Use timescaleUtil instead.")


create_database = _deprecated
create_table = _deprecated
write_records = _deprecated