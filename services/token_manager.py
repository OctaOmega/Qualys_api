import requests
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

# Using absolute imports assuming running from root or modules setup
from extensions import db
from models import QualysAuthToken

TOKEN_LIFETIME = timedelta(hours=3, minutes=55)

def _parse_token_from_response(resp: requests.Response) -> str:
    # Try JSON first
    try:
        body = resp.json()
    except Exception:
        body = None

    token = None
    if isinstance(body, dict):
        token = (
            body.get("token")
            or body.get("access_token")
            or body.get("jwt")
            or (body.get("data") or {}).get("token")
        )

    if not token:
        # fallback: plain text
        text = (resp.text or "").strip()
        if text.count(".") == 2 and len(text) > 50:
            token = text

    if not token:
        raise RuntimeError(f"Could not parse token from auth response: {resp.text[:2000]}")

    return token

def _invalidate_if_expired(token_row: QualysAuthToken) -> None:
    now = datetime.utcnow()
    if token_row.valid and token_row.expires_at <= now:
        token_row.valid = False
        db.session.add(token_row)

def get_valid_token() -> str:
    """
    Returns a valid token from DB.
    If token expired or none exists: refresh and store a new one.
    Ensures expired token is marked valid=False.
    """
    try:
        # Get newest token row
        token_row = (
            QualysAuthToken.query.order_by(QualysAuthToken.id.desc()).first()
        )

        if token_row:
            _invalidate_if_expired(token_row)
            db.session.commit()

            if token_row.valid:
                return token_row.token_value

        # No token or token invalid -> refresh
        return refresh_token()

    except SQLAlchemyError as e:
        db.session.rollback()
        raise RuntimeError(f"DB error while getting token: {e}")

def refresh_token() -> str:
    """
    Requests a new Qualys token and stores it as valid=True with expires_at.
    Marks any existing valid tokens as valid=False (optional safety).
    """
    cfg = current_app.config
    auth_url = cfg["QUALYS_AUTH_URL"]
    username = cfg["QUALYS_USERNAME"]
    password = cfg["QUALYS_PASSWORD"]
    timeout_secs = cfg.get("QUALYS_TIMEOUT_SECS", 60)

    if not username or not password:
        raise ValueError("QUALYS_USERNAME / QUALYS_PASSWORD not set")

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "username": username,
        "password": password,
        "token": "true",
        "permissions": "true",
    }

    resp = requests.post(auth_url, headers=headers, data=data, timeout=timeout_secs)

    # Treat 200 or 201 as success
    if resp.status_code not in (200, 201):
        # store a failed attempt row (optional)
        failed = QualysAuthToken(
            token_value="",
            valid=False,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow(),
            auth_url=auth_url,
            status_code=resp.status_code,
            error_message=f"Auth failed: {resp.text[:2000]}",
        )
        db.session.add(failed)
        db.session.commit()
        raise RuntimeError(f"Qualys auth failed ({resp.status_code}): {resp.text[:2000]}")

    token = _parse_token_from_response(resp)
    now = datetime.utcnow()
    expires_at = now + TOKEN_LIFETIME

    # Optional: invalidate all previous valid tokens
    QualysAuthToken.query.filter_by(valid=True).update({"valid": False})
    db.session.commit()

    row = QualysAuthToken(
        token_value=token,
        created_at=now,
        expires_at=expires_at,
        valid=True,
        auth_url=auth_url,
        status_code=resp.status_code,
        error_message=None,
    )
    db.session.add(row)
    db.session.commit()

    return token
