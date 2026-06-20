import json
import urllib.request
from pathlib import Path

BASE = 'http://127.0.0.1:8201'
SITE_FILE = Path(r'C:\Users\cl201\Downloads\clm-studio3-main\clm-studio3-main\clm-studio3-main\clm-studio-v2\data\site.json')
EXPECTED_TITLE = '繁體中文服務內容儲存測試'
EXPECTED_DESC = '這是一段確認 UTF-8 不會被污染的中文描述。'

api_data = json.loads(urllib.request.urlopen(BASE + '/api/site').read().decode('utf-8'))
file_data = json.loads(SITE_FILE.read_text(encoding='utf-8'))

api_title = api_data['services']['zh'][0]['title']
api_desc = api_data['services']['zh'][0]['description']
file_title = file_data['services']['zh'][0]['title']
file_desc = file_data['services']['zh'][0]['description']

print('API_TITLE_MATCH', api_title == EXPECTED_TITLE)
print('API_DESC_MATCH', api_desc == EXPECTED_DESC)
print('FILE_TITLE_MATCH', file_title == EXPECTED_TITLE)
print('FILE_DESC_MATCH', file_desc == EXPECTED_DESC)
print('API_TITLE_CODEPOINTS_MATCH', [ord(c) for c in api_title] == [ord(c) for c in EXPECTED_TITLE])
print('FILE_TITLE_CODEPOINTS_MATCH', [ord(c) for c in file_title] == [ord(c) for c in EXPECTED_TITLE])
