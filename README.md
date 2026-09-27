# On-call

Something breaks. This calls you, tells you what failed, and runs the fix when you say yes. Then it texts you.

## Demo

[Preview](assets/demo-preview.mp4)

[Full video](https://drive.google.com/drive/home)

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn oncall.app:build_default_app --factory --host 0.0.0.0 --port 8000
```

Demo page: http://127.0.0.1:8000/demo
