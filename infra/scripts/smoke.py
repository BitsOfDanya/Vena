import json
import secrets
import urllib.error
import urllib.request
from uuid import uuid4

from sqlalchemy import delete
from app.db.models import User
from app.db.seed_users import create_user
from app.db.session import SessionLocal

base = "http://127.0.0.1:8000/api/v1"


def request(path, token=None, method="GET", body=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, headers=headers, method=method,
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, data = error.code, error.read()
    assert status == expected, f"{method} {path}: {status}, expected {expected}"
    return json.loads(data) if data else None


prefix = "smoke-" + uuid4().hex[:12]
password = secrets.token_urlsafe(32)
usernames = [f"{prefix}-{role}" for role in ["admin", "viewer"]]
try:
    with SessionLocal.begin() as db:
        for username, role in zip(usernames, ["admin", "viewer"]):
            create_user(db, username, f"{username}@example.com", password, role)
    assert request('/health')['status'] == 'ok'
    assert request('/auth/status')['configured']
    request('/auth/me', expected=401)
    admin = request('/auth/login', method='POST', body={
        'email': usernames[0]+'@example.com', 'password': password})['access_token']
    viewer = request('/auth/login', method='POST', body={
        'login': usernames[1], 'password': password})['access_token']
    assert request('/auth/me', admin)['role'] == 'admin'
    snapshot = request('/predictions/snapshot', admin)
    integration = request('/integrations/status', admin)
    if snapshot['available']:
        assert request('/predictions?limit=5', admin), 'ML snapshot has no predictions'
    else:
        assert integration['worker'].get('state') in {'waiting', 'processing'}, integration['worker']
        request('/predictions?limit=5', admin, expected=503)
        print('ML explicitly waiting for data or initial processing; no demo fallback')
    request('/users', admin)
    request('/users', viewer, expected=403)
    request('/equipment', viewer)
    for path in ['/actions', '/notifications', '/journal', '/spatial', '/system/components']:
        request(path, admin)
    request('/predictions/refresh', admin, method='POST')
    request('/predictions/refresh', viewer, method='POST', expected=403)
    request('/auth/logout', admin, method='POST')
    request('/auth/me', admin, expected=401)
    print('PASS: password login, JWT, revocation, RBAC, ML snapshot and database API')
finally:
    with SessionLocal.begin() as db:
        db.execute(delete(User).where(User.username.in_(usernames)))
