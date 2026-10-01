# Nexra vs MIT — everything Nexra has that MIT does not

Scope: `MHBehzadian/nexra-panel` vs `Liwyd/mit-panel`, both checked out locally.

Both repos descend from **whale-panel** (`primeZdev/whale-panel`). They share 291
commits and diverged at `f395ac8` *"Nexra Panel: branding, Telegram backups, and
admin-create fix"*:

| | commits after fork | shared |
|---|---|---|
| mit-panel | 83 | 291 |
| nexra-panel | 52 | 291 |

Everything below was verified against the **net tree diff of the two HEADs**, so
a feature only appears here if MIT's working tree really lacks it (MIT ported a
number of Nexra commits under its own hashes, so commit messages alone are not
reliable).

---

## 1. Backend — API / services

### 1.1 `verify_credentials()` — unreachable ≠ wrong password
`backend/services/marzban/api.py`

Nexra splits credential checking in two:

- `verify_credentials()` — issues a real `POST /api/admin/token`; `401/403/422`
  returns `False` (credentials rejected), anything else **raises** (panel
  unreachable). Used by `/bot/admin/change-password`.
- `test_connection()` — kept for callers that genuinely cannot act on the
  difference; it now delegates to `verify_credentials()` and swallows to `False`.

MIT has **only** `test_connection()`, so a Marzban box that is down, firewalled or
502-ing is reported to the user as *"Current password is incorrect"*. This is the
single most user-visible backend difference.
(Nexra commit `66394b9` *"Stop reporting an unreachable Marzban as a wrong password"*.)

### 1.2 `get_nodes_status()` — real per-node connection status
`backend/services/marzban/api.py`

Nexra implements `GET /api/nodes` and returns `{id, name, status, message}` for
every remote node (`connected / connecting / error / disabled`).

**MIT calls this method but never defines it.** `mit-panel/backend/utils/marzban_overview.py:18`
does `await api_service.get_nodes_status()`, while `mit-panel/backend/services/marzban/api.py`
has no such method — the `AttributeError` is swallowed by `_node_statuses()`, so
in MIT **every node resolves to `"unknown"`** and the dashboard's status dot is
always grey. Nexra's node-status column therefore actually works.

### 1.3 `get_admin(username)` — targeted admin lookup
Nexra asks Marzban to filter (`GET /api/admins?username=…`) and then re-checks the
exact username, falling back to the full list for older builds. MIT iterates the
entire `get_admins()` result inline.

### 1.4 `count_online_users()` — paged instead of "download every user"
Nexra's implementation:

- pages `/api/users` with `?sort=-online_at`, `limit=200`;
- stops at the first user older than the window (newest-first ⇒ everything after
  it is older too);
- if the build rejects the `sort` field, retries the same page unsorted and falls
  back to a linear scan;
- hard cap `40 pages × 200` so a huge panel cannot stall the request.

MIT downloads the **whole** user list (`users` + every proxy, inbound and
subscription link — multi-MB on a large panel) on every call.

### 1.5 Non-blocking system info
`backend/utils/system.py`

Nexra primes `psutil.cpu_percent(interval=None)` at import time and samples with
`interval=None`, so `GET /superadmin/system` returns immediately. MIT uses
`psutil.cpu_percent(interval=1)` — it **blocks ~1 s per call**, and the
dashboard polls it continuously.

### 1.6 Partial-failure handling when provisioning a reseller
`backend/api/bot/routers.py → POST /bot/admin/create`

Nexra adds `db.rollback()` and an actionable message when Nexra's own row fails
*after* the admin was already created in Marzban:

> *"The admin was created in Marzban but could not be saved in Nexra: …. Add it
> manually in the panel, or delete it from Marzban and try again."*

It also turns the "panel reported no inbounds" branch into an explicit refusal
explaining that the new admin's users would carry no configuration. (MIT has the
same branch but a shorter message.)

### 1.7 `agent/uninstall.sh` — one-line uninstall for the monitoring agent
File exists only in Nexra:

```bash
curl -fsSL https://raw.githubusercontent.com/MHBehzadian/nexra-panel/main/agent/uninstall.sh | sudo bash
```

Stops/disables `nexra-agent`, deletes the unit, the binary and `/opt/nexra-agent`,
then `daemon-reload`.

### 1.8 Browser `User-Agent` on the agent heartbeat
`agent/main.go`

Nexra sends `Mozilla/5.0 … Chrome/124.0.0.0 Safari/537.36` instead of the default
`Go-http-client/1.1`. Several CDNs/WAFs (ArvanCloud explicitly named in the
comment) silently drop Go's UA before a response is produced, which reads as a
hung connection. MIT does not set a UA.

---

## 2. Frontend — pages and components

### 2.1 News **carousel** with banner-first rendering
`frontend/src/pages/DashboardPage.tsx` — `NewsCarousel` (Nexra-only component)

- auto-rotates every **6 s** with prev/next arrows and pill dots;
- guards against the list shrinking (resets to slide 0);
- announcement banner is **edge-to-edge**: no card frame, responsive capped
  height `h-36 → sm:h-44 → md:h-52 → lg:h-60` with `object-cover` (grows per
  breakpoint instead of a fixed aspect ratio that towers on wide screens), plus a
  pulsing skeleton while the authenticated blob fetch resolves;
- text-only announcements get a `Zap` icon and a 160 px min-height;
- the whole block has **no `Card` wrapper** on purpose.

MIT renders the same items as a static list inside a `News & Updates` card.

### 2.2 Manual **Refresh** for Marzban + system stats
`handleRefreshStats()` — Nexra-only. One button next to the Marzban heading
(`RefreshCw`, spinner while running) that calls
`getMarzbanOverview(period, force=true, includeAdmins=true)` **and**
`getSystemInfo()` in parallel, so the on-screen numbers are genuinely current
instead of waiting for the next silent poll. MIT has no manual refresh (only the
servers list has one).

### 2.3 Marzban section header (panel name + version)
Nexra shows `{{panel}} – v{{version}}` above the rings. MIT never renders
`marzban.panel` / `marzban.version`, even though the field is in both type
definitions.

### 2.4 "Nexra Panel vs Marzban-only Admins" ring
Nexra repurposes the 4th headline donut to compare how many Marzban admins have a
panel account vs. ones that exist only in Marzban. The ratio is fetched **only**
on page load / period change / manual refresh and merged into the state so the
silent 30 s poll keeps the last known value.

MIT fetches `include_admins` too, but **never displays the result** — that slot
shows "Marzban Memory" instead.

### 2.5 Admin search
`frontend/src/pages/AdminsPage.tsx`

A single search box filtering across **username, panel name and Telegram ID**,
with:

- live result count in the card description (`"12 of 34 admins"`),
- a distinct *"No admins match your search"* empty state,
- filtering applied to both the mobile card view and the desktop table.

MIT has no search on the Admins page at all.

### 2.6 `SegmentedBar` chart component
`frontend/src/components/charts/SegmentedBar.tsx` (file only in Nexra)

A dependency-free blocky meter: 22 segments, green → amber (≥75 %) → red (≥90 %),
a big tabular percentage, an optional caption, and "any non-zero value lights at
least one block". Used for the monitored servers' **Processor / Memory / Disk /
Swap**. MIT uses circular `Gauge` rings for the same four values.

### 2.7 Server list as cards
Nexra renders each monitored server as a bordered card in a 2-up `xl:grid-cols-2`
grid (MIT uses `divide-y` rows), shows the core count next to the name, and puts
the Reboot button in the card header. Metric labels are Processor / Memory / Disk
/Swap with `1.2 / 3.9 GB` spacing and `"not configured"` instead of `"None"`.

### 2.8 Sidebar: direct Finance link + a **Support** button
`frontend/src/components/Sidebar.tsx`

| | Nexra | MIT |
|---|---|---|
| Finance | `<a href="https://t.me/nexrapanelsbot">` — straight to the top-up bot | Opens a dialog that just tells you to use the bot |
| Support | **New entry** → `https://t.me/aria1060` (LifeBuoy icon) | does not exist |
| Version | not shown | `v3.3.0` footer |

### 2.9 Login page: animated aurora + forced light theme
`frontend/src/pages/LoginPage.tsx`

- three blurred `nx-aurora` blobs (46 vw / 40 vw / 34 vw, `blur(80px)`) drifting on
  20–30 s alternating keyframes, all disabled under `prefers-reduced-motion`;
- the login page is **light only**: the `dark` class is stripped on mount and
  restored on unmount, so a user with a saved dark theme still gets the light
  login;
- `overflow: hidden` on the root.

MIT's login page is static and follows the active theme.

### 2.10 Pre-paint theme script (no theme flash)
`frontend/index.html`

An inline `<script>` runs **before first paint**, reads `localStorage.theme`
(or `prefers-color-scheme`) and adds `.dark` to `<html>` — and explicitly skips
`/login`. MIT applies the theme from `useTheme`, which only mounts inside the
sidebar, so MIT flashes the wrong theme on every load and renders the login page
light/dark inconsistently.

### 2.11 Layout / shell rework
`frontend/src/App.tsx`, `frontend/src/styles/globals.css`

- **window-level scrolling** (one scrollbar at the window edge) —
  `min-h-screen` + `overflow-x-hidden`; MIT locks `html, body { height: 100%;
  overflow: hidden; }` and uses an inner scroll area with its own scrollbar;
- desktop sidebar is **`fixed inset-y-0 left-0`**, so Finance/Support/Logout stay
  pinned at the bottom of the viewport (MIT's scrolls away);
- **mobile menu is a vertical tab on the left edge** (`h-12 w-9`, `top-1/2`,
  rounded on the open side) instead of a full-width top bar — MIT loses a strip of
  every phone screen to a hamburger + title;
- **router basename normalized**:
  `import.meta.env.BASE_URL.replace(/\/+$/, '') || '/'`. Without it a bare
  `/dashboard` URL matches nothing and renders a blank page (MIT still has this
  bug — `basename={import.meta.env.BASE_URL}` keeps the trailing slash).

### 2.12 Dialogs sit inside the mobile viewport
`components/ui/dialog.tsx`, `components/ui/alert-dialog.tsx`

Nexra: `w-[calc(100%-2rem)] … p-5 sm:p-6` — dialogs never touch the screen edge
on a phone. MIT: `w-full … p-6`.

### 2.13 Admin form UX
`pages/components/AdminFormDialog.tsx`

- **auto-selects the first panel** when opening the create dialog;
- **auto-ticks every inbound** for a new admin (`selectAll = !admin`), because
  that is what is wanted nearly every time;
- **loads the inbound list when editing** an existing admin, so the saved
  selection is actually visible (MIT leaves the checkboxes blank until you
  re-pick the panel, which wipes the selection);
- label is `Traffic (GB)` (MIT: `Remaining Traffic (GB)`).

### 2.14 User form defaults
`pages/components/UserFormDialog.tsx` — Nexra defaults to `totalGb: 30`,
`expiryDatetime: 30`; MIT defaults to `0.1` / `null`, so the common case in Nexra
is a single field (username).

### 2.15 Settings → news management polish
`pages/SettingsPage.tsx`

- a `Banner` badge next to news items that carry an image;
- a **Remove** button on the banner preview (revokes the object URL);
- field label *"Message (optional if a banner is attached)"*;
- `addNews` trims the message, so banner-only announcements are valid.

### 2.16 Dashboard layout and meters

- **Nodes Usage sits in a 2/3 column beside the panel stat cards**
  (`lg:grid-cols-3`, `lg:col-span-2`) with a fallback grid when Marzban is
  unreachable; MIT puts Nodes Usage inside the Marzban block and the stat cards in
  a separate 3-column row.
- **Node status is a `Badge`** (`Connected` / `Connecting` / `Error` / `Disabled`
  / `Unknown`) matching the Active/Inactive convention; MIT uses a bare coloured
  dot.
- **"Active Users / total"** card (active count first, total as a muted suffix)
  instead of MIT's bare "Total Users" — the bare total counted disabled users.
- **`shadcn <Select>`** for the status filter instead of a native `<select>`.
- Online-users tile shows `…` + *"Counting…"* while the scan runs (MIT shows `-`).

### 2.17 Polling cadence and payload trimming
`DashboardPage.tsx`

| poll | Nexra | MIT |
|---|---|---|
| system info | **5 s** | 15 s |
| monitored servers | **10 s** | 30 s |
| Marzban overview | 30 s, `include_admins=false` | 30 s, `include_admins` only on first load |
| online count settle | **extra 5 s re-poll until the count lands** | none (blank tile for up to 30 s) |
| admin ratio | load / period change / manual refresh, merged across polls | loaded once, never rendered |

### 2.18 Panels page
The **Add Panel** button lives in the table header; MIT keeps it under the page
title.

### 2.19 `useBannerImage` correctness
Nexra resets the cached object URL to `null` when `hasBanner` flips to `false`
and derives the initial state in one expression, so a banner that disappears
never leaves a stale image on screen.

### 2.20 Colour system
`styles/globals.css`

- Nexra light: **paper-and-navy** — `--background: 220 27% 98%`,
  `--foreground: 216 49% 15%`, `--primary: 216 49% 15%`, `--ring: 217 91% 60%`,
  brand blue `217 91% 60%`, brand green `165 33% 44%`, gold `40 41% 80%`.
- Nexra dark: **deep navy** — `--background: 218 50% 6%`,
  `--card: 216 44% 12%`, `--primary: 222 78% 60%`, surface gradient
  `#172033 → #101827`.
- MIT light: **coral/red** (`0 70% 67%`), MIT dark: neutral near-black
  (`0 0% 13%`).

Also note MIT keeps `height:100%` / `overflow:hidden` on `html, body` plus a
`#root { height:100% }` rule that Nexra deletes.

---

## 3. Installer, packaging, CI, branding

| | Nexra | MIT |
|---|---|---|
| `install.sh` | original simple whale-panel script (`edit-env / update / start / stop / restart / logs / uninstall`), pulls `primezdev/whale-panel:latest`, follows `docker compose logs -f` | rewritten **ANSI TUI** + full `mit-panel` CLI (`status, settings, set-username, set-password, set-port, set-urlpath, set-bot-token, edit-env, update, uninstall, …`), git-clone based self-updating update |
| `docker-compose.yml` | `build: .`, image `nexra-panel:latest`, **no `/opt/ssl` mount** | image `liwyd/mit-panel:latest` (prebuilt pull), mounts `/opt/ssl:ro` |
| CI | `docker-release.yml` on **tags only**, pushes `primezdev/whale-panel` | `docker-release.yml` on **push to main + tags**, pushes `liwyd/mit-panel`, **plus an extra `docker.yml` workflow** |
| `pyproject.toml` | `name = "whale-panel"`, `version = "2.9.30"`, no bot deps | `name = "mit-panel"`, `version = "3.3.0"`, adds `aiogram`, `tzdata`, `[tool.pytest.ini_options]` |
| `.gitignore` | 4 fewer entries (does not ignore `node_modules/`, `dist/`) | ignores `node_modules/`, `dist/`, `frontend/node_modules/`, `frontend/dist/` |
| `agent` naming | `nexra-agent` (module, binary, systemd unit), repo `MHBehzadian/nexra-panel` | `mit-agent`, repo `liwyd/mit-panel` |
| DB file | `data/walpanel.db` | `data/mitpanel.db` |
| data dir env | `WALPANEL_DATA_DIR` | `MITPANEL_DATA_DIR` |
| FastAPI title | `WalPanel` | `MIT Panel` |
| PWA manifest / `<title>` | `nexra panel` / `Nexra Panel` | `mit panel` / `MIT Panel` |
| `frontend/package.json` name | `walpanel-frontend` | `mit-panel-frontend` |
| default `login_title` | `Nexra Panel` | `MIT Panel` |
| Telegram backup caption | `🐋 Nexra Panel backup — <stamp>` | `🐋 MIT Panel backup — <stamp>` |
| README | Telegram channel badge `@NexraTunnel`, emoji headings | one-line install + `mit-panel` CLI docs |
| `frontend/README.md` | full getting-started section | two lines |
| logos / media | `media/nexra-logo.png`, `media/whale-panel.png`, `media/ads.json` (orphan, unreferenced) | `media/mit-logo.png`, `mitvpnlogo.png`, `loginpage.png`, `panel.png` (no `ads.json` — MIT deleted the remote-ads feature) |

---

## 4. Nexra-only files

```
agent/uninstall.sh
frontend/src/components/charts/SegmentedBar.tsx
backend/alembic/versions/a1b2c3d4e5f6_add_server_sort_order.py   (layout only — see note)
```

Note on the migration: Nexra adds `servers.sort_order` in a **separate**
migration that seeds `sort_order = id`. MIT folded the same column into
`d3f8a1c2b4e6_add_servers_table.py` with `server_default=0`. Both end up with an
identical, working `sort_order` + `reorder_servers()`, so this is **not** a
feature difference.

---

## 5. Behavioural notes where MIT is ahead (for balance)

These are not Nexra features — they are MIT-only improvements you would lose by
switching:

- **Request timeouts everywhere**: MIT sets `REQUEST_TIMEOUT = 10` on *every*
  Marzban call; Nexra only sets `_request_timeout = 15` on some calls and has
  **no timeout** on `create_user`, `update_user`, `reset_user_traffic`,
  `delete_user`.
- **Concurrent-login protection**: MIT serialises logins per `(url, username)`
  with an `asyncio.Lock`; Nexra has no lock.
- **Hardened Marzban client**: MIT adds `MarzbanAPIError`, retries
  `get_inbounds()` three times, and validates `/api/users` payloads with
  `get_users_page()` / `get_all_users_paginated()` (detects ignored offsets and
  incomplete reads, caps at 500 k users). Nexra's `get_inbounds()` / `get_users()`
  are unguarded.
- **Settings cache**: MIT caches `settings.json` for 10 s (`settings_store.py`).
- **Username validation**: MIT enforces `USERNAME_REGEX` on login, admin and user
  forms (zod); Nexra only checks length.
- **`marzban_all_inbounds`** (migration `f1a2b3c4d5e6`): "select all inbounds,
  auto-sync on every login" checkbox, refreshed live at user creation and on each
  admin login.
- **`initial_traffic` / Total Quota**: MIT exposes a Total Quota field on admin
  edit and preserves/accumulates `initial_traffic` in `crud.update_admin`; Nexra
  just resets `initial_traffic = traffic` on every update.
- **`marzban_users` ledger** (migration `e5a6f7b8c9d0`) + `reduce_admin_traffic_debt()`
  + twice-daily usage sweep that bills users created outside the bot — MIT-only.
- **Embedded Telegram top-up bot**: `backend/bot/**` (≈30 modules, aiogram),
  started from `backend/app.py`, configured via `BOT_*` env vars and the
  **Top-up Bot** settings card + `/superadmin/settings/bot` GET/PUT. Shop/pricing,
  referral codes and requests, wallet, invoices, weekly consumption & delayed
  billing, tutorials, approvals, warnings, receipts, usage sync, per-Telegram
  multi-panel ownership. Nexra exposes only the **HTTP bot API**
  (`backend/api/bot/*`) for an externally hosted bot.
- **`/dashboard/version`** + version badge in Settings + version footer in the
  sidebar + `__version__` in `backend.config`.
- **`PageLayout`** component (per-page header/footer shell with inner scrolling).
- **`tests/`** (4 test files + `conftest.py`), **`scripts/reset_referral_requests.py`**,
  **`.github/workflows/docker.yml`**, **`/opt/ssl` read-only mount**,
  **`aiogram`/`tzdata` dependencies**, **`.env.example` bot block**.
- `crud.reduce_admin_traffic` clamps at 0 in MIT (Nexra lets traffic go negative).

---

## 6. One-line summary

Nexra's edge is **frontend polish and Marzban client quality**: a rotating
banner carousel, a manual refresh button, an admins-vs-Marzban ratio ring, admin
search, a segmented meter UI, a fixed sidebar with direct Finance **and Support**
links, an animated login page with a pre-paint theme script, window-level
scrolling with a fixed sidebar and an edge-mounted mobile menu, plus
`verify_credentials()` (unreachable ≠ wrong password), a working
`get_nodes_status()`, a paged online-user scan, a non-blocking system-info
endpoint and an agent uninstall script. MIT's edge is **depth of backend
feature-set**: an entire embedded Telegram bot, the Marzban users ledger and
usage sweep, all-inbounds sync, total-quota accounting, timeouts/locks/retries on
every panel call, a TUI installer with a full CLI, versioning and tests.
