"""Local web server for AI QA Scenario Studio (Python standard library only)."""
from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from ai_provider import AIProviderError, configured, generate_additional_scenarios
from evaluate import run_evaluation
from generator import build_artifacts, parse_criteria
from memory_store import (
    DEFAULT_PROJECT_ID,
    approved_examples,
    create_project,
    export_project,
    get_project,
    get_run,
    import_project,
    list_projects,
    list_runs,
    save_reviews,
    save_run,
)

ROOT = Path(__file__).resolve().parent
PUBLIC = (ROOT / "public").resolve()


class Handler(BaseHTTPRequestHandler):
    server_version = "ScenarioStudio/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(200, {"aiConfigured": configured(), "mode": "AI + deterministic guardrails" if configured() else "Local rules demo", "site": "SauceDemo"})
            return
        if path == "/api/evaluate":
            self._json(200, run_evaluation())
            return
        if path == "/api/projects":
            self._json(200, {"projects": list_projects()})
            return
        parts = [part for part in path.split("/") if part]
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "runs":
            if not get_project(parts[2]):
                self._json(404, {"error": "Project not found."})
                return
            self._json(200, {"runs": list_runs(parts[2])})
            return
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "export":
            bundle = export_project(parts[2])
            if bundle is None:
                self._json(404, {"error": "Project not found."})
                return
            self._json(200, bundle)
            return
        if len(parts) == 3 and parts[:2] == ["api", "runs"]:
            run = get_run(parts[2])
            if run is None:
                self._json(404, {"error": "Saved plan not found."})
                return
            self._json(200, run)
            return
        requested = "/index.html" if path == "/" else unquote(path)
        file_path = (PUBLIC / requested.lstrip("/")).resolve()
        if not file_path.is_relative_to(PUBLIC) or not file_path.is_file():
            self.send_error(404, "Not found")
            return
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        parts = [part for part in path.split("/") if part]
        is_review_update = len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "reviews"
        if path not in {"/api/generate", "/api/projects", "/api/projects/import"} and not is_review_update:
            self.send_error(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            max_bytes = 50_000 if path == "/api/generate" else 2_000_000
            if length <= 0 or length > max_bytes:
                self._json(413 if length > max_bytes else 400, {"error": f"Send a request body up to {max_bytes // 1000} KB."})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("The request must be a JSON object.")
            if path == "/api/projects":
                project = create_project(payload.get("name", ""))
                self._json(201, {"project": project})
                return
            if path == "/api/projects/import":
                project = import_project(payload)
                self._json(201, {"project": project})
                return
            if is_review_update:
                reviews = payload.get("reviews", {})
                if not isinstance(reviews, dict):
                    raise ValueError("Reviews must be an object with criterion statuses.")
                self._json(200, {"reviews": save_reviews(parts[2], reviews)})
                return
            story = str(payload.get("story", "")).strip()
            if not story:
                raise ValueError("Add a short user story before generating artifacts.")
            if len(story) > 2000:
                raise ValueError("Keep the user story under 2,000 characters.")
            if len(str(payload.get("product", ""))) > 120 or len(str(payload.get("feature", ""))) > 120:
                raise ValueError("Product and feature names must be under 120 characters.")
            project_id = str(payload.get("projectId", DEFAULT_PROJECT_ID))
            project = get_project(project_id)
            if project is None:
                raise ValueError("Choose a saved project before generating a plan.")
            payload["projectId"] = project_id
            payload["criteria"] = parse_criteria(payload.get("criteria", []))
            ai_scenarios = []
            engine = "Local rules demo"
            warning = None
            memory_examples = []
            result = build_artifacts(payload, engine=engine)
            if configured():
                memory_examples = approved_examples(project_id)
                try:
                    ai_scenarios = generate_additional_scenarios(
                        payload,
                        payload["criteria"],
                        project_memory=memory_examples,
                        existing_scenarios=result["scenarios"],
                    )
                    engine = "OpenAI + local traceability guardrails"
                    result = build_artifacts(payload, ai_scenarios=ai_scenarios, engine=engine)
                except AIProviderError as exc:
                    warning = str(exc)
            if warning:
                result["aiWarning"] = warning + " Local baseline artifacts are shown instead."
            saved = save_run(project_id, payload, result)
            result["memory"] = {**saved, "projectName": project["name"], "approvedExamplesShared": len(memory_examples) if configured() and not warning else 0}
            self._json(200, result)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "Request body must be valid UTF-8 JSON."})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            self._json(500, {"error": "The studio could not generate artifacts. Review your input and try again."})

    def _json(self, status: int, value: object) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")

    def log_message(self, format: str, *args: object) -> None:
        # Avoid writing user requirement text or request bodies to terminal logs.
        super().log_message(format, *args)


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Scenario Studio running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Scenario Studio.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
