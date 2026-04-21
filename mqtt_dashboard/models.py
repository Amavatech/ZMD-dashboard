from flask_login import UserMixin, current_user
from . import db

class User(UserMixin,db.Model):
    __tablename__='users'
    userID=db.Column('userid',db.Integer,primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))
    db_uid=db.Column(db.String(15))
    ss_key=db.Column(db.String(32),server_default="")
    def get_id(self):
        return self.userID

class timestream_table(db.Model):
    __tablename__='timestream_tables'
    tableID=db.Column('tableid',db.Integer,primary_key=True)
    topic=db.Column(db.String(255),unique=True)
    brokerID=db.Column('brokerid',db.Integer,db.ForeignKey("brokers.brokerid"))
    db_uid=db.Column(db.String(15))
    ss_key=db.Column(db.String(32),server_default="")
    longitude=db.Column(db.Float)
    latitude=db.Column(db.Float)
    groupID=db.Column('groupid',db.Integer)
    station_id=db.Column('station_id',db.String(64))
    topics=db.Column('topics',db.ARRAY(db.String(255)))
    def __repr__(self) -> str:
        return f"<Timestream Table(tableID={self.tableID}, station_id={self.station_id}, topic={self.topic})>"
    broker=db.relationship("broker",back_populates="tables")

class timestream_measurement(db.Model):
    __tablename__='timestream_measurements'
    measurementID=db.Column('measurementid',db.Integer,primary_key=True)
    name=db.Column('name',db.String(255))
    directionName=db.Column('directionname',db.String(255))
    tableID=db.Column('tableid',db.Integer,db.ForeignKey('timestream_tables.tableid'))
    unit=db.Column('unit',db.String(255),server_default="unitless")
    nickname=db.Column('nickname',db.String(100),server_default="")
    type=db.Column('type',db.String(10),server_default="DOUBLE")
    graph=db.Column('graph',db.String(10),server_default="LINE")
    visible=db.Column('visible',db.Integer,default=1,server_default='1')
    status=db.Column('status',db.Integer,default=0,server_default='0')
    table=db.relationship("timestream_table",back_populates="measurements")


class permission(db.Model):
    __tablename__='permissions'
    permissionID=db.Column('permissionid',db.Integer,primary_key=True)
    type=db.Column(db.String(10),server_default="TOPIC")
    userID=db.Column('userid',db.Integer,db.ForeignKey('users.userid'))
    tableID=db.Column('tableid',db.Integer,db.ForeignKey('timestream_tables.tableid'))
    groupID=db.Column('groupid',db.Integer,db.ForeignKey('groups.groupid'))
    user=db.relationship("User",back_populates="permissions")
    def __repr__(self) -> str:
        return f"<Permission(permissionID={self.permissionID},type={self.type},userID={self.userID},tableID={self.tableID},groupID={self.groupID}>"
    
class broker(db.Model):
    __tablename__='brokers'
    brokerID=db.Column('brokerid',db.Integer,primary_key=True)
    URL=db.Column('url',db.String(100))
    port=db.Column(db.Integer)
    authentication=db.Column(db.Integer)
    username=db.Column(db.String(100))
    password=db.Column(db.String(100))
    name=db.Column(db.String(100))
    def __repr__(self) -> str:
        return f"<Broker(brokerID={self.brokerID},name={self.name}, URL={self.URL}, port={self.port}, username={self.username})>"
    

class group(db.Model):
    __tablename__='groups'
    groupID=db.Column('groupid',db.Integer,primary_key=True)
    name=db.Column(db.String(100))

broker.tables=db.relationship("timestream_table",order_by=timestream_table.tableID,back_populates="broker")
timestream_table.measurements=db.relationship("timestream_measurement",order_by=timestream_measurement.measurementID,back_populates="table")
User.permissions=db.relationship("permission",order_by=permission.permissionID,back_populates="user")