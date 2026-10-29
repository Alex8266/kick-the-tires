#!/usr/bin/env python3
"""Collect the facts for a Kick the tires run and print them as JSON.

Covers what a script can check reliably: the environment, a static audit of
every installed skill, and update checks for skills, plugins and clients.
Browser, computer use, web search and MCP checks need the agent's own tools,
so SKILL.md handles those.

The script only reads. It never installs, updates or changes anything.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 10
USER_AGENT = "kick-the-tires/1.0"
ORCA_APP = Path("/Applications/Orca.app")
REF_PREFIXES = ("scripts", "references", "assets", "templates")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def http_json(url: str):
    return json.loads(http_get(url).decode("utf-8"))


def run_cmd(args: list[str]) -> str | None:
    """Run a command and return stdout, or None if it is missing or fails."""
    if not shutil.which(args[0]) and not os.path.isabs(args[0]):
        return None
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def version_tuple(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else None


def base_version(text: str | None) -> str | None:
    v = version_tuple(text)
    return ".".join(map(str, v)) if v else None


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"network error: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "timed out"
    return f"{type(exc).__name__}: {exc}"


def read_plist_version(app: Path) -> str | None:
    plist = app / "Contents" / "Info.plist"
    if not plist.exists():
        return None
    try:
        import plistlib
        with plist.open("rb") as fh:
            return plistlib.load(fh).get("CFBundleShortVersionString")
    except Exception:
        return None


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

def detect_environment(env: dict[str, str]) -> dict:
    client, client_version = "unknown", None
    if env.get("ORCA_APP_VERSION"):
        client, client_version = "Orca", env["ORCA_APP_VERSION"]
    elif env.get("__CFBundleIdentifier", "").startswith("com.anthropic.claude"):
        client = "Claude desktop"
        client_version = read_plist_version(Path("/Applications/Claude.app"))
    elif env.get("TERM_PROGRAM") == "vscode":
        client = "VS Code / Cursor"
    elif env.get("TERM_PROGRAM"):
        client = f"Terminal ({env['TERM_PROGRAM']})"

    agent, agent_version = "unknown", None
    if env.get("CLAUDECODE") == "1":
        agent = "Claude Code"
        exe = env.get("CLAUDE_CODE_EXECPATH") or "claude"
        agent_version = base_version(run_cmd([exe, "--version"]) or run_cmd(["claude", "--version"]))
    elif any(k.startswith("CODEX_") and k != "CODEX_HOME" for k in env):
        agent = "Codex"
        agent_version = base_version(run_cmd(["codex", "--version"]))

    return {
        "client": client,
        "clientVersion": client_version,
        "clientLocalBuild": bool(client_version and "-local" in client_version),
        "agent": agent,
        "agentVersion": agent_version,
        "os": f"macOS {platform.mac_ver()[0]}" if platform.mac_ver()[0]
        else f"{platform.system()} {platform.release()}",
        "model": None,  # Only the agent knows its model; SKILL.md fills this in.
    }


# --------------------------------------------------------------------------
# Skill discovery and static audit
# --------------------------------------------------------------------------

def skill_roots(home: Path, cwd: Path) -> list[dict]:
    """Every place an agent looks for skills. `group` decides name clashes."""
    roots = [
        {"path": home / ".claude/skills", "label": "~/.claude/skills", "group": "claude"},
        {"path": cwd / ".claude/skills", "label": "project .claude/skills", "group": "claude"},
        {"path": home / ".agents/skills", "label": "~/.agents/skills", "group": "codex"},
        {"path": cwd / ".agents/skills", "label": "project .agents/skills", "group": "codex"},
        {"path": home / ".codex/skills", "label": "~/.codex/skills", "group": "codex"},
        {"path": home / ".codex/skills/.system", "label": "Codex built-in", "group": "codex-system",
         "source": "codex-builtin"},
    ]
    synced = home / ".claude/skills/synced"
    if synced.is_dir():
        for bucket in sorted(synced.iterdir()):
            if bucket.is_dir() and not bucket.name.startswith("."):
                roots.append({"path": bucket, "label": "claude.ai synced", "group": "synced",
                              "source": "claude.ai-sync"})
    for plugin in installed_plugins(home):
        roots.append({"path": Path(plugin["installPath"]) / "skills",
                      "label": f"plugin {plugin['id']}", "group": f"plugin:{plugin['id']}",
                      "source": f"plugin:{plugin['id']}"})
    seen, unique = set(), []
    for r in roots:
        key = str(r["path"])
        if key not in seen and r["path"].is_dir():
            seen.add(key)
            unique.append(r)
    return unique


def installed_plugins(home: Path) -> list[dict]:
    path = home / ".claude/plugins/installed_plugins.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for plugin_id, installs in data.get("plugins", {}).items():
        for inst in installs:
            if inst.get("installPath"):
                out.append({"id": plugin_id, **inst})
    return out


def parse_frontmatter(text: str) -> dict | None:
    """Parse the simple YAML subset skills use. Returns None if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    data, key, block = {}, None, None
    for line in lines[1:end]:
        if block is not None:
            if line.startswith((" ", "\t")) or not line.strip():
                block.append(line.strip())
                data[key] = " ".join(x for x in block if x)
                continue
            block = None
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block, data[key] = [], ""
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            data[key] = value
    return data


# Only high-confidence references count: markdown links and files a command
# runs (`python3 scripts/x.py`). Paths merely mentioned in prose or examples
# ("e.g. `assets/logo.png`") describe other projects and are not checked.
RUN_RE = re.compile(r"\b(?:python3?|bash|sh|node|source|cat)\s+(?:-\S+\s+)*((?:%s)/[\w./-]+\.\w+)"
                    % "|".join(REF_PREFIXES))
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")


FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)


def referenced_paths(text: str) -> set[str]:
    refs = set(RUN_RE.findall(text))
    # Links inside fenced blocks are sample markdown, not this skill's links.
    for target in LINK_RE.findall(FENCE_RE.sub("", text)):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith(("#", "/", "~")):
            continue
        refs.add(target.split("#")[0])
    clean = set()
    for ref in refs:
        ref = ref.rstrip(".,:;")
        if ref and not re.search(r"[<>{}*$]", ref) and not ref.endswith("/"):
            clean.add(ref)
    return clean


def audit_skill(skill_dir: Path) -> tuple[str | None, list[dict]]:
    """Return (name, problems). Each problem is {level: fail|warn, text}."""
    problems = []
    if skill_dir.is_symlink() and not skill_dir.exists():
        return None, [{"level": "fail", "text": f"broken symlink → {os.readlink(skill_dir)}"}]
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None, [{"level": "warn", "text": "folder has no SKILL.md (agents ignore it)"}]
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    if fm is None:
        return None, [{"level": "fail", "text": "SKILL.md has no frontmatter"}]
    name = fm.get("name") or None
    if not name:
        problems.append({"level": "fail", "text": "frontmatter is missing `name`"})
    elif name != skill_dir.name:
        problems.append({"level": "warn", "text": f"name `{name}` differs from folder `{skill_dir.name}`"})
    desc = fm.get("description", "")
    if not desc:
        problems.append({"level": "fail", "text": "frontmatter is missing `description`"})
    elif len(desc) > 1024:
        problems.append({"level": "warn", "text": f"description is {len(desc)} chars (limit 1024)"})
    bases = [skill_dir, skill_dir.parent, skill_dir.parent.parent]
    missing = sorted(r for r in referenced_paths(text) if not any((b / r).exists() for b in bases))
    if missing:
        shown = ", ".join(missing[:3]) + (" …" if len(missing) > 3 else "")
        problems.append({"level": "warn", "text": f"referenced file missing: {shown}"})
    return name or skill_dir.name, problems


def collect_skills(home: Path, cwd: Path) -> list[dict]:
    by_real: dict[str, dict] = {}
    for root in skill_roots(home, cwd):
        for entry in sorted(root["path"].iterdir()):
            if entry.name.startswith(".") or not (entry.is_dir() or entry.is_symlink()):
                continue
            if root["path"] == home / ".claude/skills" and entry.name == "synced":
                continue  # handled as its own roots
            real = os.path.realpath(entry)
            if real in by_real:
                by_real[real]["roots"].append(root["label"])
                by_real[real]["groups"].add(root["group"])
                continue
            name, problems = audit_skill(entry)
            by_real[real] = {
                "name": name or entry.name,
                "path": str(entry),
                "realPath": real,
                "roots": [root["label"]],
                "groups": {root["group"]},
                "source": root.get("source"),
                "problems": problems,
            }
    skills = list(by_real.values())
    # Same name in two different folders that one agent reads → ambiguous.
    for group in ("claude", "codex"):
        names: dict[str, list[dict]] = {}
        for s in skills:
            if group in s["groups"] and (Path(s["realPath"]) / "SKILL.md").is_file():
                names.setdefault(s["name"], []).append(s)
        for name, dupes in names.items():
            if len(dupes) > 1:
                where = " and ".join(d["roots"][0] for d in dupes)
                for d in dupes:
                    d["problems"].append({"level": "warn", "text": f"name clash: `{name}` in {where}"})
    for s in skills:
        s["groups"] = sorted(s["groups"])
        levels = {p["level"] for p in s["problems"]}
        s["status"] = "fail" if "fail" in levels else "warn" if "warn" in levels else "ok"
    return sorted(skills, key=lambda s: (s["name"], s["path"]))


# --------------------------------------------------------------------------
# Skill and plugin update checks
# --------------------------------------------------------------------------

def file_matches(path: Path, entry: dict) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    wanted = {entry.get("exactSha256"), entry.get("textNormalizedSha256"), entry.get("identitySha256")}
    candidates = {hashlib.sha256(data).hexdigest(),
                  hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()}
    return bool(wanted & candidates)


def check_orca_skills(skills: list[dict], orca_app: Path) -> tuple[list[dict], set[str]]:
    """Compare installed Orca skills with the copy this Orca build ships."""
    manifest_path = orca_app / "Contents/Resources/skills/current-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return [], set()
    bundled = {s["name"]: s for s in manifest.get("skills", [])}
    outdated, covered = [], set()
    for s in skills:
        if s["source"] or s["name"] not in bundled:
            continue
        covered.add(s["realPath"])
        files = bundled[s["name"]].get("files", [])
        if not all(file_matches(Path(s["realPath"]) / f["path"], f) for f in files):
            outdated.append(s["name"])
    if not covered:
        return [], covered
    outdated = sorted(set(outdated))
    result = {
        "kind": "orca-skills",
        "name": "Orca skills",
        "status": "outdated" if outdated else "current",
        "detail": (", ".join(outdated) + " differ from this Orca build") if outdated
        else f"{len({Path(c).name for c in covered})} match this Orca build",
        "fix": ("orca skills update " + " ".join(f"--skill {n}" for n in outdated)) if outdated else None,
    }
    return [result], covered


def check_lock_skills(home: Path, skills: list[dict], covered: set[str]) -> list[dict]:
    """Skills installed with the `skills` CLI record the folder hash they came from."""
    try:
        lock = json.loads((home / ".agents/.skill-lock.json").read_text())
    except (OSError, ValueError):
        return []
    installed = {s["name"]: s for s in skills if s["realPath"] not in covered and not s["source"]}
    parents: dict[tuple[str, str], dict] = {}
    results = []
    for name, info in sorted(lock.get("skills", {}).items()):
        if name not in installed or info.get("sourceType") != "github":
            continue
        skill_dir = str(Path(info.get("skillPath", "")).parent)
        parent, folder = str(Path(skill_dir).parent), Path(skill_dir).name
        key = (info["source"], parent)
        if key not in parents:
            try:
                listing = http_json(f"https://api.github.com/repos/{info['source']}/contents/{parent}")
                parents[key] = {e["name"]: e.get("sha") for e in listing if isinstance(e, dict)}
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                parents[key] = {"__error__": describe_error(exc)}
        listing = parents[key]
        if "__error__" in listing:
            results.append({"kind": "skill", "name": name, "status": "unknown",
                            "detail": f"couldn't reach GitHub ({listing['__error__']})", "fix": None})
        elif folder not in listing:
            results.append({"kind": "skill", "name": name, "status": "unknown",
                            "detail": f"no longer in {info['source']}", "fix": None})
        elif listing[folder] != info.get("skillFolderHash"):
            results.append({"kind": "skill", "name": name, "status": "outdated",
                            "detail": f"newer version in {info['source']}", "fix": "npx skills update"})
        else:
            results.append({"kind": "skill", "name": name, "status": "current",
                            "detail": f"matches {info['source']}", "fix": None})
        covered.add(installed[name]["realPath"])
    return results


def check_git_skills(skills: list[dict], covered: set[str]) -> list[dict]:
    results = []
    for s in skills:
        repo = Path(s["realPath"])
        if s["realPath"] in covered or not (repo / ".git").exists():
            continue
        covered.add(s["realPath"])
        local = run_cmd(["git", "-C", str(repo), "rev-parse", "HEAD"])
        remote = run_cmd(["git", "-C", str(repo), "ls-remote", "origin", "HEAD"])
        if not local or not remote:
            results.append({"kind": "skill", "name": s["name"], "status": "unknown",
                            "detail": "couldn't compare with its git remote", "fix": None})
        elif remote.split()[0] != local:
            results.append({"kind": "skill", "name": s["name"], "status": "outdated",
                            "detail": "differs from its git remote",
                            "fix": f"git -C {repo} pull"})
        else:
            results.append({"kind": "skill", "name": s["name"], "status": "current",
                            "detail": "matches its git remote", "fix": None})
    return results


def check_plugins(home: Path) -> list[dict]:
    try:
        markets = json.loads((home / ".claude/plugins/known_marketplaces.json").read_text())
    except (OSError, ValueError):
        markets = {}
    manifests: dict[str, dict | str] = {}
    results = []
    for plugin in installed_plugins(home):
        name, _, market = plugin["id"].partition("@")
        src = markets.get(market, {}).get("source", {})
        if market not in manifests:
            try:
                if src.get("source") == "github":
                    manifests[market] = http_json(
                        f"https://raw.githubusercontent.com/{src['repo']}/HEAD/.claude-plugin/marketplace.json")
                elif src.get("source") == "directory":
                    manifests[market] = json.loads(
                        (Path(src["path"]) / ".claude-plugin/marketplace.json").read_text())
                else:
                    manifests[market] = "unsupported marketplace type"
            except Exception as exc:  # noqa: BLE001
                manifests[market] = describe_error(exc)
        manifest = manifests[market]
        latest = None
        if isinstance(manifest, dict):
            entry = next((p for p in manifest.get("plugins", []) if p.get("name") == name), None)
            if entry:
                latest = entry.get("version")
                if not latest and src.get("source") == "directory" and isinstance(entry.get("source"), str):
                    pj = Path(src["path"]) / entry["source"] / ".claude-plugin/plugin.json"
                    try:
                        latest = json.loads(pj.read_text()).get("version")
                    except (OSError, ValueError):
                        latest = None
        installed = plugin.get("version")
        fix = f"claude plugin update {plugin['id']}"
        if isinstance(manifest, str):
            results.append({"kind": "plugin", "name": name, "status": "unknown",
                            "detail": f"couldn't read marketplace ({manifest})", "fix": None})
        elif not latest:
            results.append({"kind": "plugin", "name": name, "status": "unknown",
                            "detail": "marketplace lists no version", "fix": None})
        elif version_tuple(latest) and version_tuple(installed) and version_tuple(latest) > version_tuple(installed):
            results.append({"kind": "plugin", "name": name, "status": "outdated",
                            "installed": installed, "latest": latest,
                            "detail": f"{installed} → {latest}", "fix": fix})
        else:
            results.append({"kind": "plugin", "name": name, "status": "current",
                            "installed": installed, "latest": latest, "detail": installed, "fix": None})
    return results


def skill_updates(home: Path, skills: list[dict], orca_app: Path) -> list[dict]:
    results, covered = check_orca_skills(skills, orca_app)
    results += check_lock_skills(home, skills, covered)
    results += check_git_skills(skills, covered)
    results += check_plugins(home)
    unchecked = [s["name"] for s in skills
                 if s["realPath"] not in covered and not s["source"] and s["status"] != "fail"
                 and (Path(s["realPath"]) / "SKILL.md").exists()]
    if unchecked:
        results.append({"kind": "unknown-source", "name": "no update source", "status": "unknown",
                        "detail": ", ".join(sorted(set(unchecked))), "fix": None})
    return results


# --------------------------------------------------------------------------
# Client updates
# --------------------------------------------------------------------------

def npm_latest(package: str) -> str:
    return http_json(f"https://registry.npmjs.org/{package}/latest")["version"]


def compare(name: str, installed: str | None, latest_fn, fix: str, note: str | None = None) -> dict:
    item = {"name": name, "installed": installed, "latest": None, "status": "unknown", "fix": None,
            "note": note}
    if not installed:
        item["detail"] = "couldn't read installed version"
        return item
    try:
        item["latest"] = latest_fn()
    except Exception as exc:  # noqa: BLE001
        item["detail"] = f"couldn't check latest ({describe_error(exc)})"
        return item
    newer = version_tuple(item["latest"]) and version_tuple(item["latest"]) > version_tuple(installed)
    item["status"] = "outdated" if newer else "current"
    item["fix"] = fix if newer else None
    item["detail"] = f"{base_version(installed)} → {base_version(item['latest'])}" if newer \
        else base_version(installed)
    return item


def find_skill(skills: list[dict], name: str) -> bool:
    return any(s["name"] == name for s in skills)


def client_updates(env_info: dict, skills: list[dict], orca_app: Path) -> list[dict]:
    items = []
    claude = run_cmd(["claude", "--version"])
    if claude:
        items.append(compare("Claude Code", base_version(claude),
                             lambda: npm_latest("@anthropic-ai/claude-code"), "claude update"))
    codex_path = shutil.which("codex")
    if codex_path:
        fix = "brew upgrade codex" if ("Cellar" in os.path.realpath(codex_path) or "homebrew" in codex_path) \
            else "npm install -g @openai/codex@latest"
        items.append(compare("Codex", base_version(run_cmd(["codex", "--version"])),
                             lambda: npm_latest("@openai/codex"), fix))
    orca_version = env_info["clientVersion"] if env_info["client"] == "Orca" else read_plist_version(orca_app)
    if orca_version:
        local = "-local" in orca_version
        if local:
            fix = ("use the `orca-update` skill (custom build: don't install the stock release)"
                   if find_skill(skills, "orca-update") else "rebuild your local Orca from the latest release")
        else:
            fix = "Orca → Check for Updates"
        item = compare("Orca", orca_version,
                       lambda: http_json("https://api.github.com/repos/stablyai/orca/releases/latest")["tag_name"],
                       fix, note="local build" if local else None)
        items.append(item)
    return items


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def summarize_skills(skills: list[dict], updates: list[dict]) -> dict:
    counts = {"total": len(skills),
              "ok": sum(s["status"] == "ok" for s in skills),
              "warn": sum(s["status"] == "warn" for s in skills),
              "fail": sum(s["status"] == "fail" for s in skills),
              "updates": sum(u["status"] == "outdated" for u in updates)}
    status = "fail" if counts["fail"] else "warn" if counts["warn"] or counts["updates"] else "ok"
    return {"status": status, "counts": counts}


def mmss(seconds: float) -> str:
    """Format a duration as minutes:seconds, e.g. 0:07 or 2:05."""
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def guarded(fn, *args):
    """Run one section; return (result, error, seconds). Never raises."""
    start = time.monotonic()
    try:
        result, err = fn(*args), None
    except Exception as exc:  # noqa: BLE001 - one failing section must not stop the run
        result, err = None, f"{fn.__name__}: {describe_error(exc)}"
    return result, err, time.monotonic() - start


def probe(home: Path, cwd: Path, env: dict[str, str], orca_app: Path = ORCA_APP) -> dict:
    started = time.monotonic()
    now = dt.datetime.now(dt.timezone.utc)
    env_info, env_err, _ = guarded(detect_environment, env)
    env_info = env_info or {"client": "unknown", "clientVersion": None, "agent": "unknown"}
    skills, skills_err, t_audit = guarded(collect_skills, home, cwd)
    skills = skills or []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f_updates = pool.submit(guarded, skill_updates, home, skills, orca_app)
        f_clients = pool.submit(guarded, client_updates, env_info, skills, orca_app)
        (updates, upd_err, t_updates), (clients, cli_err, t_clients) = (
            f_updates.result(), f_clients.result())
    errors = [e for e in (env_err, skills_err, upd_err, cli_err) if e]
    # Time per report row. Skill update checks and client updates run in
    # parallel, so these overlap and don't add up to `total`.
    timings = {
        "skills": mmss(t_audit + t_updates),
        "updates": mmss(t_clients),
        "total": mmss(time.monotonic() - started),
    }
    return {
        "generatedAt": now.isoformat(),
        "environment": env_info,
        "skills": {**summarize_skills(skills, updates or []), "items": skills},
        "skillUpdates": updates or [],
        "clientUpdates": clients or [],
        "timings": timings,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd", default=os.getcwd(), help="project folder to scan for project skills")
    ap.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    result = probe(Path(args.home), Path(args.cwd), dict(os.environ))
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
