"""Resolve the git commit the running ReDU app and its metadata workflow were built from.

The deployed container makes this awkward in two ways: git is not installed in the
image (see Dockerfile), and `workflows/` is a bind mount rather than part of the
build context (see .dockerignore / docker-compose.yml). So the commit is read by
parsing the .git plumbing directly in Python, with an env-var override for
deployments that build without .git present and a git CLI fallback for the cases
plumbing parsing does not cover (worktrees, unusual layouts).
"""
import os
import subprocess
import time

APP_ROOT = os.path.dirname(os.path.realpath(__file__))
WORKFLOW_PATH = os.path.join(APP_ROOT, "workflows", "PublicDataset_ReDU_Metadata_Workflow")

REDU_REPO_URL = "https://github.com/Wang-Bioinformatics-Lab/ReDU-MS2-GNPS2"
WORKFLOW_REPO_URL = "https://github.com/Wang-Bioinformatics-Lab/PublicDataset_ReDU_Metadata_Workflow"

# The workflow lives on a bind mount and can be updated under a running container,
# so the answer is cached briefly rather than for the process lifetime.
_CACHE_TTL_SECONDS = 300
_cache = {}


def _resolve_git_dir(repo_path):
    """Return the .git directory for repo_path, following the gitdir: indirection
    that submodules and worktrees use. Returns None if there is no git metadata."""
    dot_git = os.path.join(repo_path, ".git")
    if os.path.isdir(dot_git):
        return dot_git
    if os.path.isfile(dot_git):
        # Submodule: a file containing "gitdir: ../../.git/modules/<name>"
        try:
            with open(dot_git, "r") as handle:
                content = handle.read().strip()
        except OSError:
            return None
        if content.startswith("gitdir:"):
            target = content.split(":", 1)[1].strip()
            if not os.path.isabs(target):
                target = os.path.join(repo_path, target)
            target = os.path.normpath(target)
            if os.path.isdir(target):
                return target
    return None


def _commit_from_git_files(repo_path):
    """Read HEAD without invoking git, since git is absent from the image."""
    git_dir = _resolve_git_dir(repo_path)
    if git_dir is None:
        return None
    try:
        with open(os.path.join(git_dir, "HEAD"), "r") as handle:
            head = handle.read().strip()
    except OSError:
        return None

    if not head.startswith("ref:"):
        # Detached HEAD already holds the sha
        return head or None

    ref_name = head.split(":", 1)[1].strip()

    # Loose ref
    ref_path = os.path.join(git_dir, *ref_name.split("/"))
    try:
        with open(ref_path, "r") as handle:
            return handle.read().strip() or None
    except OSError:
        pass

    # Packed ref
    try:
        with open(os.path.join(git_dir, "packed-refs"), "r") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith(("#", "^")):
                    continue
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[1].strip() == ref_name:
                    return parts[0].strip()
    except OSError:
        pass

    return None


def _git(repo_path, *args):
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _commit_from_git_cli(repo_path):
    if not os.path.isdir(repo_path):
        return None

    # git searches parent directories, so an un-checked-out submodule would other-
    # wise report the SUPERPROJECT's commit as the workflow version. Confirm the
    # repo git found is actually the one asked for before trusting the answer.
    toplevel = _git(repo_path, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    if os.path.realpath(toplevel) != os.path.realpath(repo_path):
        return None

    return _git(repo_path, "rev-parse", "HEAD")


def _resolve_commit(repo_path, env_var):
    override = os.environ.get(env_var, "").strip()
    if override:
        return override
    return _commit_from_git_files(repo_path) or _commit_from_git_cli(repo_path)


def get_versions():
    """Return {'redu': {...}, 'workflow': {...}} with 'short', 'full' and 'url' keys.

    'short' is "unknown" when the commit cannot be determined, so callers can render
    the indicator unconditionally without guarding.
    """
    now = time.time()
    cached = _cache.get("versions")
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    versions = {}
    for key, repo_path, env_var, repo_url in (
        ("redu", APP_ROOT, "REDU_COMMIT", REDU_REPO_URL),
        ("workflow", WORKFLOW_PATH, "REDU_WORKFLOW_COMMIT", WORKFLOW_REPO_URL),
    ):
        commit = _resolve_commit(repo_path, env_var)
        versions[key] = {
            "full": commit,
            "short": commit[:7] if commit else "unknown",
            "url": "{}/commit/{}".format(repo_url, commit) if commit else repo_url,
        }

    _cache["versions"] = (now, versions)
    return versions
