"""
git-context MCP server

Tools for reading and acting on Git repos, GitHub PRs, and CI status.
Covers local git ops, branch management, PR/MR lifecycle, and code review
context — everything an agent needs mid-task without shelling out manually.

Dependencies: GitPython (pip). GitHub ops use the `gh` CLI (must be installed
and authenticated). GitLab ops use the `glab` CLI.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "git-context",
    instructions=(
        "Tools for git operations and PR/MR management. Local git tools work "
        "anywhere. GitHub tools require `gh` CLI authenticated. GitLab tools "
        "require `glab` CLI authenticated. Always call git_status before "
        "making branch or stash changes so you know what state you're in."
    ),
)


def _git(args: list[str], cwd: Optional[str] = None) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, cwd=cwd
    )
    if result.returncode != 0 and result.stderr:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def _gh(args: list[str]) -> str:
    if not shutil.which("gh"):
        raise RuntimeError("gh CLI not found. Install: https://cli.github.com")
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _glab(args: list[str]) -> str:
    if not shutil.which("glab"):
        raise RuntimeError("glab CLI not found. Install: https://gitlab.com/gitlab-org/cli")
    result = subprocess.run(["glab"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Local git — status and history
# ---------------------------------------------------------------------------


@mcp.tool()
def git_status(repo: str = ".") -> dict:
    """
    Show the working tree status: current branch, staged files, unstaged
    changes, untracked files, and whether there are unpushed commits.

    Args:
        repo: Path to the git repo root (default: current directory).
    """
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    status_lines = _git(["status", "--porcelain"], cwd=repo).splitlines()

    staged = [l[3:] for l in status_lines if l[0] not in (" ", "?")]
    unstaged = [l[3:] for l in status_lines if l[1] not in (" ", "?")]
    untracked = [l[3:] for l in status_lines if l[:2] == "??"]

    # Unpushed commits
    try:
        ahead = _git(["rev-list", "--count", f"@{{u}}..HEAD"], cwd=repo)
    except Exception:
        ahead = "unknown"

    return {
        "branch": branch,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "commits_ahead_of_upstream": ahead,
        "clean": len(status_lines) == 0,
    }


@mcp.tool()
def git_log(repo: str = ".", n: int = 20, author: Optional[str] = None, file: Optional[str] = None) -> list[dict]:
    """
    Get recent commit history with author, date, and message.

    Args:
        repo: Path to the git repo root.
        n: Number of commits to return (default 20).
        author: Filter by author name or email.
        file: If provided, only show commits that touched this file.
    """
    fmt = "%H|||%an|||%ae|||%ai|||%s"
    args = ["log", f"-{n}", f"--format={fmt}"]
    if author:
        args += [f"--author={author}"]
    if file:
        args += ["--", file]

    output = _git(args, cwd=repo)
    commits = []
    for line in output.splitlines():
        if "|||" not in line:
            continue
        h, name, email, date, subject = line.split("|||", 4)
        commits.append({
            "hash": h[:12],
            "full_hash": h,
            "author": name,
            "email": email,
            "date": date,
            "message": subject,
        })
    return commits


@mcp.tool()
def git_diff(
    repo: str = ".",
    base: Optional[str] = None,
    head: Optional[str] = None,
    file: Optional[str] = None,
    staged: bool = False,
    stat_only: bool = False,
) -> str:
    """
    Show diffs between commits, branches, or working tree changes.

    Args:
        repo: Path to the git repo root.
        base: Base ref (branch, commit, tag). Defaults to staged/unstaged changes.
        head: Head ref. If base is set and head is None, diffs base against HEAD.
        file: Limit diff to this file path.
        staged: If true, show staged (index) changes only.
        stat_only: If true, return only the --stat summary (faster, smaller output).
    """
    args = ["diff"]
    if stat_only:
        args.append("--stat")
    if staged:
        args.append("--cached")
    if base and head:
        args.append(f"{base}...{head}")
    elif base:
        args.append(f"{base}...HEAD")
    if file:
        args += ["--", file]

    return _git(args, cwd=repo)


@mcp.tool()
def git_blame(repo: str, file: str, start_line: int, end_line: int) -> list[dict]:
    """
    Get blame information for a range of lines in a file.

    Args:
        repo: Path to the git repo root.
        file: Relative path to the file within the repo.
        start_line: First line number (1-indexed).
        end_line: Last line number (inclusive).
    """
    output = _git([
        "blame", f"-L{start_line},{end_line}",
        "--porcelain", file
    ], cwd=repo)

    lines = output.splitlines()
    entries = []
    current: dict = {}
    for line in lines:
        if re.match(r"^[0-9a-f]{40} ", line):
            parts = line.split()
            current = {"hash": parts[0][:12], "line": int(parts[2])}
        elif line.startswith("author "):
            current["author"] = line[7:]
        elif line.startswith("author-time "):
            current["timestamp"] = line[12:]
        elif line.startswith("summary "):
            current["summary"] = line[8:]
        elif line.startswith("\t"):
            current["content"] = line[1:]
            entries.append(dict(current))
    return entries


# ---------------------------------------------------------------------------
# Branch management
# ---------------------------------------------------------------------------


@mcp.tool()
def list_branches(repo: str = ".", include_remote: bool = True) -> dict:
    """
    List local and optionally remote branches with their last commit info.

    Args:
        repo: Path to the git repo root.
        include_remote: Include remote-tracking branches (default true).
    """
    local = _git(["branch", "--format=%(refname:short)|||%(objectname:short)|||%(subject)"], cwd=repo)
    local_branches = [
        {"name": p[0], "hash": p[1], "last_commit": p[2]}
        for line in local.splitlines()
        if len((p := line.split("|||", 2))) == 3
    ]

    remote_branches = []
    if include_remote:
        remote = _git(["branch", "-r", "--format=%(refname:short)|||%(objectname:short)|||%(subject)"], cwd=repo)
        remote_branches = [
            {"name": p[0], "hash": p[1], "last_commit": p[2]}
            for line in remote.splitlines()
            if len((p := line.split("|||", 2))) == 3
        ]

    current = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return {"current": current, "local": local_branches, "remote": remote_branches}


@mcp.tool()
def create_branch(repo: str, name: str, base: Optional[str] = None, checkout: bool = True) -> dict:
    """
    Create a new branch, optionally from a specific base ref, and optionally
    check it out.

    Args:
        repo: Path to the git repo root.
        name: New branch name.
        base: Base branch or commit (default: current HEAD).
        checkout: If true, check out the new branch after creating it.
    """
    args = ["checkout", "-b", name] if checkout else ["branch", name]
    if base:
        args.append(base)
    _git(args, cwd=repo)
    return {"created": name, "checked_out": checkout, "base": base or "HEAD"}


@mcp.tool()
def checkout(repo: str, ref: str, create: bool = False) -> dict:
    """
    Check out a branch, tag, or commit.

    Args:
        repo: Path to the git repo root.
        ref: Branch name, tag, or commit hash.
        create: If true, create the branch if it doesn't exist (-b flag).
    """
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(ref)
    _git(args, cwd=repo)
    current = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return {"checked_out": current}


@mcp.tool()
def stash(repo: str = ".", action: str = "push", message: Optional[str] = None) -> dict:
    """
    Manage the git stash.

    Args:
        repo: Path to the git repo root.
        action: One of "push", "pop", "list", "drop", "show" (default "push").
        message: Optional stash message (only used with action="push").
    """
    if action == "push":
        args = ["stash", "push"]
        if message:
            args += ["-m", message]
        output = _git(args, cwd=repo)
        return {"action": "push", "result": output}
    elif action == "pop":
        output = _git(["stash", "pop"], cwd=repo)
        return {"action": "pop", "result": output}
    elif action == "list":
        output = _git(["stash", "list"], cwd=repo)
        return {"stashes": output.splitlines()}
    elif action == "drop":
        output = _git(["stash", "drop"], cwd=repo)
        return {"action": "drop", "result": output}
    elif action == "show":
        output = _git(["stash", "show", "-p"], cwd=repo)
        return {"diff": output}
    else:
        raise ValueError(f"action must be one of: push, pop, list, drop, show")


# ---------------------------------------------------------------------------
# GitHub PR tools (requires gh CLI)
# ---------------------------------------------------------------------------


@mcp.tool()
def pr_list(state: str = "open", limit: int = 20, author: Optional[str] = None) -> list[dict]:
    """
    List pull requests in the current repo.

    Args:
        state: "open", "closed", or "merged" (default "open").
        limit: Max PRs to return (default 20).
        author: Filter by PR author.
    """
    args = ["pr", "list", "--state", state, "--limit", str(limit), "--json",
            "number,title,author,state,headRefName,baseRefName,createdAt,url,isDraft"]
    if author:
        args += ["--author", author]
    return json.loads(_gh(args))


@mcp.tool()
def pr_view(number: int) -> dict:
    """
    Get full details of a specific PR: title, body, status checks, review
    state, comments count, and changed files.

    Args:
        number: PR number.
    """
    info = json.loads(_gh([
        "pr", "view", str(number), "--json",
        "number,title,body,author,state,headRefName,baseRefName,"
        "isDraft,mergeable,reviewDecision,statusCheckRollup,"
        "additions,deletions,changedFiles,url,createdAt,updatedAt"
    ]))
    return info


@mcp.tool()
def pr_diff(number: int, stat_only: bool = False) -> str:
    """
    Get the diff for a PR.

    Args:
        number: PR number.
        stat_only: If true, return only the file-level stat summary.
    """
    args = ["pr", "diff", str(number)]
    if stat_only:
        args.append("--stat")
    return _gh(args)


@mcp.tool()
def pr_create(
    title: str,
    body: str,
    base: str = "main",
    draft: bool = False,
    reviewer: Optional[list[str]] = None,
) -> dict:
    """
    Create a new pull request from the current branch.

    Args:
        title: PR title.
        body: PR description (markdown supported).
        base: Target branch (default "main").
        draft: Open as draft PR (default false).
        reviewer: List of GitHub usernames to request review from.
    """
    args = ["pr", "create", "--title", title, "--body", body, "--base", base]
    if draft:
        args.append("--draft")
    if reviewer:
        for r in reviewer:
            args += ["--reviewer", r]
    output = _gh(args)
    return {"url": output.strip()}


@mcp.tool()
def pr_comment(number: int, body: str) -> dict:
    """
    Add a comment to a PR.

    Args:
        number: PR number.
        body: Comment text (markdown supported).
    """
    _gh(["pr", "comment", str(number), "--body", body])
    return {"commented_on": number}


@mcp.tool()
def pr_merge(number: int, method: str = "squash", delete_branch: bool = True) -> dict:
    """
    Merge a pull request.

    Args:
        number: PR number.
        method: "merge", "squash", or "rebase" (default "squash").
        delete_branch: Delete the head branch after merge (default true).
    """
    if method not in ("merge", "squash", "rebase"):
        raise ValueError("method must be merge, squash, or rebase")
    args = ["pr", "merge", str(number), f"--{method}"]
    if delete_branch:
        args.append("--delete-branch")
    _gh(args)
    return {"merged": number, "method": method}


@mcp.tool()
def pr_checks(number: int) -> list[dict]:
    """
    Get the status of all CI checks on a PR.

    Args:
        number: PR number.
    """
    output = _gh(["pr", "checks", str(number), "--json", "name,state,conclusion,startedAt,completedAt,detailsUrl"])
    return json.loads(output)


# ---------------------------------------------------------------------------
# GitLab MR tools (requires glab CLI)
# ---------------------------------------------------------------------------


@mcp.tool()
def mr_list(state: str = "opened", limit: int = 20) -> list[dict]:
    """
    List GitLab merge requests.

    Args:
        state: "opened", "closed", "locked", or "merged" (default "opened").
        limit: Max MRs to return (default 20).
    """
    output = _glab(["mr", "list", "--state", state, "--output", "json", "-P", str(limit)])
    return json.loads(output)


@mcp.tool()
def mr_view(iid: int) -> dict:
    """
    Get details of a specific GitLab merge request.

    Args:
        iid: MR internal ID (the number shown in the UI).
    """
    output = _glab(["mr", "view", str(iid), "--output", "json"])
    return json.loads(output)


@mcp.tool()
def mr_create(
    title: str,
    description: str,
    source_branch: Optional[str] = None,
    target_branch: str = "main",
    draft: bool = False,
) -> dict:
    """
    Create a GitLab merge request from the current or specified branch.

    Args:
        title: MR title.
        description: MR description.
        source_branch: Source branch (default: current branch).
        target_branch: Target branch (default "main").
        draft: Open as draft MR (default false).
    """
    args = ["mr", "create", "--title", title, "--description", description,
            "--target-branch", target_branch]
    if source_branch:
        args += ["--source-branch", source_branch]
    if draft:
        args.append("--draft")
    output = _glab(args)
    return {"output": output}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
