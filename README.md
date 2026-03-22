# 🚀 LAUNCH VECTOR — Auto-Updating Rocket Launch Tracker

A lightweight, self-updating launch tracker hosted entirely on **GitHub Pages**, powered by a single **GitHub Actions** workflow. No server, no database, no paid APIs, no external dispatcher.

## How it works

One script. One workflow. Runs every 30 minutes.

```
┌─────────────────────────────────────────────────────────┐
│  sync-launches.yml  (every 30 min)                      │
│                                                         │
│  python scripts/sync_launches.py                        │
│    1. Fetch upcoming launches from LL2 API              │
│    2. Upsert into site/launches.json                    │
│    3. Re-fetch any launch past its NET                  │
│       but within the 6h recheck window                  │
│    4. Mark success / failure / partial_failure          │
│       once a terminal status is seen                    │
│    5. Commit + push → triggers Pages deploy             │
└─────────────────────────────────────────────────────────┘
```

No dispatcher, no pending_rechecks queue, no separate recheck workflow.

## Setup

1. Push this code to a new GitHub repo
2. **Settings → Pages → Source: GitHub Actions**
3. **Settings → Actions → General → Workflow permissions → Read and write permissions**
4. **Actions → Sync Launches → Run workflow** (to seed initial data)

## Structure

```
├── .github/workflows/
│   ├── sync-launches.yml    # The only workflow (runs every 30 min)
│   └── deploy-pages.yml     # Deploys site/ to GH Pages on push
├── scripts/
│   └── sync_launches.py     # The only script (stdlib only, no pip needed)
└── site/
    ├── index.html
    └── launches.json        ← live API, served at your Pages root URL
```

## API shape

`GET /launches.json`

```json
{
  "last_updated": "2025-06-01T08:00:00+00:00",
  "launches": [
    {
      "id": "abc-123",
      "name": "Falcon 9 | Starlink Group 10-1",
      "net": "2025-06-02T12:00:00Z",
      "outcome": null,
      "failure_reason": null,
      ...
    }
  ]
}
```

`outcome` is `null` (upcoming), `"success"`, `"failure"`, `"partial_failure"`, or `"unknown"` (past 6h window, no result seen).

## Data source

[The Space Devs Launch Library 2](https://thespacedevs.com/llapi) — free, no API key required.

## License

MIT
