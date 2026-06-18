# Launch Tracker

A lightweight, self-updating launch tracker hosted on GitHub Pages. Uses a GitHub Actions workflow to keep itself up to date.

## Static API

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

[The Space Devs Launch Library 2](https://thespacedevs.com/llapi) - free, no API key required.
