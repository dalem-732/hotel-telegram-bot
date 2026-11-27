import os
from datetime import datetime
from pathlib import Path

from peewee import SqliteDatabase, Model, CharField, DateTimeField, TextField, FloatField


db = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    user_id = CharField(unique=True)
    username = CharField(null=True)


class SearchHistory(BaseModel):
    user_id = CharField()
    command = CharField()
    date_time = DateTimeField(default=datetime.now)
    hotel_name = CharField()
    hotel_link = TextField()
    price = FloatField(null=True)


def get_db_path() -> str:
    return os.getenv("DATABASE_PATH") or "history.db"


def create_models():
    path = get_db_path()
    parent = Path(path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    if not db.is_closed():
        db.close()
    db.init(
        str(Path(path).expanduser().resolve()),
        pragmas={"journal_mode": "wal", "busy_timeout": 5000},
        check_same_thread=True,
    )
    db.connect()
    db.create_tables([User, SearchHistory])


def upsert_user(user_id, username):
    uid = str(user_id)
    user, created = User.get_or_create(user_id=uid, defaults={"username": username})
    if not created and user.username != username:
        user.username = username
        user.save()
    return user
