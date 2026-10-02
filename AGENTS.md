# AGENTS.md

## Commands

- **Tests:** `uv run --with pytest pytest -q`
  `--with pytest` is required. pytest is deliberately not a project dependency
  (see the comment in `pyproject.toml`), so plain `uv run pytest` falls back to
  whatever interpreter is on `PATH` — which has no `aiogram` and none of the
  other project packages, and the bot tests then fail to import.
- **Frontend lint:** `npm run lint` in `frontend/` — baseline is **49 problems
  (3 errors, 46 warnings)**; keep it there, don't add to it.
- **Frontend type-check:** `npm run type-check` in `frontend/` — must be clean.
- **ruff** is installed but not configured for this repo (no `[tool.ruff]`),
  and its default rules report ~650 pre-existing hits. Ignore it.

## Ground rules

- Never run `docker compose down/up/restart`. Never edit `.env`. No changes to
  `Dockerfile`, `docker-compose.yml`, `install.sh`, `entrypoint.sh`, or
  `.github/`.
- SQLite schema changes only as idempotent `CREATE TABLE IF NOT EXISTS` /
  `_ensure_column` calls inside `backend/bot/db.py` → `init_db()`. No alembic.
- Bot behaviour is configured through `backend/utils/settings_store.py` →
  `DEFAULTS`, never through new deployment env vars.
- Several commits with one-line subjects; push once, at the end.
- Bot copy lives in `backend/bot/texts.py` (Persian, HTML `<b>` tags); every new
  reply-keyboard label must also be added to `ALL_MENU_TEXTS` in
  `backend/bot/nav.py`.
