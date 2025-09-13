
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    pw_hash = db.Column(db.String(255), nullable=False)
    def set_password(self, pw): self.pw_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.pw_hash, pw)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True)
    slug = db.Column(db.String(128), unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, default=0.0)
    cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(8), default="USD")
    description = db.Column(db.Text)
    image_url = db.Column(db.String(500))

class EventLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    channel = db.Column(db.String(16))  # pixel|capi|app
    event_name = db.Column(db.String(64))
    event_id = db.Column(db.String(128), index=True)
    status = db.Column(db.String(32))
    latency_ms = db.Column(db.Integer, default=0)
    payload = db.Column(db.Text)
    error = db.Column(db.Text)

class KVStore(db.Model):
    key = db.Column(db.String(120), primary_key=True)
    val = db.Column(db.Text, nullable=True)
    @staticmethod
    def get(k, default=None):
        row = KVStore.query.filter_by(key=k).first()
        return row.val if row else default
    @staticmethod
    def set(k, v):
        row = KVStore.query.filter_by(key=k).first()
        if not row:
            row = KVStore(key=k, val=str(v)); db.session.add(row)
        else:
            row.val = str(v)
        db.session.commit()
