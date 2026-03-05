# my-diary

Automated daily scribe — collects activity from multiple sources, synthesizes a coherent diary entry using Claude, and saves it in three places.

## How it works

```
Collectors (async, parallel)  →  Claude CLI (AI synthesis)  →  Writers (parallel)
├── Linear                                                    ├── output/*.md
├── GitLab                                                    ├── Obsidian vault
├── Notion                                                    └── Notion database
├── Slack
├── Gmail
├── Google Calendar
├── Google Drive
├── Local Git (all repos)
├── Terminal (~/.zsh_history)
├── Filesystem (changed files)
└── Weather (Open-Meteo)
```

Graceful degradation — if a collector/writer fails, the rest keep running.

## Quick start

```bash
# Install
uv sync

# Dry-run (collect data, print raw output, no AI)
uv run python -m my_diary --dry-run

# Full run
uv run python -m my_diary

# Specific date
uv run python -m my_diary --date 2026-03-02

# Only selected collectors
uv run python -m my_diary --dry-run --collectors local_git,terminal,weather

# Only selected writers
uv run python -m my_diary --writers markdown,obsidian

# Retry writers (skip data collection and AI synthesis)
uv run python -m my_diary --retry-writers
uv run python -m my_diary --retry-writers --writers notion

# Verbose
uv run python -m my_diary --verbose
```

## Configuration

### Secrets (`.env`)

Copy `.env.example` → `.env` and fill in:

```bash
cp .env.example .env
```

| Variable | Where to get it |
|----------|-----------------|
| `LINEAR_API_KEY` | https://linear.app/settings/api → Personal API keys |
| `SLACK_USER_TOKEN` | Slack App with User Token (see below) |
| `NOTION_API_TOKEN` | https://www.notion.so/profile/integrations → Internal integration |

### Config (`config.yaml`)

Single file configuring collectors, writers, and synthesis. Individual collectors/writers can be disabled by setting `enabled: false`.

## Service setup

### Slack

1. Go to https://api.slack.com/apps → **Create New App** → From scratch
2. **OAuth & Permissions** → User Token Scopes, add:
   - `search:read` (required)
   - `channels:history`, `channels:read` (public channels)
   - `groups:history`, `groups:read` (private channels)
   - `im:history`, `im:read` (DMs)
   - `mpim:history`, `mpim:read` (group DMs)
   - `users:read` (name resolution)
3. **Install to Workspace** → copy **User OAuth Token** (`xoxp-...`)
4. Paste into `.env` → `SLACK_USER_TOKEN`

Minimum to get started: `search:read` — enough for the collector to work.

### Google (Calendar, Drive, Gmail)

1. https://console.cloud.google.com/ → create a project (e.g. `my-diary`)
2. **APIs & Services → Library** → enable:
   - Google Calendar API
   - Google Drive API
   - Gmail API
3. **OAuth consent screen**:
   - User type: External
   - Scopes: `calendar.readonly`, `drive.readonly`, `gmail.readonly`
   - Test users: add your email
4. **Credentials → Create → OAuth client ID** → Desktop app → **Download JSON**
5. Place the file in the project directory:
   ```bash
   cp ~/Downloads/client_secret_*.json google_credentials.json
   ```
6. First run will open a browser for authorization:
   ```bash
   uv run python -m my_diary --dry-run --collectors google_cal,google_drive,gmail
   ```
   Token is saved as `google_token.json` — subsequent runs are automatic.
   If adding a new scope, delete the old token: `rm google_token.json`

### Notion

1. https://www.notion.so/profile/integrations → create an Internal Integration
2. Copy token → `.env` → `NOTION_API_TOKEN`
3. In Notion: go to a page/database → **...** → **Connections** → add your integration
4. **Writer**: create a "Daily Diary" database (Name/title column is enough — missing Date and Tags columns will be added automatically)
5. Copy the database ID from the URL — it's the first part of the path, **not** the `v=` parameter:
   ```
   https://www.notion.so/workspace/XXXXXXX?v=YYYYYYY
                                  ^^^^^^^^ this is the database_id
   ```
   Paste into `config.yaml`:
   ```yaml
   writers:
     notion:
       database_id: "XXXXXXX"
   ```

### Linear

1. https://linear.app/settings/api → **Personal API keys** → create a key
2. Paste into `.env` → `LINEAR_API_KEY`

### GitLab

Requires `glab` CLI installed and authenticated:
```bash
glab auth login
```

## Re-run logic

Re-running for the same date **updates** existing notes:

| Writer | Re-run behavior |
|--------|-----------------|
| **Markdown** | Overwrites the file |
| **Obsidian** | Replaces the auto-generated section (between `%% AUTO-GENERATED-START/END %%` markers), manual notes outside markers are preserved |
| **Notion** | If auto-generated page → deletes blocks and inserts new ones. If manual page → appends at the end |

`--retry-writers` lets you re-run writers without re-collecting data or re-running AI synthesis (uses cache from `output/.cache/`).

## Scheduling (systemd timer)

Automatic daily run at 23:00 (`Persistent=true` — if the computer was off, it runs on next boot):

```bash
./scheduling/install.sh
```

Check status:
```bash
systemctl --user status my-diary.timer
journalctl --user -u my-diary.service -n 50
```

## AI synthesis

Uses `claude -p` CLI in non-interactive mode (uses existing Claude subscription, no additional costs). The prompt instructs the model to write in Polish, rely solely on provided data, and return structured JSON.

## Project structure

```
src/my_diary/
├── cli.py                  # --date, --dry-run, --collectors, --writers, --retry-writers, --verbose
├── config.py               # YAML + .env (pydantic-settings)
├── models.py               # CollectorResult, DiaryEntry, PipelineResult
├── pipeline.py             # Orchestrator: collect → synthesize → write (+ cache)
├── collectors/             # 11 collectors (async, parallel)
│   ├── base.py             # ABC with safe_collect() (graceful degradation)
│   ├── local_git.py        # git log across all local repos
│   ├── terminal.py         # ~/.zsh_history
│   ├── filesystem.py       # Changed files
│   ├── weather.py          # Open-Meteo API
│   ├── gitlab.py           # glab api subprocess
│   ├── linear.py           # GraphQL API
│   ├── notion.py           # REST API
│   ├── slack.py            # Slack Web API
│   ├── gmail.py            # Gmail API
│   ├── google_cal.py       # Calendar API v3
│   └── google_drive.py     # Drive API v3
├── synthesis/
│   ├── engine.py           # claude -p CLI invocation
│   └── prompts.py          # System/user prompt templates
├── writers/
│   ├── base.py             # ABC
│   ├── markdown.py         # output/*.md (Jinja2)
│   ├── obsidian.py         # Obsidian vault + frontmatter + update
│   └── notion.py           # Notion database + update-or-create
└── auth/
    └── google_oauth.py     # Google OAuth2 flow + token refresh
```
