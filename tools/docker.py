import config

from .subprocess_utils import run_bounded


def docker_ps():
    """Show currently running Docker containers."""

    return run_bounded(
        ["docker", "ps"],
        timeout=config.DOCKER_TIMEOUT_SECONDS,
        error_label="Docker",
    )


def docker_images():
    """Show Docker images available locally."""

    return run_bounded(
        ["docker", "images"],
        timeout=config.DOCKER_TIMEOUT_SECONDS,
        error_label="Docker",
    )


def docker_logs(container: str, tail: int = 100):
    """Show recent logs from a Docker container."""

    return run_bounded(
        ["docker", "logs", "--tail", str(tail), container],
        timeout=config.DOCKER_TIMEOUT_SECONDS,
        error_label="Docker logs",
    )


def docker_inspect(container: str):
    """Inspect a Docker container."""

    return run_bounded(
        ["docker", "inspect", container],
        timeout=config.DOCKER_TIMEOUT_SECONDS,
        error_label="Docker inspect",
    )