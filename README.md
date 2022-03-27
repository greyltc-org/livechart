# python-live-chart
Real time data plotting (in the terminal) with python
[![asciicast](https://asciinema.org/a/327214.svg)](https://asciinema.org/a/327214)

## Build
```
python -m build --wheel
#python -m build --wheel --no-isolation
```

## Install
```
python -m installer --destdir="./someplace" dist/*.whl
```

## Test
### Manually
```
PYTHONPATH=someplace/usr/lib/python3.10/site-packages ./someplace/usr/bin/livechart-cli
#PYTHONPATH=someplace/usr/lib/python3.10/site-packages ./someplace/usr/bin/livechart
```
### With unittest
```
# (from the project root)
PYTHONPATH="src" python -m unittest -v

# with code coverage report
PYTHONPATH="src" coverage run --source livechart -m unittest -v; coverage report

## Combo
```
rm -rf someplace/; rm -rf dist/; python -m build --wheel; python -m installer --destdir="./someplace" dist/*.whl
```
