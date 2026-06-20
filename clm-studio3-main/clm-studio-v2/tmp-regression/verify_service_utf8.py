import json
import urllib.request

BASE = 'http://127.0.0.1:8201'
NEW_TITLE = '資安回歸修復中文服務'
NEW_DESC = '中文服務修復後再次儲存測試'

req = urllib.request.Request(BASE + '/api/admin/login', method='POST', headers={'X-Admin-Token': 'temp-secure-token'})
with urllib.request.urlopen(req) as r:
    cookie = r.headers.get('set-cookie', '').split(';', 1)[0]
    csrf = json.loads(r.read().decode('utf-8'))['csrf_token']

with urllib.request.urlopen(BASE + '/api/site') as r:
    site = json.loads(r.read().decode('utf-8'))

print('BEFORE', json.dumps(site['services']['zh'][0], ensure_ascii=False))
site['services']['zh'][0]['title'] = NEW_TITLE
site['services']['zh'][0]['description'] = NEW_DESC

req = urllib.request.Request(
    BASE + '/api/admin/site',
    method='POST',
    headers={
        'Cookie': cookie,
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
    },
    data=json.dumps(site, ensure_ascii=False).encode('utf-8'),
)
with urllib.request.urlopen(req) as r:
    print('SAVE', r.status, r.read().decode('utf-8'))

with urllib.request.urlopen(BASE + '/api/site') as r:
    updated = json.loads(r.read().decode('utf-8'))
print('AFTER', json.dumps(updated['services']['zh'][0], ensure_ascii=False))
