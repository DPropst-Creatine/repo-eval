#!/usr/bin/env python3
"""repo_eval.py — deterministic GitHub repository health check.

Usage:
    repo_eval.py <github-repo-url> [--token TOKEN]

Fetches public signal via the GitHub REST API (no cloning, no AI) and prints a
deterministic health report. Qualitative judgment (project fit, alternatives,
licensing nuance) is left to the caller — this tool only reports checkable facts.

Exit codes: 0 ok · 2 bad URL / repo not found / API error.
"""
import base64
import http.client
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

API = "https://api.github.com"


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


class NotFoundError(Exception):
    pass


def api_get(path, token, _retried=False):
    req = urlreq.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "repo-eval/1.0",
    })
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urlreq.urlopen(req, timeout=25) as res:
            body = res.read().decode("utf-8", "replace")
            return json.loads(body), dict(res.headers)
    except HTTPError as e:
        if e.code == 404:
            raise NotFoundError()
        if e.code == 403:
            remaining = e.headers.get("x-ratelimit-remaining")
            if remaining == "0":
                fail("error: GitHub API rate limit exhausted — set GITHUB_TOKEN "
                     "to raise it from 60 to 5,000 req/hr")
            # Transient denial (secondary rate limiting / abuse detection on
            # shared egress IPs). Retry once after a short wait.
            if not _retried:
                time.sleep(8)
                return api_get(path, token, _retried=True)
            fail("error: GitHub API denied the request (HTTP 403) twice — "
                 "likely transient throttling on this network; retry in a minute")
        fail(f"error: GitHub API returned HTTP {e.code}")
    except (URLError, http.client.HTTPException) as e:
        # Transient network failure (proxy hiccup, truncated response, ...).
        if not _retried:
            time.sleep(5)
            return api_get(path, token, _retried=True)
        fail(f"error: network failure reaching api.github.com ({e})")


def parse_repo_url(url):
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", (url or "").strip())
    if not m:
        fail("error: that doesn't look like a GitHub repository URL")
    owner, repo = m.group(1), m.group(2)
    repo = repo[:-4] if repo.endswith(".git") else repo
    # Fail closed: owner/repo are interpolated raw into API paths, so reject
    # anything outside GitHub's own naming rules (dot segments, percent
    # encodings, '?' or '#' would otherwise alter the request path).
    if len(owner) > 39 or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", owner):
        fail("error: that doesn't look like a valid GitHub owner name")
    if repo in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", repo):
        fail("error: that doesn't look like a valid GitHub repository name")
    return owner, repo


def days_since(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


TEST_DIR_RE = re.compile(r"(^|/)(tests?|__tests__|testdata)(/|$)", re.I)
TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*|[^/]*[._-]test\.[^/]*|[^/]*\.spec\.[^/]*)$", re.I)


def has_tests(paths):
    return any(TEST_DIR_RE.search(p) or TEST_FILE_RE.search(p) for p in paths)


def dep_count(paths, get_file):
    """Count dependencies from the first recognized manifest found."""
    manifests = [
        ("package.json", lambda c: _json_deps(c)),
        ("requirements.txt", lambda c: _req_lines(c)),
        ("pyproject.toml", lambda c: _toml_deps(c)),
        ("Cargo.toml", lambda c: _toml_deps(c)),
        ("go.mod", lambda c: _gomod_deps(c)),
    ]
    for name, parser in manifests:
        if name in paths:
            content = get_file(name)
            if content:
                try:
                    return {"count": parser(content), "source": name}
                except Exception:
                    return {"count": None, "source": name, "parse_error": True}
    return {"count": None, "source": None}


def _json_deps(content):
    pkg = json.loads(content)
    return len(pkg.get("dependencies", {}) or {}) + len(pkg.get("devDependencies", {}) or {})


def _req_lines(content):
    return sum(1 for ln in content.splitlines()
               if ln.strip() and not ln.strip().startswith(("#", "-")))


def _toml_deps(content):
    # Crude but honest: count lines under [dependencies]-style sections.
    count, in_deps = 0, False
    for ln in content.splitlines():
        s = ln.strip()
        if s.startswith("["):
            in_deps = "dependenc" in s.lower()
            continue
        if in_deps and s and not s.startswith("#") and "=" in s:
            count += 1
    return count


def _gomod_deps(content):
    return sum(1 for ln in content.splitlines()
               if re.match(r"\s+[^\s]+\s+v\d", ln))


def compute_score(signals):
    """Additive 0-100 health score. Every point is traceable to a named check.

    `signals` keys: pushed_days, license_spdx, has_license_file, tests,
    has_ci, readme_len, has_docker, homepage, contributors, stars,
    open_issues. Returns (score, breakdown).
    """
    score, breakdown = 0, []

    def add(label, pts):
        breakdown.append({"label": label, "points": pts})
        return pts

    pushed_days = signals.get("pushed_days")
    if pushed_days is not None:
        if pushed_days <= 30:
            score += add("Pushed in the last 30 days", 20)
        elif pushed_days <= 90:
            score += add("Pushed in the last 90 days", 14)
        elif pushed_days <= 365:
            score += add("Pushed in the last year", 7)

    if signals.get("license_spdx") not in (None, "NOASSERTION"):
        score += add("Code license declared (%s)" % signals.get("license_spdx"), 15)
    if signals.get("has_license_file"):
        score += add("LICENSE file present in tree", 5)
    if signals.get("tests"):
        score += add("Test files/directories present", 15)
    if signals.get("has_ci"):
        score += add("CI workflow configured", 15)
    readme_len = signals.get("readme_len", 0) or 0
    if readme_len >= 500:
        score += add("README present and substantive", 5)
    elif readme_len > 0:
        score += add("README present but thin", 2)
    if signals.get("has_docker"):
        score += add("Dockerfile present", 5)
    if signals.get("homepage"):
        score += add("Homepage/demo link set", 5)
    contributors = signals.get("contributors")
    if contributors and contributors >= 3:
        score += add(f"{contributors} contributors", 5)
    stars = signals.get("stars", 0) or 0
    open_issues = signals.get("open_issues", 0) or 0
    ratio = open_issues / max(stars, 1)
    if ratio < 0.05:
        score += add("Healthy open-issue ratio", 10)
    elif ratio < 0.2:
        score += add("Acceptable open-issue ratio", 6)
    elif ratio < 0.5:
        score += add("Elevated open-issue ratio", 3)
    return score, breakdown


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        fail("usage: repo_eval.py <github-repo-url> [--token TOKEN]")
    token = os.environ.get("GITHUB_TOKEN", "")
    if "--token" in flags:
        i = sys.argv.index("--token")
        token = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""

    owner, repo = parse_repo_url(args[0])
    base = f"/repos/{owner}/{repo}"

    try:
        meta, _ = api_get(base, token)
    except NotFoundError:
        fail("error: repository not found (is it public?)")
    if meta.get("private"):
        # Public-only by design: never spend the operator's token on follow-on
        # calls, or print derived data, for a repository the URL supplier may
        # not be able to read themselves.
        fail("error: repository is private; "
             "repo_eval only evaluates public repositories")
    default_branch = meta.get("default_branch", "main")

    tree, _ = api_get(f"{base}/git/trees/{default_branch}?recursive=1", token)
    tree_truncated = bool(tree.get("truncated"))
    paths = [i["path"] for i in tree.get("tree", []) if i.get("type") == "blob"]

    def get_file(path):
        try:
            data, _ = api_get(f"{base}/contents/{path}", token)
        except NotFoundError:
            return None
        if data.get("encoding") == "base64":
            try:
                return base64.b64decode(data.get("content", "")).decode("utf-8", "ignore")
            except Exception:
                return None
        return None

    readme_len = 0
    try:
        data, _ = api_get(f"{base}/readme", token)
        if data.get("encoding") == "base64":
            readme_len = len(base64.b64decode(data.get("content", "")))
    except NotFoundError:
        pass

    langs, _ = api_get(meta.get("languages_url", "").replace(API, ""), token) \
        if meta.get("languages_url") else ({}, {})
    total = sum(langs.values()) or 1
    top_langs = [{"name": n, "pct": round(v / total * 100)}
                 for n, v in sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:4]]

    contrib_data, contrib_headers = api_get(f"{base}/contributors?per_page=1&anon=true", token)
    contributors = None
    link = contrib_headers.get("Link", "")
    m = re.search(r'page=(\d+)>;\s*rel="last"', link)
    contributors = int(m.group(1)) if m else (len(contrib_data) if isinstance(contrib_data, list) else None)

    license_info = meta.get("license") or {}
    pushed_days = days_since(meta.get("pushed_at"))
    stars = meta.get("stargazers_count", 0) or 0
    open_issues = meta.get("open_issues_count", 0) or 0
    deps = dep_count(paths, get_file)

    lower = [p.lower() for p in paths]
    has_license_file = any(os.path.basename(p) in
                           ("license", "license.md", "license.txt", "copying", "licence")
                           for p in lower)
    has_docker = any("dockerfile" in p for p in lower) or "docker-compose.yml" in lower
    has_ci = any(p.startswith(".github/workflows") for p in paths)
    has_env_example = ".env.example" in lower or ".env.sample" in lower
    committed_env = ".env" in paths
    tests = has_tests(paths)
    homepage = (meta.get("homepage") or "").strip() or None

    # ---- deterministic score (additive, every point traceable) ----
    score, breakdown = compute_score({
        "pushed_days": pushed_days,
        "license_spdx": license_info.get("spdx_id"),
        "has_license_file": has_license_file,
        "tests": tests,
        "has_ci": has_ci,
        "readme_len": readme_len,
        "has_docker": has_docker,
        "homepage": homepage,
        "contributors": contributors,
        "stars": stars,
        "open_issues": open_issues,
    })

    # ---- red flags ----
    flags = []
    if meta.get("archived"):
        flags.append("Repository is archived — read-only, no future maintenance expected.")
    if not license_info.get("spdx_id") or license_info.get("spdx_id") == "NOASSERTION":
        flags.append("No code license declared — reuse/fork rights unclear.")
    if readme_len < 500:
        flags.append("README missing or thin — expect setup friction.")
    if not tests:
        flags.append("No test files detected — no automated verification of claims.")
    if not has_ci:
        flags.append("No CI pipeline — contribution quality is unmeasured.")
    if pushed_days is not None and pushed_days > 365:
        flags.append(f"Last push {pushed_days} days ago — likely unmaintained.")
    if committed_env:
        flags.append("A .env file is committed at the repo root — check for leaked secrets.")
    if tree_truncated:
        flags.append("File tree was truncated by the GitHub API — file-based checks "
                     "(tests, CI, Dockerfile) may be incomplete for this very large repo.")
    if contributors == 1:
        flags.append("Single contributor — bus-factor risk.")
    if deps.get("parse_error"):
        flags.append(f"Could not parse {deps.get('source')} — dependency list unverified.")

    report = {
        "repo": meta.get("full_name"),
        "url": meta.get("html_url"),
        "description": meta.get("description") or "",
        "language": meta.get("language") or "",
        "top_languages": top_langs,
        "stars": stars,
        "forks": meta.get("forks_count", 0),
        "open_issues": open_issues,
        "watchers": meta.get("subscribers_count", 0),
        "license_spdx": license_info.get("spdx_id"),
        "license_file_in_tree": has_license_file,
        "topics": meta.get("topics", []),
        "created_at": meta.get("created_at"),
        "pushed_at": meta.get("pushed_at"),
        "days_since_push": pushed_days,
        "archived": bool(meta.get("archived")),
        "contributors": contributors,
        "file_count": len(paths),
        "file_tree_truncated": tree_truncated,
        "dependency_count": deps.get("count"),
        "dependency_source": deps.get("source"),
        "readme_bytes": readme_len,
        "has_tests": tests,
        "has_ci": has_ci,
        "has_dockerfile": has_docker,
        "has_env_example": has_env_example,
        "committed_root_env": committed_env,
        "homepage": homepage,
        "health_score": max(0, min(100, score)),
        "score_breakdown": breakdown,
        "red_flags": flags,
        "api_calls_used": 6,
    }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
