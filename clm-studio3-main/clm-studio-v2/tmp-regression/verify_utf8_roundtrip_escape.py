import json
import urllib.request
from pathlib import Path

BASE = 'http://127.0.0.1:8201'
SITE_FILE = Path(r'C:\Users\cl201\Downloads\clm-studio3-main\clm-studio3-main\clm-studio3-main\clm-studio-v2\data\site.json')
NEW_TITLE = '\u7e41\u9ad4\u4e2d\u6587\u670d\u52d9\u5167\u5bb9\u5132\u5b58\u6e2c\u8a66'
NEW_DESC = '\u9019\u662f\u4e00\u6bb5\u78ba\u8a8d UTF-8 \u4e0d\u6703\u88ab\u6c61\u67d3\u7684\u4e2d\u6587\u63cf\u8ff0\u3002'

req = urllib.request.Request(BASE + '/api/admin/login', method='POST', headers={'X-Admin-Token': 'temp-secure-token'})
with urllib.request.urlopen(req) as r:
    cookie = r.headers.get('set-cookie', '').split(';', 1)[0]
    csrf = json.loads(r.read().decode('utf-8'))['csrf_token']

with urllib.request.urlopen(BASE + '/api/site') as r:
    site = json.loads(r.read().decode('utf-8'))

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
    save_body = r.read().decode('utf-8')

api_data = json.loads(urllib.request.urlopen(BASE + '/api/site').read().decode('utf-8'))
file_data = json.loads(SITE_FILE.read_text(encoding='utf-8'))

print('SAVE_BODY', save_body)
print('API_VALUE', json.dumps(api_data['services']['zh'][0], ensure_ascii=False))
print('FILE_VALUE', json.dumps(file_data['services']['zh'][0], ensure_ascii=False))
print('API_MATCH', api_data['services']['zh'][0]['title'] == NEW_TITLE and api_data['services']['zh'][0]['description'] == NEW_DESC)
print('FILE_MATCH', file_data['services']['zh'][0]['title'] == NEW_TITLE and file_data['services']['zh'][0]['description'] == NEW_DESC)
