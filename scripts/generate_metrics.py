#!/usr/bin/env python3
"""Generate a compact SVG showing the four most-used languages in public repos."""

from __future__ import annotations

import html
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.github.com"
USER = "ShashwatSolanki"
IGNORED = {"HTML", "CSS", "SCSS", "Makefile", "Dockerfile"}
COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "C": "#555555",
    "C++": "#f34b7d",
    "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B",
    "Vue": "#41b883",
    "Rust": "#dea584",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Dart": "#00B4AB",
    "R": "#198CE7",
    "PowerShell": "#012456",
    "Dockerfile": "#384d54",
}
FALLBACK = "#8b949e"


def get_json(url: str, token: str) -> object:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
            "User-Agent": "ShashwatSolanki-profile-metrics",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in (403, 429, 500, 502, 503, 504):
                raise
        except (URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(2 ** attempt)
    raise RuntimeError(f"GitHub API request failed after retries: {url}") from last_error


def load_languages(repo: dict[str, object], token: str) -> dict[str, int]:
    full_name = str(repo["full_name"])
    payload = get_json(f"{API}/repos/{full_name}/languages", token)
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected language response for {full_name}")
    return {str(name): int(size) for name, size in payload.items()}


def collect_totals(token: str) -> dict[str, int]:
    payload = get_json(
        f"{API}/users/{USER}/repos?type=owner&visibility=public&per_page=100&sort=updated",
        token,
    )
    if not isinstance(payload, list):
        raise TypeError("GitHub repositories endpoint returned an unexpected response")

    repos = [
        repo for repo in payload
        if isinstance(repo, dict) and not repo.get("fork", False)
    ]
    totals: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(load_languages, repo, token) for repo in repos]
        for future in as_completed(futures):
            for language, size in future.result().items():
                if language not in IGNORED:
                    totals[language] = totals.get(language, 0) + size

    return totals


def render_svg(totals: dict[str, int]) -> str:
    selected = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:4]
    if not selected or sum(size for _, size in selected) <= 0:
        raise RuntimeError("No language data was returned for public repositories")

    total = sum(size for _, size in selected)
    shares = [(name, size, size / total) for name, size in selected]

    width = 480
    bar_x = 24
    bar_y = 58
    bar_width = 432
    bar_height = 10
    cursor = bar_x
    segments = []
    for index, (name, _size, share) in enumerate(shares):
        segment_width = bar_width - (cursor - bar_x) if index == len(shares) - 1 else bar_width * share
        segments.append(
            f'<rect x="{cursor:.2f}" y="{bar_y}" width="{segment_width:.2f}" '
            f'height="{bar_height}" fill="{COLORS.get(name, FALLBACK)}"/>'
        )
        cursor += segment_width

    labels = []
    positions = [(24, 101), (252, 101), (24, 135), (252, 135)]
    for (name, _size, share), (x, y) in zip(shares, positions):
        color = COLORS.get(name, FALLBACK)
        labels.append(
            f'<circle cx="{x + 5}" cy="{y - 4}" r="4" fill="{color}"/>'
            f'<text x="{x + 17}" y="{y}" class="language">{html.escape(name)}</text>'
            f'<text x="{x + 205}" y="{y}" class="percent" text-anchor="end">{share * 100:.1f}%</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="164" viewBox="0 0 {width} 164" role="img" aria-labelledby="title desc">
  <title id="title">Top 4 programming languages</title>
  <desc id="desc">Language distribution across Shashwat Solanki's public, non-fork GitHub repositories.</desc>
  <style>
    .title {{ font: 600 16px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #e6edf3; }}
    .language {{ font: 13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #c9d1d9; }}
    .percent {{ font: 12px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #8b949e; }}
    .note {{ font: 10px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #6e7681; }}
  </style>
  <rect x="1" y="1" width="478" height="162" rx="12" fill="#0d1117" stroke="#30363d"/>
  <text x="24" y="34" class="title">Top 4 languages</text>
  <defs>
    <clipPath id="bar-clip"><rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="5"/></clipPath>
  </defs>
  <g clip-path="url(#bar-clip)">{''.join(segments)}</g>
  {''.join(labels)}
  <text x="24" y="153" class="note">Based on public repositories · Excludes forks</text>
</svg>
"""


def main() -> int:
    token = os.environ.get("METRICS_TOKEN", "").strip()
    if not token:
        print("METRICS_TOKEN is required", file=sys.stderr)
        return 1

    totals = collect_totals(token)
    output = render_svg(totals)
    with open("metrics.svg", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(output)
        handle.write("\n")

    print("Generated metrics.svg from public repository language totals:")
    for name, size in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:4]:
        print(f"  {name}: {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
