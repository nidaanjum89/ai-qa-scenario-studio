"""Local, provider-neutral storage for saved QA project work."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SCENARIO_STUDIO_DB", ROOT / "data" / "scenario_studio.sqlite3")).expanduser()
EXPORT_FORMAT = "ai-qa-scenario-studio-memory"
EXPORT_VERSION = 1
DEFAULT_PROJECT_ID = "default"
DEFAULT_PROJECT_NAME = "QA Sample Project"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            feature TEXT NOT NULL,
            product TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            reviews_json TEXT NOT NULL,
            UNIQUE(project_id, version)
        );
        CREATE INDEX IF NOT EXISTS runs_by_project ON runs(project_id, version DESC);
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            criterion_id TEXT NOT NULL,
            status TEXT NOT NULL,
            changed_at TEXT NOT NULL
        );
        """
    )
    now = _now()
    connection.execute(
        "INSERT OR IGNORE INTO projects(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (DEFAULT_PROJECT_ID, DEFAULT_PROJECT_NAME, now, now),
    )
    connection.commit()
    return connection


@contextmanager
def _database():
    connection = _connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_projects() -> list[dict[str, Any]]:
    with _database() as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.name, p.created_at, p.updated_at,
                   COUNT(r.id) AS run_count, MAX(r.created_at) AS last_run_at
            FROM projects p LEFT JOIN runs r ON r.project_id = p.id
            GROUP BY p.id ORDER BY p.updated_at DESC, p.name COLLATE NOCASE
            """
        ).fetchall()
    return [
        {"id": row["id"], "name": row["name"], "createdAt": row["created_at"],
         "updatedAt": row["updated_at"], "runCount": row["run_count"], "lastRunAt": row["last_run_at"]}
        for row in rows
    ]


def create_project(name: str) -> dict[str, Any]:
    clean_name = str(name).strip()
    if not clean_name or len(clean_name) > 80:
        raise ValueError("Project names must be 1 to 80 characters long.")
    project_id = uuid.uuid4().hex
    now = _now()
    with _database() as connection:
        connection.execute(
            "INSERT INTO projects(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (project_id, clean_name, now, now),
        )
    return {"id": project_id, "name": clean_name, "createdAt": now, "updatedAt": now, "runCount": 0, "lastRunAt": None}


def get_project(project_id: str) -> dict[str, Any] | None:
    with _database() as connection:
        row = connection.execute("SELECT id, name, created_at, updated_at FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "name": row["name"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def save_run(project_id: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    now = _now()
    with _database() as connection:
        project = connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise ValueError("Choose a saved project before generating a plan.")
        version = connection.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM runs WHERE project_id = ?", (project_id,)).fetchone()[0]
        connection.execute(
            """INSERT INTO runs(id, project_id, version, feature, product, created_at, payload_json, result_json, reviews_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, project_id, version, str(payload.get("feature", "User journey")),
             str(payload.get("product", "Unspecified demo")), now,
             json.dumps(payload, ensure_ascii=False), json.dumps(result, ensure_ascii=False), "{}"),
        )
        connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
    return {"runId": run_id, "projectId": project_id, "version": version, "createdAt": now, "reviews": {}}


def list_runs(project_id: str) -> list[dict[str, Any]]:
    with _database() as connection:
        rows = connection.execute(
            "SELECT id, version, feature, product, created_at, result_json, reviews_json FROM runs WHERE project_id = ? ORDER BY version DESC LIMIT 100",
            (project_id,),
        ).fetchall()
    items = []
    for row in rows:
        result = json.loads(row["result_json"])
        reviews = json.loads(row["reviews_json"])
        items.append({
            "runId": row["id"], "version": row["version"], "feature": row["feature"],
            "product": row["product"], "createdAt": row["created_at"],
            "coverage": result.get("coverage", 0), "scenarioCount": len(result.get("scenarios", [])),
            "reviewedCount": sum(status == "approved" for status in reviews.values()),
        })
    return items


def get_run(run_id: str) -> dict[str, Any] | None:
    with _database() as connection:
        row = connection.execute(
            "SELECT id, project_id, version, created_at, payload_json, result_json, reviews_json FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    result = json.loads(row["result_json"])
    result["memory"] = {"runId": row["id"], "projectId": row["project_id"], "version": row["version"], "createdAt": row["created_at"]}
    return {"runId": row["id"], "projectId": row["project_id"], "version": row["version"],
            "createdAt": row["created_at"], "payload": json.loads(row["payload_json"]),
            "result": result, "reviews": json.loads(row["reviews_json"])}


def save_reviews(run_id: str, reviews: dict[str, str]) -> dict[str, str]:
    valid_statuses = {"pending", "approved", "changes"}
    with _database() as connection:
        row = connection.execute("SELECT project_id, result_json, reviews_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise ValueError("This saved plan could not be found.")
        result = json.loads(row["result_json"])
        valid_ids = {item["id"] for item in result.get("criteria", [])}
        current = json.loads(row["reviews_json"])
        updated = dict(current)
        for criterion_id, status in reviews.items():
            status = str(status)
            if criterion_id not in valid_ids:
                raise ValueError(f"Unknown acceptance criterion: {criterion_id}")
            if status not in valid_statuses:
                raise ValueError("Review status must be pending, approved, or changes.")
            if updated.get(criterion_id, "pending") != status:
                connection.execute(
                    "INSERT INTO review_history(run_id, criterion_id, status, changed_at) VALUES (?, ?, ?, ?)",
                    (run_id, criterion_id, status, _now()),
                )
            updated[criterion_id] = status
        now = _now()
        connection.execute("UPDATE runs SET reviews_json = ? WHERE id = ?", (json.dumps(updated), run_id))
        connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, row["project_id"]))
    return updated


def approved_examples(project_id: str, limit: int = 8) -> list[dict[str, Any]]:
    with _database() as connection:
        rows = connection.execute(
            """SELECT r.result_json, r.reviews_json FROM runs r
               WHERE r.project_id = ? ORDER BY r.version DESC LIMIT 40""",
            (project_id,),
        ).fetchall()
    examples: list[dict[str, Any]] = []
    for row in rows:
        result = json.loads(row["result_json"])
        reviews = json.loads(row["reviews_json"])
        criteria = {item["id"]: item["text"] for item in result.get("criteria", [])}
        for scenario in result.get("scenarios", []):
            ids = scenario.get("acceptanceIds", [])
            if not ids or not all(reviews.get(criterion_id) == "approved" for criterion_id in ids):
                continue
            examples.append({
                "feature": result.get("feature", ""),
                "criteria": [{"id": criterion_id, "text": criteria.get(criterion_id, "")} for criterion_id in ids],
                "title": scenario.get("title", ""),
                "kind": scenario.get("kind", ""),
                "steps": scenario.get("steps", [])[:6],
                "expectedResult": scenario.get("expectedResult", ""),
            })
            if len(examples) >= limit:
                return examples
    return examples


def export_project(project_id: str) -> dict[str, Any] | None:
    project = get_project(project_id)
    if not project:
        return None
    with _database() as connection:
        rows = connection.execute(
            "SELECT id, version, created_at, payload_json, result_json, reviews_json FROM runs WHERE project_id = ? ORDER BY version",
            (project_id,),
        ).fetchall()
        history_by_run: dict[str, list[dict[str, str]]] = {}
        history = connection.execute(
            "SELECT run_id, criterion_id, status, changed_at FROM review_history WHERE run_id IN (SELECT id FROM runs WHERE project_id = ?) ORDER BY id",
            (project_id,),
        ).fetchall()
    for item in history:
        history_by_run.setdefault(item["run_id"], []).append(
            {"criterionId": item["criterion_id"], "status": item["status"], "changedAt": item["changed_at"]}
        )
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exportedAt": _now(),
        "project": {"name": project["name"]},
        "runs": [
            {"version": row["version"], "createdAt": row["created_at"],
             "payload": json.loads(row["payload_json"]), "result": json.loads(row["result_json"]),
             "reviews": json.loads(row["reviews_json"]), "reviewHistory": history_by_run.get(row["id"], [])}
            for row in rows
        ],
    }


def _restore_review_history(run_id: str, history: Any) -> None:
    if not isinstance(history, list) or len(history) > 5000:
        raise ValueError("The memory file has an invalid review history.")
    with _database() as connection:
        row = connection.execute("SELECT result_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise ValueError("The imported plan could not be found.")
        valid_ids = {item["id"] for item in json.loads(row["result_json"]).get("criteria", [])}
        connection.execute("DELETE FROM review_history WHERE run_id = ?", (run_id,))
        for event in history:
            if not isinstance(event, dict):
                raise ValueError("The memory file has an invalid review event.")
            criterion_id = str(event.get("criterionId", ""))
            status = str(event.get("status", ""))
            changed_at = str(event.get("changedAt", ""))
            if criterion_id not in valid_ids or status not in {"pending", "approved", "changes"} or not changed_at or len(changed_at) > 64:
                raise ValueError("The memory file has an invalid review event.")
            connection.execute(
                "INSERT INTO review_history(run_id, criterion_id, status, changed_at) VALUES (?, ?, ?, ?)",
                (run_id, criterion_id, status, changed_at),
            )


def import_project(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("format") != EXPORT_FORMAT or bundle.get("version") != EXPORT_VERSION:
        raise ValueError("This file is not a Scenario Studio memory export we can read.")
    project_data = bundle.get("project")
    runs = bundle.get("runs")
    if not isinstance(project_data, dict) or not isinstance(runs, list) or len(runs) > 200:
        raise ValueError("The memory file has an invalid project or run list.")
    name = str(project_data.get("name", "Imported project")).strip()
    if not name or len(name) > 80:
        raise ValueError("The project name must be 1 to 80 characters long.")
    project = create_project(name[:69].rstrip() + " (imported)")
    try:
        for item in runs:
            if not isinstance(item, dict) or not isinstance(item.get("payload"), dict) or not isinstance(item.get("result"), dict):
                raise ValueError("The memory file contains an invalid saved plan.")
            result = item["result"]
            criteria = result.get("criteria", [])
            scenarios = result.get("scenarios", [])
            if not isinstance(criteria, list) or not isinstance(scenarios, list) or any(not isinstance(row, dict) or not row.get("id") for row in criteria):
                raise ValueError("The memory file has invalid criteria or scenarios.")
            payload = dict(item["payload"])
            payload["projectId"] = project["id"]
            saved = save_run(project["id"], payload, result)
            reviews = item.get("reviews", {})
            if not isinstance(reviews, dict):
                raise ValueError("The memory file has invalid review choices.")
            if reviews:
                save_reviews(saved["runId"], reviews)
            if "reviewHistory" in item:
                _restore_review_history(saved["runId"], item["reviewHistory"])
    except Exception:
        with _database() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project["id"],))
        raise
    return next(item for item in list_projects() if item["id"] == project["id"])
