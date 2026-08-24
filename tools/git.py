import config

from .subprocess_utils import run_bounded


def git_status():
    """Show the current Git branch and working tree status."""

    return run_bounded(
        ["git", "status", "--short", "--branch"],
        timeout=config.GIT_TIMEOUT_SECONDS,
        error_label="Git",
    )


def git_diff():
    """Show the current uncommitted Git diff."""

    return run_bounded(
        ["git", "diff", "--no-ext-diff"],
        timeout=config.GIT_TIMEOUT_SECONDS,
        error_label="Git diff",
    )