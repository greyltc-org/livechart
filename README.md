# python-live-chart
Real time data plotting (in the terminal) with python
[![asciicast](https://asciinema.org/a/327214.svg)](https://asciinema.org/a/327214)

## Building
### With flit
```
flit build
```

## Testing
### With unittest
```
# (from the project root)
PYTHONPATH="src" python -m unittest -v

# with code coverage report
PYTHONPATH="src" coverage run --source livechart -m unittest -v; coverage report
```
### With pytest
```
PYTHONPATH="src" python -m pytest -v --cov=livechart
```