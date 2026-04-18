import urllib.request
import sys

try:
    resp = urllib.request.urlopen('http://localhost:5002/')
    print('✅ 服务正常')
    print('状态码:', resp.status)
    content = resp.read()
    print('页面大小:', len(content), 'bytes')
except Exception as e:
    print('❌ 连接失败:', e)
    sys.exit(1)
