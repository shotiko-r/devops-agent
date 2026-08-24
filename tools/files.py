from pathlib import Path


PROJECT_ROOT = Path.cwd()


def safe_path(path: str) -> Path:
    """Resolve a path and prevent access outside the project."""

    target = (PROJECT_ROOT / path).resolve()

    try:
        target.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        raise ValueError(
            "Access denied: path is outside the project directory."
        )

    return target


def read_file(path: str):
    """Read a text file inside the project."""

    target = safe_path(path)

    if not target.exists():
        return f"File not found: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    try:
        return target.read_text()
    except Exception as e:
        return f"Read error: {e}"


def write_file(path: str, content: str):
    """Write a text file inside the project.

    Approval is enforced by the ToolRegistry boundary, not here.
    """

    target = safe_path(path)

    try:
        target.write_text(content)
        return f"File successfully written: {path}"
    except Exception as e:
        return f"Write error: {e}"