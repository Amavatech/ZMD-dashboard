from email.policy import default
from enum import unique
from operator import add
from typing import Collection
from xmlrpc.client import Boolean
import pymysql
import sqlalchemy
from sqlalchemy import ForeignKey, create_engine,Column,Integer,String,Float, event
from sqlalchemy.orm import declarative_base,sessionmaker, relationship
import configUtil as config

Base=declarative_base()
Session=sessionmaker()

# Pass options directly to psycopg2 to ensure search_path is set for every connection
engine=create_engine(
    f'postgresql+psycopg2://{config.timescale.username}:{config.timescale.password}@{config.timescale.host}:{config.timescale.port}/{config.timescale.database}',
    connect_args={'options': '-csearch_path=public'},
    echo=False
)

Session.configure(bind=engine)
session=Session()

class timestream_table(Base):
    __tablename__='timestream_tables'
    tableID=Column('tableid',Integer,primary_key=True)
    brokerID=Column('brokerid',Integer,ForeignKey("brokers.brokerid"))
    topic=Column('topic',String(255),unique=True)
    db_uid=Column('db_uid',String(15))
    ss_key=Column('ss_key',String(32),server_default="")
    longitude=Column('longitude',Float)
    latitude=Column('latitude',Float)
    groupID=Column('groupid',Integer)
    station_id=Column('station_id',String(64))
    topics=Column('topics',sqlalchemy.ARRAY(String(255)))
    def __repr__(self) -> str:
        return f"<Timestream Table(tableID={self.tableID}, station_id={self.station_id}, topic={self.topic})>"
    broker=relationship("broker",back_populates="tables")

class timestream_measurement(Base):
    __tablename__='timestream_measurements'
    measurementID=Column('measurementid',Integer,primary_key=True)
    name=Column('name',String(255))
    directionName=Column('directionname',String(255))
    tableID=Column('tableid',Integer,ForeignKey('timestream_tables.tableid'))
    unit=Column('unit',String(255),server_default="unitless")
    nickname=Column('nickname',String(100),server_default="")
    type=Column('type',String(10),server_default="DOUBLE")
    visible=Column('visible',Integer,default=1,server_default='1')
    status=Column('status',Integer,default=0,server_default='0')
    graph=Column('graph',String(10),server_default="LINE")
    table=relationship("timestream_table",back_populates="measurements")

class broker(Base):
    __tablename__='brokers'
    brokerID=Column('brokerid',Integer,primary_key=True)
    URL=Column('url',String(100))
    port=Column('port',Integer)
    authentication=Column('authentication',sqlalchemy.Boolean(),default=True,server_default='t')
    username=Column('username',String(100))
    password=Column('password',String(100))
    name=Column('name',String(100))
    def __repr__(self) -> str:
        return f"<Broker(brokerID={self.brokerID},name={self.name}, URL={self.URL}, port={self.port}, username={self.username})>"

timestream_table.measurements=relationship("timestream_measurement",order_by=timestream_measurement.measurementID,back_populates="table")
broker.tables=relationship("timestream_table",order_by=timestream_table.tableID,back_populates="broker")
# REMOVED create_all to avoid schema pollution in public
# Base.metadata.create_all(engine)

def get_all_brokers():
    res=session.query(broker).all()
    return res

def get_broker_by_id(brokerID:int)->broker:
    res=session.query(broker).filter_by(brokerID=brokerID).first()
    return res

def get_broker_by_url_port(url: str, port: int) -> broker:
    return session.query(broker).filter_by(URL=url, port=port).first()

def add_broker_record(url: str, port: int, authentication: bool, username: str, password: str, name: str = "") -> broker:
    existing = get_broker_by_url_port(url, port)
    if existing:
        return existing
    new_broker = broker(
        URL=url,
        port=port,
        authentication=authentication,
        username=username,
        password=password,
        name=name,
    )
    session.add(new_broker)
    session.commit()
    return new_broker

def _extract_station_id(topic: str) -> str:
    """Extract canonical station_id from an MQTT topic (mirrors migration script logic)."""
    import re
    m = re.search(r'/(\d{4,})(/|$)', topic)
    if m:
        return m.group(1)
    name_m = re.search(r'/0-894-2-([^/]+)/data', topic)
    if name_m:
        return name_m.group(1)
    # Last meaningful path segment
    parts = [p for p in re.split(r'[/]', topic)
             if p and p.lower() not in {
                 'data', 'cr1000x', 'cr1000', 'synop', 'hour', 'cr350', 'satellite',
                 'status', 'state', 'table2m', 'campbell', 'v1', 'campbell-v1',
                 'southafrica', 'zmb', 'stellenbosch', 'csa', 'csaf', 'limpopo'}]
    return parts[-1] if parts else topic


def get_table_by_station_id(station_id: str) -> timestream_table:
    """Look up a timestream_table row by canonical station_id."""
    return session.query(timestream_table).filter_by(station_id=station_id).first()


def get_timestream_table_id(tblName: str) -> int:
    """Return tableID for exact topic match, or by station_id if no exact match."""
    res = session.query(timestream_table).filter_by(topic=tblName).first()
    if res:
        return res.tableID
    sid = _extract_station_id(tblName)
    res = get_table_by_station_id(sid)
    return res.tableID if res else None


def get_timestream_table(tblName: str) -> timestream_table:
    """Find the timestream_table for this topic.
    First tries exact topic match; falls back to station_id lookup so that
    HOUR/SYNOP/satellite variants all resolve to the same merged row.
    """
    if tblName and tblName[0] == "/":
        tblName = tblName[1:]
    if tblName and tblName[-1] == "/":
        tblName = tblName[:-1]
    # Exact match first
    res = session.query(timestream_table).filter_by(topic=tblName).first()
    if res:
        return res
    # Fallback: match by station_id
    sid = _extract_station_id(tblName)
    return get_table_by_station_id(sid)


def get_timestream_tables_substring(subStr: str):
    res = session.query(timestream_table).filter(
        timestream_table.topic.contains(subStr)).all()
    return res


def does_timestream_table_exist(tblName: str) -> bool:
    """True if a row exists for this exact topic OR for the inferred station_id."""
    if session.query(timestream_table).filter_by(topic=tblName).count() > 0:
        return True
    sid = _extract_station_id(tblName)
    return session.query(timestream_table).filter_by(station_id=sid).count() > 0


def does_timestream_measurement_exist(tblName: str, measurement: str) -> bool:
    table = get_timestream_table(tblName)
    if not table:
        return False
    return session.query(timestream_measurement).filter_by(
        tableID=table.tableID, name=measurement).count() > 0


def add_timestream_table(tblName: str, brokerID: int = 1, commit: bool = True):
    """Create a new station row, or (if the station_id already exists) just append
    the new topic to the existing row's topics array instead of inserting a duplicate.
    """
    sid = _extract_station_id(tblName)
    # Check if station already exists under a different topic
    existing = get_table_by_station_id(sid)
    if existing:
        # Just add the new topic variant to the topics array
        current_topics = list(existing.topics or [])
        if tblName not in current_topics:
            current_topics.append(tblName)
            existing.topics = current_topics
            if commit:
                session.commit()
        return existing
    try:
        new_table = timestream_table(
            topic=tblName, brokerID=brokerID, db_uid="",
            longitude=0, latitude=0,
            station_id=sid, topics=[tblName]
        )
        session.add(new_table)
        if commit:
            session.commit()
        return new_table
    except sqlalchemy.exc.IntegrityError as err:
        print(f"MySQL: Timestream Table {tblName} already exists")
        print(err)
        session.rollback()
        return None


def add_timestream_measurement(tblName: str, name: str, unit: str = "unitless",
                                type: str = "DOUBLE", commit: bool = True,
                                status: bool = False):
    table = get_timestream_table(tblName)
    if not table:
        print("Timestream Table does not exist")
        return
    new_measurement = timestream_measurement(
        name=name,
        tableID=table.tableID,
        unit=unit,
        type=type,
        nickname="",
        status=1 if status else 0,
        visible=1
    )
    session.add(new_measurement)
    if commit:
        session.commit()


def create_dashboard_table(table: timestream_table):
    import grafana_helpers
    grafana_helpers.create_dashboard_table(table, session=session)


def restart_session():
    s = False
    while not s:
        global session
        try:
            session.close()
            session=Session()
            s=True
        except exc.SQLAlchemyError:
            pass