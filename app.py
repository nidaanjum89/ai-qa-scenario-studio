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
        if urlparse(self.path).path != "/api/generate":
            self.send_error(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 50_000:
                self._json(413 if length > 50_000 else 400, {"error": "Send a request body up to 50 KB."})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("The request must be a JSON object.")
            story = str(payload.get("story", "")).strip()
            if not story:
                raise ValueError("Add a short user story before generating artifacts.")
            if len(story) > 2000:
                raise ValueError("Keep the user story under 2,000 characters.")
            if len(str(payload.get("product", ""))) > 120 or len(str(payload.get("feature", ""))) > 120:
                raise ValueError("Product and feature names must be under 120 characters.")
            payload["criteria"] = parse_criteria(payload.get("criteria", []))
            ai_scenarios = []
            engine = "Local rules demo"
            warning = None
            if configured():
                try:
                    ai_scenarios = generate_additional_scenarios(payload, payload["criteria"])
                    engine = "OpenAI + local traceability guardrails"
                except AIProviderError as exc:
                    warning = str(exc)
            result = build_artifacts(payload, ai_scenarios=ai_scenarios, engine=engine)
            if warning:
                result["aiWarning"] = warning + " Local baseline artifacts are shown instead."
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
