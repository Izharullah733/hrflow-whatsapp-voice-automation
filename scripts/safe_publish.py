"""Reject sensitive files or known local secrets before a public Git commit."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_PATH = re.compile(
    r"(^|/)(?:\.env(?:\..*)?|config\.json|service-account[^/]*\.json|chrome-profile|data|\.venv)(?:/|$)|"
    r"\.(?:sqlite3|db|log|ogg|opus|mp3|wav|pem|p12)$",
    re.I,
)
SECRET_MARKERS = [
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ("service-account JSON", re.compile(rb'"private_key"\s*:')),
    ("GitHub token", re.compile(rb"(?:ghp_|github_pat_)[A-Za-z0-9_]{15,}")),
    ("Google API key", re.compile(rb"AIza[0-9A-Za-z_-]{20,}")),
    ("Google Sheet URL", re.compile(rb"docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]{20,}")),
]


def staged_files() -> list[str]:
    result = subprocess.run(["git", "ls-files", "--cached", "-z"], cwd=ROOT, check=True, capture_output=True)
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def local_secrets() -> list[bytes]:
    secrets = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"WHATSAPP_ALLOWED_NUMBERS", "GOOGLE_SHEET_ID", "DASHBOARD_SECRET_KEY"}:
                value = value.strip().strip('"').strip("'")
                if len(value) >= 8:
                    secrets.append(value.encode("utf-8"))
    service_account = ROOT / "service-account.json"
    if service_account.exists():
        account = json.loads(service_account.read_text(encoding="utf-8"))
        for key in ("client_email", "private_key_id", "private_key"):
            value = account.get(key, "")
            if value:
                secrets.append(value.encode("utf-8"))
    return secrets


def main() -> int:
    problems = []
    secrets = local_secrets()
    for name in staged_files():
        normalized = name.replace("\\", "/")
        if normalized != ".env.example" and FORBIDDEN_PATH.search(normalized):
            problems.append(f"Forbidden path: {name}")
            continue
        content = subprocess.run(["git", "show", ":" + name], cwd=ROOT, check=True, capture_output=True).stdout
        for label, pattern in SECRET_MARKERS:
            if pattern.search(content):
                problems.append(f"Possible {label}: {name}")
        if any(secret in content for secret in secrets):
            problems.append(f"Known local secret: {name}")
    if problems:
        print("Publish check FAILED (values withheld):")
        print("\n".join(problems))
        return 1
    print(f"Publish check passed: {len(staged_files())} staged files; no known private paths or secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
