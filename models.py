from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db, login_manager

class KVStore(db.Model):
    __tablename__ = "kvstore"
    key = db.Column(db.String(128), primary_key=True)
    value = db.Column(db.Text, nullable=True)

    @staticmethod
    def get(key, default=None):
        item = KVStore.query.get(key)
        return item.value if item else default

    @staticmethod
    def set(key, value):
        existing = KVStore.query.get(key)
        if existing:
            existing.value = value
        else:
            existing = KVStore(key=key, value=value)
            db.session.add(existing)
        db.session.commit()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def ensure_seed_admin():
    from config import Config
    db.create_all()
    if not User.query.filter_by(username=Config.ADMIN_USER).first():
        u = User(username=Config.ADMIN_USER)
        u.set_password(Config.ADMIN_PASS)
        db.session.add(u)
        db.session.commit()

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, default=20.0)
    currency = db.Column(db.String(8), default="USD")
    image_url = db.Column(db.String(512), default="")

class EventLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    channel = db.Column(db.String(16))    # 'pixel' or 'capi'
    event_name = db.Column(db.String(64))
    event_id = db.Column(db.String(64))
    status = db.Column(db.String(64))
    latency_ms = db.Column(db.Integer)
    payload = db.Column(db.Text)
    error = db.Column(db.Text)

class RequestLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    method = db.Column(db.String(8))
    path = db.Column(db.String(256))
    status = db.Column(db.Integer)
    latency_ms = db.Column(db.Integer)
    body = db.Column(db.Text)
    error = db.Column(db.Text)

class Counters(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pixel = db.Column(db.Integer, default=0)
    capi = db.Column(db.Integer, default=0)
    dedup = db.Column(db.Integer, default=0)
    margin_sum = db.Column(db.Float, default=0.0)
    pltv_sum = db.Column(db.Float, default=0.0)

    @staticmethod
    def get_or_create():
        obj = Counters.query.get(1)
        if not obj:
            obj = Counters(id=1)
            db.session.add(obj)
            db.session.commit()
        return obj
