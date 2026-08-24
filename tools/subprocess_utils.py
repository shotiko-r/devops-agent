"""
Shared subprocess runner with a bounded timeout.

Every subprocess operation in the project must have a bounded
execution time so a hung command can never freeze the agent.
Timeouts produce a controlled error string instead of raising.
"""

import subprocess

import config


def run_bounded(
    args: list[str],
    timeout: int | None = None,
    error_label: str = "Command",
    cwd: str | None = None,
) -> str:
    """Run a subprocess and return stdout, or a controlled error string.

    Never raises and never blocks indefinitely.
    """
    if timeout is None:
        timeout = config.SUBCOMMAND_TIMEOUT_SECONDS

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return f"{error_label} error:\nCommand timed out after {timeout} seconds."
    except FileNotFoundError:
        return f"{error_label} error:\nExecutable not found: {args[0]}"
    except Exception as exc:  # noqa: BLE001 - deliberate isolation
        return f"{error_label} error:\n{exc}"

    if result.returncode != 0:
        return f"{error_label} error:\n{result.stderr}"

    return result.stdout