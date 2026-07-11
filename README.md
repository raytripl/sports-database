# Raymond Sports Database

Automated multi-sport database for sports analytics and prop research.

## Sports

- MLB
- WNBA
- NBA
- NFL
- NHL
- NCAAB
- NCAAF
- Tennis
- Soccer
- Golf
- MMA
- NASCAR

## Run with Git Bash

Update everything:

```bash
./update.sh all
```

Update one sport:

```bash
./update.sh mlb
```

Run directly through Python:

```bash
python update_all.py --sport wnba
```

## Run from GitHub

1. Open the repository.
2. Select **Actions**.
3. Select **Update Sports Database**.
4. Select **Run workflow**.
5. Choose one sport or `all`.
