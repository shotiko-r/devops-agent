import subprocess

import config

from .files import PROJECT_ROOT


def run_command(command: str):
    """Run a shell command inside the project.

    Approval is enforced by the ToolRegistry boundary, not here.
    """

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=config.SHELL_COMMAND_TIMEOUT_SECONDS,
        )

        output = ""

        if result.stdout:
            output += result.stdout

        if result.stderr:
            output += "\nSTDERR:\n" + result.stderr

        output += f"\nExit code: {result.returncode}"

        return output

    except subprocess.TimeoutExpired:
        return (
            f"Command timed out after "
            f"{config.SHELL_COMMAND_TIMEOUT_SECONDS} seconds."
        )

    except Exception as e:
        return f"Command execution error: {e}"