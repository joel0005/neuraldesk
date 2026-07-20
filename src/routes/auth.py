"""Auth Routes — signup, login, JWT."""

import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from jose import jwt
from passlib.hash import bcrypt
from ..models.database import get_db
from ..config import config

auth = Blueprint("auth", __name__)


def create_token(user_id, email):
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=config.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def get_current_user():
    """Call this in any protected route to get the logged-in user."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        return dict(user) if user else None
    except Exception:
        return None


@auth.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.json
    email = data.get("email", "").strip()
    password = data.get("password", "")
    name = data.get("name", "").strip()

    if not email or not password or not name:
        return jsonify({"error": "email, password, and name required"}), 400

    db = get_db()

    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.close()
        return jsonify({"error": "Email already registered"}), 400

    user_id = str(uuid.uuid4())
    password_hash = bcrypt.hash(password)

    db.execute(
        "INSERT INTO users (id, email, password_hash, name) VALUES (?, ?, ?, ?)",
        (user_id, email, password_hash, name),
    )
    db.commit()
    db.close()

    token = create_token(user_id, email)
    return jsonify({
        "access_token": token,
        "user_id": user_id,
        "name": name,
        "email": email,
        "plan": "free",
    })


@auth.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "")
    password = data.get("password", "")

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()

    if not user or not bcrypt.verify(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_token(user["id"], user["email"])
    return jsonify({
        "access_token": token,
        "user_id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "plan": user["plan"],
    })