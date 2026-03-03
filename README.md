# my-diary

Automatyczny skryba dzienny — zbiera aktywność z wielu źródeł, syntetyzuje spójną notatkę za pomocą Claude i zapisuje ją w trzech miejscach.

## Jak działa

```
Collectors (async, parallel)  →  Claude CLI (synteza AI)  →  Writers (parallel)
├── Linear                                                    ├── output/*.md
├── GitLab                                                    ├── Obsidian vault
├── Notion                                                    └── Notion database
├── Slack
├── Gmail
├── Google Calendar
├── Google Drive
├── Local Git (wszystkie repo)
├── Terminal (~/.zsh_history)
├── Filesystem (zmienione pliki)
└── Weather (Open-Meteo)
```

Graceful degradation — jeśli collector/writer padnie, reszta działa dalej.

## Szybki start

```bash
# Instalacja
uv sync

# Dry-run (zbiera dane, drukuje surowy output, bez AI)
uv run python -m my_diary --dry-run

# Pełne uruchomienie
uv run python -m my_diary

# Konkretna data
uv run python -m my_diary --date 2026-03-02

# Tylko wybrane collectory
uv run python -m my_diary --dry-run --collectors local_git,terminal,weather

# Tylko wybrane writery
uv run python -m my_diary --writers markdown,obsidian

# Retry writerów (bez ponownego zbierania danych i syntezy AI)
uv run python -m my_diary --retry-writers
uv run python -m my_diary --retry-writers --writers notion

# Verbose
uv run python -m my_diary --verbose
```

## Konfiguracja

### Sekrety (`.env`)

Skopiuj `.env.example` → `.env` i uzupełnij:

```bash
cp .env.example .env
```

| Zmienna | Skąd pobrać |
|---------|-------------|
| `LINEAR_API_KEY` | https://linear.app/settings/api → Personal API keys |
| `SLACK_USER_TOKEN` | Slack App z User Token (patrz niżej) |
| `NOTION_API_TOKEN` | https://www.notion.so/profile/integrations → Internal integration |

### Config (`config.yaml`)

Jeden plik z konfiguracją collectorów, writerów i syntezy. Poszczególne collectory/writery można wyłączyć ustawiając `enabled: false`.

## Setup poszczególnych serwisów

### Slack

1. Wejdź na https://api.slack.com/apps → **Create New App** → From scratch
2. **OAuth & Permissions** → User Token Scopes, dodaj:
   - `search:read` (wymagane)
   - `channels:history`, `channels:read` (kanały publiczne)
   - `groups:history`, `groups:read` (kanały prywatne)
   - `im:history`, `im:read` (DM)
   - `mpim:history`, `mpim:read` (grupowe DM)
   - `users:read` (resolving nazw)
3. **Install to Workspace** → skopiuj **User OAuth Token** (`xoxp-...`)
4. Wklej do `.env` → `SLACK_USER_TOKEN`

Minimum na start: `search:read` — wystarczy do działania collectora.

### Google (Calendar, Drive, Gmail)

1. https://console.cloud.google.com/ → utwórz projekt (np. `my-diary`)
2. **APIs & Services → Library** → włącz:
   - Google Calendar API
   - Google Drive API
   - Gmail API
3. **OAuth consent screen**:
   - User type: External
   - Scopes: `calendar.readonly`, `drive.readonly`, `gmail.readonly`
   - Test users: dodaj swój email
4. **Credentials → Create → OAuth client ID** → Desktop app → **Download JSON**
5. Umieść plik w katalogu projektu:
   ```bash
   cp ~/Downloads/client_secret_*.json google_credentials.json
   ```
6. Pierwsze uruchomienie otworzy przeglądarkę do autoryzacji:
   ```bash
   uv run python -m my_diary --dry-run --collectors google_cal,google_drive,gmail
   ```
   Token zapisze się jako `google_token.json` — kolejne uruchomienia są automatyczne.
   Jeśli dodajesz nowy scope, usuń stary token: `rm google_token.json`

### Notion

1. https://www.notion.so/profile/integrations → utwórz Internal Integration
2. Skopiuj token → `.env` → `NOTION_API_TOKEN`
3. W Notion: wejdź w stronę/bazę → **...** → **Connections** → dodaj swoją integration
4. **Writer**: utwórz bazę danych "Daily Diary" (kolumny Name/title wystarczy — brakujące Date i Tags zostaną dodane automatycznie)
5. Skopiuj ID bazy z URL — to pierwsza część ścieżki, **nie** parametr `v=`:
   ```
   https://www.notion.so/workspace/XXXXXXX?v=YYYYYYY
                                  ^^^^^^^^ to jest database_id
   ```
   Wklej do `config.yaml`:
   ```yaml
   writers:
     notion:
       database_id: "XXXXXXX"
   ```

### Linear

1. https://linear.app/settings/api → **Personal API keys** → utwórz klucz
2. Wklej do `.env` → `LINEAR_API_KEY`

### GitLab

Wymaga zainstalowanego i zalogowanego `glab` CLI:
```bash
glab auth login
```

## Logika re-run

Ponowne uruchomienie dla tej samej daty **aktualizuje** istniejące notatki:

| Writer | Re-run |
|--------|--------|
| **Markdown** | Nadpisuje plik |
| **Obsidian** | Podmienia sekcję auto-generated (markery `%% AUTO-GENERATED-START/END %%`), ręczne notatki poza markerami nietknięte |
| **Notion** | Jeśli auto-generated strona → kasuje bloki i wstawia nowe. Jeśli ręczna strona → dopisuje na końcu |

`--retry-writers` pozwala ponowić zapis bez ponownego zbierania danych i syntezy AI (korzysta z cache w `output/.cache/`).

## Scheduling (systemd timer)

Automatyczne uruchamianie codziennie o 23:00 (`Persistent=true` — jeśli komputer był wyłączony, uruchomi się przy następnym starcie):

```bash
./scheduling/install.sh
```

Sprawdzenie statusu:
```bash
systemctl --user status my-diary.timer
journalctl --user -u my-diary.service -n 50
```

## Synteza AI

Używa `claude -p` CLI w trybie non-interactive (korzysta z istniejącej subskrypcji Claude, bez dodatkowych kosztów). Prompt nakazuje pisać po polsku, bazować wyłącznie na dostarczonych danych i zwracać strukturalny JSON.

## Struktura projektu

```
src/my_diary/
├── cli.py                  # --date, --dry-run, --collectors, --writers, --retry-writers, --verbose
├── config.py               # YAML + .env (pydantic-settings)
├── models.py               # CollectorResult, DiaryEntry, PipelineResult
├── pipeline.py             # Orkiestrator: collect → synthesize → write (+ cache)
├── collectors/             # 11 collectorów (async, parallel)
│   ├── base.py             # ABC z safe_collect() (graceful degradation)
│   ├── local_git.py        # git log we wszystkich lokalnych repo
│   ├── terminal.py         # ~/.zsh_history
│   ├── filesystem.py       # Zmienione pliki
│   ├── weather.py          # Open-Meteo API
│   ├── gitlab.py           # glab api subprocess
│   ├── linear.py           # GraphQL API
│   ├── notion.py           # REST API
│   ├── slack.py            # Slack Web API
│   ├── gmail.py            # Gmail API
│   ├── google_cal.py       # Calendar API v3
│   └── google_drive.py     # Drive API v3
├── synthesis/
│   ├── engine.py           # Wywołanie claude -p CLI
│   └── prompts.py          # System/user prompt templates
├── writers/
│   ├── base.py             # ABC
│   ├── markdown.py         # output/*.md (Jinja2)
│   ├── obsidian.py         # Obsidian vault + frontmatter + update
│   └── notion.py           # Notion database + update-or-create
└── auth/
    └── google_oauth.py     # Google OAuth2 flow + token refresh
```
