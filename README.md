# ZipStreamer

ZipStreamer is a Python library for generating ZIP files on-the-fly with ZIP
file size information.

This library was implemented using logic from Python's `zipfile` library and
Golang's `archive/zip` library.

```python
z = ZipStream(files=[
    ZipFile('file.txt', 4, lambda: StringIO('test'), None, None),
    ZipFile('emptydir/', None, None, None, None),
    ZipFile('dir/remote.txt', remote_file_size, get_remote_file, None, None),
])

size = z.size()

res = Response(z.generate(), mimetype='application/zip')
res.headers['Content-Length'] = str(size)
```

## Installation

```
pip install zipstreamer
```

## Examples

```
pip install flask requests
PYTHONPATH=. FLASK_APP=examples/flask_example.py flask run
```

## Testing

```
pipenv install --dev --skip-lock
pipenv run nosetests
```

Testing multiple versions:

```
pip install pyenv tox tox-pyenv
pyenv install 2.7.14
pyenv install 3.4.8
pyenv install 3.5.5
pyenv install 3.6.4
pyenv install 3.7-dev
pyenv local 2.7.14 3.4.8 3.5.5 3.6.4 3.7-dev
tox
```
