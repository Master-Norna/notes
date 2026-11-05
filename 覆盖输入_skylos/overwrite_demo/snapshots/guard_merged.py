"""Output guard excerpted from skylos ``sbom_cmd.py`` at 7eff6a5.

Same condition as ``guard_parent.py`` plus the thirteen names added by
merge 7eff6a5.  See ``upstream/sbom_cmd_merged.py`` for the complete file.
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
            "bun.lock",
            "cargo.lock",
            "cargo.toml",
            "composer.lock",
            "composer.json",
            "gemfile.lock",
            "pubspec.lock",
            "pubspec.yaml",
            "gradle.lockfile",
            "packages.lock.json",
            "pom.xml",
            "setup.py",
            "setup.cfg",
        }
        or Path(output).suffix.casefold() == ".csproj"
    )
