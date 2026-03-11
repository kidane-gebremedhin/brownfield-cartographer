"""Safe subprocess utilities.

- No shell=True
- Explicit argument lists only
- Captures stdout/stderr
- Raises clear exceptions
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    def __init__(self, message: str, result: CommandResult):
        super().__init__(message)
        self.result = result


def run_cmd(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    timeout_s: int = 120,
    env: dict[str, str] | None = None,
) -> CommandResult:
    if not args:
        raise ValueError('args must be non-empty')

    cwd_path = str(Path(cwd).resolve()) if cwd is not None else None

    try:
        cp = subprocess.run(
            args,
            cwd=cwd_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as e:
        logger.error('Executable not found: %s', args[0])
        raise
    except subprocess.TimeoutExpired as e:
        logger.error('Command timed out after %ss: %s', timeout_s, ' '.join(args))
        raise

    result = CommandResult(args=list(args), returncode=cp.returncode, stdout=cp.stdout or '', stderr=cp.stderr or '')

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or '(no output)'
        logger.error('Command failed (exit %s): %s', result.returncode, msg)
        raise CommandError(f'Command failed (exit {result.returncode}): {msg}', result)

    return result
