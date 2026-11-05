"""Output guard excerpted from skylos ``sbom_cmd.py`` at b529347.

The condition below is copied from ``run_sbom_command`` (parent of merge
7eff6a5); only ``args.output`` became the ``output`` argument.  See
``upstream/sbom_cmd_parent.py`` for the complete file.
"""

from __future__ import annotations

from pathlib import Path


def is_protected_output(output: str) -> bool:
    return output != "-" and (
        Path(output).name.casefold()
        in {
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "go.mod",
            "uv.lock",
            "package-lock.json",
            "pnpm-lock.yaml",
            "poetry.lock",
            "yarn.lock",
            "pipfile.lock",
            "npm-shrinkwrap.json",
        }
        or Path(output).suffix.casefold() == ".csproj"
    )
