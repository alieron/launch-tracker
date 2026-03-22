#!/usr/bin/env python3
"""
sync_launches.py
Runs every 30 minutes via GitHub Actions.

For upcoming launches:  fetches the latest list and upserts them.
For in-window launches: re-fetches the individual record to get live status.
For concluded launches: marks outcome (success / failure / partial_failure)
                        and keeps them in the history forever.
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_FILE = Path("site/launches.json")
LL2_BASE = "https://ll.thespacedevs.com/2.2.0"
UA = "LaunchVector/1.0 (github-actions)"

# How far past NET we keep re-fetching a launch looking for a final outcome
RECHECK_WINDOW_HOURS = 6

# LL2 status IDs
STATUS_GO = 1
STATUS_TBD = 2
STATUS_SUCCESS = 3
STATUS_FAILURE = 4
STATUS_HOLD = 5
STATUS_IN_FLIGHT = 6
STATUS_PARTIAL_FAILURE = 7
STATUS_TBC = 8
TERMINAL = {STATUS_SUCCESS, STATUS_FAILURE, STATUS_PARTIAL_FAILURE}


# ── HTTP helpers ─────────────────────────────────────────────────────────────


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ── Data helpers ─────────────────────────────────────────────────────────────


def load() -> dict:
    if not DATA_FILE.exists():
        return {"launches": [], "last_updated": None}
    return json.loads(DATA_FILE.read_text())


def save(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(json.dumps(data, indent=2))
    print(f"  → saved {DATA_FILE}")


def dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ── Normalisers ───────────────────────────────────────────────────────────────


def norm_status(raw: dict) -> dict:
    s = raw.get("status") or {}
    return {
        "id": s.get("id"),
        "abbrev": s.get("abbrev"),
        "name": s.get("name"),
        "description": s.get("description"),
    }


def norm_launch(raw: dict, existing: dict | None = None) -> dict:
    cfg = (raw.get("rocket") or {}).get("configuration") or {}
    mission = raw.get("mission") or {}
    pad = raw.get("pad") or {}
    pad_loc = pad.get("location") or {}
    provider = raw.get("launch_service_provider") or {}

    record = {
        "id": raw["id"],
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "status": norm_status(raw),
        "net": raw.get("net"),
        "window_start": raw.get("window_start"),
        "window_end": raw.get("window_end"),
        "probability": raw.get("probability"),
        "rocket": {
            "name": cfg.get("name"),
            "family": cfg.get("family"),
            "manufacturer": (cfg.get("manufacturer") or {}).get("name"),
            "image_url": cfg.get("image_url"),
        },
        "mission": {
            "name": mission.get("name"),
            "description": mission.get("description"),
            "type": mission.get("type"),
            "orbit": (mission.get("orbit") or {}).get("name"),
        },
        "pad": {
            "name": pad.get("name"),
            "location": pad_loc.get("name"),
            "country": pad_loc.get("country_code"),
            "latitude": pad.get("latitude"),
            "longitude": pad.get("longitude"),
        },
        "agency": {
            "name": provider.get("name"),
            "abbrev": provider.get("abbrev"),
            "type": provider.get("type"),
        },
        "image_url": raw.get("image"),
        "vidURLs": [
            {"title": v.get("title"), "url": v.get("url")}
            for v in (raw.get("vidURLs") or [])
        ],
        "webcast_live": raw.get("webcast_live"),
        # Our metadata — preserve if already set
        "discovered_at": (existing or {}).get("discovered_at"),
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "outcome": (existing or {}).get("outcome"),
        "failure_reason": (existing or {}).get("failure_reason"),
        "status_history": (existing or {}).get("status_history", []),
    }

    if not record["discovered_at"]:
        record["discovered_at"] = datetime.now(timezone.utc).isoformat()

    # Track status / NET changes for the activity feed
    new_sid = (raw.get("status") or {}).get("id")
    new_abbrev = (raw.get("status") or {}).get("abbrev")
    new_net = raw.get("net")
    history = record["status_history"]
    last = history[-1] if history else {}

    status_changed = last.get("status_id") != new_sid
    net_changed = bool(history) and last.get("net") != new_net

    if not history or status_changed or net_changed:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "status_id": new_sid,
            "abbrev": new_abbrev,
            "net": new_net,
        }
        if net_changed and last.get("net"):
            entry["prev_net"] = last["net"]
        if status_changed and last.get("abbrev"):
            entry["prev_abbrev"] = last["abbrev"]
        history.append(entry)
        record["status_history"] = history[-20:]

    return record


def apply_outcome(record: dict, raw: dict) -> dict:
    """Set outcome fields based on live LL2 status. Returns updated record."""
    status_id = (raw.get("status") or {}).get("id")

    if status_id == STATUS_SUCCESS:
        record["outcome"] = "success"
        print(f"  * SUCCESS: {record['name']}")

    elif status_id == STATUS_FAILURE:
        record["outcome"] = "failure"
        record["failure_reason"] = (
            raw.get("failreason")
            or (raw.get("status") or {}).get("description")
            or "No reason provided"
        )
        print(f"  ! FAILURE: {record['name']} — {record['failure_reason']}")

    elif status_id == STATUS_PARTIAL_FAILURE:
        record["outcome"] = "partial_failure"
        record["failure_reason"] = (
            raw.get("failreason")
            or (raw.get("status") or {}).get("description")
            or "Partial failure — no details"
        )
        print(f"  # PARTIAL FAILURE: {record['name']}")

    return record


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    now = datetime.now(timezone.utc)
    data = load()
    existing_map: dict[str, dict] = {l["id"]: l for l in data.get("launches", [])}

    # ── 1. Fetch upcoming launches and upsert ────────────────────────────────
    print("Fetching upcoming launches…")
    upcoming_raw = get(f"{LL2_BASE}/launch/upcoming/?limit=25&mode=detailed").get(
        "results", []
    )
    print(f"  {len(upcoming_raw)} results")

    incoming_ids = set()
    for raw in upcoming_raw:
        lid = raw["id"]
        incoming_ids.add(lid)
        record = norm_launch(raw, existing_map.get(lid))

        # If we already have a terminal outcome, don't overwrite it
        if existing_map.get(lid, {}).get("outcome") in (
            "success",
            "failure",
            "partial_failure",
        ):
            record = apply_outcome(
                record, raw
            )  # will be a no-op if LL2 still shows terminal
        else:
            record = apply_outcome(record, raw)

        if lid not in existing_map:
            print(f"  + New launch: {record['name']} (NET {record['net']})")
        existing_map[lid] = record

    # ── 2. Re-check launches that are past their NET but not yet concluded ───
    print("Checking in-window launches…")
    recheck_cutoff = now - timedelta(hours=RECHECK_WINDOW_HOURS)

    for lid, record in list(existing_map.items()):
        # Skip if already concluded or in the fresh upcoming batch
        if record.get("outcome") in ("success", "failure", "partial_failure"):
            continue
        if lid in incoming_ids:
            continue

        net = dt(record.get("net"))
        if net and recheck_cutoff <= net <= now:
            # Launch window — fetch individual record for live status
            print(f"  * Rechecking: {record['name']}")
            try:
                raw = get(f"{LL2_BASE}/launch/{lid}/?mode=detailed")
                updated = norm_launch(raw, record)
                updated = apply_outcome(updated, raw)
                existing_map[lid] = updated
            except Exception as exc:
                print(f"    Recheck failed: {exc}", file=sys.stderr)

        elif net and net < recheck_cutoff and not record.get("outcome"):
            # Past the recheck window with no outcome — mark as unknown
            record["outcome"] = "unknown"
            record["failure_reason"] = (
                "Outcome could not be determined within the recheck window"
            )
            existing_map[lid] = record
            print(f"  ? Unknown outcome (past window): {record['name']}")

    # ── 3. Prune concluded launches older than 6 months ──────────────────────
    cutoff_6mo = now - timedelta(days=183)
    concluded = {"success", "failure", "partial_failure", "unknown"}
    before = len(existing_map)
    existing_map = {
        lid: r
        for lid, r in existing_map.items()
        if not (
            r.get("outcome") in concluded
            and dt(r.get("net") or r.get("discovered_at")) is not None
            and dt(r.get("net") or r.get("discovered_at")) < cutoff_6mo
        )
    }
    pruned = before - len(existing_map)
    if pruned:
        print(f"  x Pruned {pruned} concluded launch(es) older than 6 months")

    # ── 4. Sort and save ─────────────────────────────────────────────────────
    data["launches"] = sorted(
        existing_map.values(),
        key=lambda l: l.get("net") or "",
        reverse=True,
    )
    save(data)
    print(f"Done. {len(data['launches'])} launches in record.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
