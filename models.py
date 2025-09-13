from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    pw_hash = db.Column(db.String(255), nullable=False)
    def set_password(self, password): self.pw_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.pw_hash, password)

class KVStore(db.Model):
    key = db.Column(db.String(128), primary_key=True)
    value = db.Column(db.Text)
    @staticmethod
    def get(key, default=None):
        row = db.session.get(KVStore, key); return row.value if row else default
    @staticmethod
    def set(key, value):
        row = db.session.get(KVStore, key)
        if not row:
            row = KVStore(key=key, value=str(value)); db.session.add(row)
        else:
            row.value = str(value)
        db.session.commit()

class EventLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    channel = db.Column(db.String(16))
    event_name = db.Column(db.String(64))
    event_id = db.Column(db.String(128), index=True)
    status = db.Column(db.String(64))
    latency_ms = db.Column(db.Integer)
    payload = db.Column(db.Text)
    error = db.Column(db.Text)

class Counters(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    pixel = db.Column(db.Integer, default=0)
    capi = db.Column(db.Integer, default=0)
    dedup = db.Column(db.Integer, default=0)
    @staticmethod
    def get_or_create():
        c = db.session.get(Counters, 1)
        if not c: 
            c = Counters(id=1); db.session.add(c); db.session.commit()
        return c

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True)
    slug = db.Column(db.String(128), unique=True)
    name = db.Column(db.String(200))
    price = db.Column(db.Float, default=0.0)
    cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(8), default="USD")
    description = db.Column(db.Text)
    image_url = db.Column(db.String(512))
