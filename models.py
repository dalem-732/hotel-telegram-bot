from peewee import SqliteDatabase, Model, CharField, DateTimeField, TextField, FloatField
import datetime

db = SqliteDatabase('history.db')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    user_id = CharField(unique=True)
    username = CharField(null=True)

class SearchHistory(BaseModel):
    user_id = CharField()
    command = CharField()
    date_time = DateTimeField(default=datetime.datetime.now)
    hotel_name = CharField()
    hotel_link = TextField()
    price = FloatField(null=True)
    
    class Meta:
        order_by = ('-date_time',)

def create_models():
    db.connect()
    db.create_tables([User, SearchHistory])
