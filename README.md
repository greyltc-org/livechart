# python-live-chart
Real time data plotting (in the terminal) with python
[![asciicast](https://asciinema.org/a/327214.svg)](https://asciinema.org/a/327214)

## Getting Started
```bash
python -m venv lc_venv --system-site-packages
source lc_venv/bin/activate
python -m pip install --editable git+https://github.com/greyltc-org/livechart.git#egg=livechart
livechart

# and when you want to be done with the virtual environment:
deactivate
```

## Build
```
python -m build --wheel
#python -m build --wheel --no-isolation
```

## Install
```
python -m installer --destdir="./someplace" dist/*.whl
```
one time setup for GSettings  
```
sudo cp gsettings/* /usr/share/glib-2.0/schemas/
sudo glib-compile-schemas /usr/share/glib-2.0/schemas/
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
```
## Combo
```
rm -rf someplace/; rm -rf dist/; python -m build --wheel --no-isolation; python -m installer --destdir="./someplace" dist/*.whl
```
