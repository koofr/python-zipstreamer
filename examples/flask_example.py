# FLASK_APP=flask_example.py flask run

import sys

if sys.version_info[0] == 2:
    from StringIO import StringIO as BytesIO
else:
    from io import BytesIO

from flask import Flask, Response
import requests
from zipstreamer import ZipStream, ZipFile

app = Flask(__name__)

@app.route('/')
def download():
    remote_file_size = 1024

    def get_remote_file():
        res = requests.get('https://httpbin.org/range/%d' % remote_file_size, stream=True)
        raw = res.raw
        raw.decode_content = True
        return raw

    z = ZipStream(files=[
        ZipFile('file.txt', 4, lambda: BytesIO(b'test'), None, None),
        ZipFile('emptydir/', None, None, None, None),
        ZipFile('dir/remote.txt', remote_file_size, get_remote_file, None, None),
    ])

    size = z.size()

    res = Response(z.generate(), mimetype='application/zip')
    res.headers['Content-Disposition'] = 'attachment; filename={}'.format('files.zip')
    res.headers['Content-Length'] = str(size)

    return res
