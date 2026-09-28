"""Exercise authenticated API, database writes, snapshot and RBAC inside backend."""
import json
import os
import urllib.error
import urllib.request

base = "http://127.0.0.1:8000/api/v1"
keys = json.loads(os.environ["VENA_API_KEYS_JSON"])


def request(path, key=None, method="GET", body=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(base + path, headers=headers, method=method,
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, data = error.code, error.read()
    assert status == expected, f"{method} {path}: {status}, expected {expected}: {data[:200]}"
    return json.loads(data) if data else None


admin = next(key for key, value in keys.items() if (value if isinstance(value, str) else value['role']) == 'admin')
assert request('/health')['status'] == 'ok'
assert request('/auth/status')['keys_configured']
request('/auth/me', expected=401)
assert request('/auth/login', method='POST', body={'api_key': admin})['role'] == 'admin'
assert request('/auth/me', admin)['role'] == 'admin'
predictions = request('/predictions?limit=5', admin)
assert predictions, 'ML snapshot has no predictions'
for path in ['/actions', '/notifications', '/journal', '/spatial', '/system/components']:
    request(path, admin)
request('/predictions/refresh', admin, method='POST')
viewer = next((key for key, value in keys.items() if value == 'viewer'), None)
if viewer:
    request('/predictions/refresh', viewer, method='POST', expected=403)
print('PASS: health, authentication, RBAC, ML predictions, database API and refresh')
