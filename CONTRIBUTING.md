# Contributing

Thanks for helping improve on-call voice.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` for local runs. Do not commit `.env`.

## Tests

```bash
pytest
```

## Pull requests

Keep changes focused. Add or update tests when behavior changes. Open a PR against `main` with a short description of what you changed and why.
