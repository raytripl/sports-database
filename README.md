# Multi-Sport Automatic Database

Sports included:

- Tennis (ATP + WTA)
- CS2
- Soccer
- NFL
- NBA

The project stores normalized data in SQLite and exports CSV files for analysis.

## Data sources

- Tennis: Jeff Sackmann ATP/WTA GitHub repositories
- NBA: `nba_api`
- NFL: `nfl_data_py`
- Soccer: football-data.org API
- CS2: PandaScore API

## 1. Install

```bash
git clone YOUR_REPOSITORY_URL
cd sports_database

python -m venv .venv
source .venv/Scripts/activate   # Git Bash on Windows
# Windows Command Prompt: .venv\Scripts\activate
# PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## 2. Add API keys

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Add your keys:

```env
FOOTBALL_DATA_TOKEN=your_soccer_key
PANDASCORE_TOKEN=your_cs2_key
```

Do not commit `.env`.

For GitHub Actions, create repository secrets:

- `FOOTBALL_DATA_TOKEN`
- `PANDASCORE_TOKEN`

Go to:

`GitHub repository > Settings > Secrets and variables > Actions > New repository secret`

## 3. Run updates locally

Update every sport:

```bash
python update_all.py
```

Update one sport:

```bash
python update_all.py --sport tennis
python update_all.py --sport cs2
python update_all.py --sport soccer
python update_all.py --sport nfl
python update_all.py --sport nba
```

## 4. Database

SQLite database:

```text
data/sports.db
```

CSV exports:

```text
data/exports/
```

## 5. Automatic GitHub updates

The workflow runs every day and commits changed database/CSV files.

Manual run:

`GitHub > Actions > Update Sports Database > Run workflow`

## Important

Free public sources can change, rate-limit, or temporarily block requests. The updater logs each sport separately so one failed sport does not prevent every other sport from updating.
