# Testing Guide

## Local test

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run with default themes:

```bash
python run_pipeline.py --out-dir outputs
```

3. Verify generated files:

- `outputs/latest_news_YYYY-MM-DD.md`
- `outputs/[theme]_youtube.md`
- `outputs/[theme]_medium.md`
- `outputs/[theme]_substack.md`
- `outputs/[theme]_blogs.md`
- `outputs/[theme]_gold.md`

## Local test with one topic

```bash
python run_pipeline.py --themes "embedded linux career roadmap" --out-dir outputs
```

## GitHub Actions manual test

1. Push branch to GitHub.
2. Open **Actions** -> **Daily Research Miner**.
3. Click **Run workflow**.
4. Confirm workflow success.
5. Confirm commit from `github-actions[bot]` updates files in `outputs/`.

## Notes

- This pipeline uses DuckDuckGo HTML search results and can be affected by layout/rate-limit changes.
- For stronger YouTube coverage later, we can add YouTube Data API support as optional mode.
