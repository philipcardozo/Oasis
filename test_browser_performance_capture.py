"""Browser performance capture helper regressions."""
from __future__ import annotations

import json
import subprocess


def test_browser_capture_sanitizes_sensitive_query_values():
    script = """
const {sanitizeUrl} = require("./scripts/browser_performance_capture.js");
const out = [
  sanitizeUrl("https://staging.example.com/api/auth/verify?token=raw-secret-token&next=/"),
  sanitizeUrl("https://staging.example.com/api/search?q=NVDA"),
];
process.stdout.write(JSON.stringify(out));
"""

    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data[0]["sensitive"] is True
    assert "raw-secret-token" not in data[0]["url"]
    assert "token=redacted" in data[0]["url"]
    assert data[1] == {"url": "https://staging.example.com/api/search?q=NVDA", "sensitive": False}
