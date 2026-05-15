# Deployment — Streamlit Community Cloud

The Apex Console is a Streamlit app, so the simplest cloud target is
**Streamlit Community Cloud** (free, official). Vercel does **not** support
Streamlit because Vercel's Python runtime is serverless (≤60 s per request);
Streamlit needs a persistent process with WebSockets.

## Prerequisites

- A GitHub account (the repo can be private if you have Streamlit Cloud's
  paid plan; otherwise public).
- An Anthropic API key (needed by the Agents page; everything else works
  without it).

## Five-minute deploy

1. **Push to GitHub.**

   ```bash
   git init
   git add -A
   git commit -m "Black Orca Apex platform + console"
   gh repo create blackorca-apex --public --source . --remote origin --push
   # or, manual:
   #   git remote add origin git@github.com:<you>/<repo>.git
   #   git push -u origin main
   ```

   `.env` is gitignored — verify with `git status --ignored | grep .env`.

2. **Connect Streamlit Cloud.**
   - Go to <https://share.streamlit.io>.
   - Sign in with GitHub.
   - Click **New app**.
   - Repo: `<you>/<repo>`. Branch: `main`. **Main file path:**
     `streamlit_app.py`.
   - Click **Advanced settings**:
     - Python version: `3.12`.
     - Add secrets (TOML format) with at least:

       ```toml
       ANTHROPIC_API_KEY = "sk-ant-..."
       ALPHA_VANTAGE_API_KEY = "..."
       BLACKORCA_PROFILE = "paper"
       ```

   - Click **Deploy**. First build ~3-5 min; subsequent restarts ~30 s.

3. **Verify.** Streamlit gives you a URL like
   `https://blackorca-apex.streamlit.app`. The Home page should render
   with system metrics. Visit `/Agents` and click **Generate hypothesis** —
   that smoke-tests the Anthropic key.

## Secrets reference

| Variable                | Required? | Used by                          |
|-------------------------|-----------|----------------------------------|
| `ANTHROPIC_API_KEY`     | yes       | Agents page (hypothesis / review)|
| `ALPHA_VANTAGE_API_KEY` | optional  | Fundamentals fetcher             |
| `DATABENTO_API_KEY`     | optional  | Databento market data adapter    |
| `ALPACA_API_KEY`        | optional  | Paper trading page               |
| `ALPACA_API_SECRET`     | optional  | Paper trading page               |
| `EXA_API_KEY`           | optional  | (reserved for news enrichment)   |
| `FIRECRAWL_API_KEY`     | optional  | (reserved for news enrichment)   |
| `BLACKORCA_PROFILE`     | yes       | `dev` / `paper` / `live`         |

Paste them in the Streamlit Cloud **Advanced settings → Secrets** form as TOML.

## What works on Cloud / what doesn't

| Page              | On Cloud | Notes                                                                |
|-------------------|----------|----------------------------------------------------------------------|
| Home              | ✅       | Fully working                                                        |
| Data Catalog      | ✅       | Ingest writes to the Cloud sandbox FS, **does not persist** across restarts |
| Universe          | ✅       | Static data                                                          |
| Research          | ✅       | Needs ingested data first                                            |
| Backtest          | ✅       | Same caveat — ingest first                                           |
| ML Pipeline       | ✅       | LightGBM works on Linux containers                                   |
| Agents            | ✅       | Needs `ANTHROPIC_API_KEY`                                            |
| Risk              | ✅       | Pure compute                                                         |
| Paper Trading     | ⚠️       | Subprocess works but isn't suitable for production paper trading from a free serverless sandbox. Use a VPS for real paper. |
| Tests             | ⚠️       | Can run pytest but Cloud's I/O sandbox may reject some integration tests |
| Logs & Metrics    | ⚠️       | Prometheus + Grafana not reachable from inside Cloud                  |

## Alternative: Hugging Face Spaces

If you'd rather not depend on Streamlit Cloud, **HF Spaces** supports
Streamlit natively (free CPU tier). Use the same `streamlit_app.py` and a
`requirements.txt`, plus a `Spacefile` (one-line). Same deploy model.

## Persistent paper trading

For real paper trading the right home is a small **VPS** (Fly.io, Hetzner,
DigitalOcean, an EC2 t4g.small). Deploy:

```bash
docker build -t blackorca .
docker run -d --name blackorca --env-file .env -p 8501:8501 blackorca \
    sh -c "streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0"
```

This is the production path once we move off paper.
