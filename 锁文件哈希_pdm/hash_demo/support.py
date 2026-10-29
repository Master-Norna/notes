"""Small, explicit environment adapters, NOT replacement PDM hash logic.

Only unmarked named packages and direct wheel archives are supported. All hash
loading/export loops and Candidate construction run verbatim upstream code.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import itertools
import json
import os
from pathlib import Path
import posixpath
import re
import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import patch
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import url2pathname

HERE = Path(__file__).resolve().parent


def url_without_fragments(url):
    return urlunsplit(urlsplit(url)._replace(fragment=""))


def url_to_path(url):
    parsed = urlsplit(url)
    assert parsed.scheme == "file" and not parsed.netloc, url
    return url2pathname(parsed.path)


@contextmanager
def cd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class Link:
    """Subset of unearth.Link needed here: URL, fragment-free URL, filename."""
    def __init__(self, url):
        self.url = url
        self.url_without_fragment = url_without_fragments(url)
        self.filename = unquote(posixpath.basename(urlsplit(url).path))


class Requirement:
    """Fixture-only adapter, not a general PEP 508 parser/validator."""
    def __init__(self, name, data):
        assert not any(k in data for k in ("marker", "git", "hg", "svn", "bzr", "editable")), data
        self.name = name
        self.project_name = name
        self.key = re.sub(r"[-_.]+", "-", name).lower()
        self.version = data.get("version", "")
        self.editable = False
        self.extras = []
        self.groups = []
        self.marker = None
        self.is_named = type(self) is Requirement
        self.is_file_or_url = type(self) is FileRequirement
        self.is_vcs = False

    @classmethod
    def from_req_dict(cls, name, data):
        if "path" in data or "url" in data:
            return FileRequirement(name, data)
        return Requirement(name, data)

    def identify(self):
        return self.key

    def as_pinned_version(self, version):
        assert self.version == f"=={version}", (self.version, version)
        return self

    def as_line(self):
        return f"{self.name}{self.version}"

    def __str__(self):
        return self.as_line()


class FileRequirement(Requirement):
    def __init__(self, name, data):
        super().__init__(name, data)
        self.path = Path(data["path"]) if data.get("path") else None
        self.url = data.get("url") or ""
        self.subdirectory = data.get("subdirectory")
        # Match the URL fragment parsing used by these fixtures, without
        # claiming support for general requirement parsing.
        from urllib.parse import parse_qs
        fragment = parse_qs(urlsplit(self.url).fragment)
        if "subdirectory" in fragment:
            self.subdirectory = fragment["subdirectory"][0]
        self.is_local_dir = False

    @property
    def str_path(self):
        if self.path is None:
            return None
        text = self.path.as_posix()
        return text if text.startswith(("./", "../")) or self.path.is_absolute() else "./" + text

    def get_full_url(self):
        return url_without_fragments(self.url)

    def as_file_link(self):
        from urllib.parse import quote
        suffix = f"#subdirectory={quote(self.subdirectory)}" if self.subdirectory else ""
        return Link(self.get_full_url() + suffix)

    def as_line(self):
        return f"{self.name} @ {self.as_file_link().url}"


class VcsRequirement(Requirement):
    pass


class PdmUsageError(Exception):
    pass


class AnyMarker:
    pass


class UnsupportedEnvSpec:
    @staticmethod
    def from_spec(**kwargs):
        raise NotImplementedError("Target environment parsing is outside this demo")

    @staticmethod
    def from_marker(marker):
        raise NotImplementedError("Environment marker parsing is outside this demo")


@dataclass
class Package:
    candidate: object
    dependencies: object = None
    summary: str = ""
    marker: object = None


class TomlArray(list):
    def multiline(self, enabled):
        return self


def load_code():
    common = {
        "cast": cast, "Path": Path, "posixpath": posixpath, "itertools": itertools,
        "Requirement": Requirement, "FileRequirement": FileRequirement, "VcsRequirement": VcsRequirement,
        "AnyMarker": AnyMarker, "EnvSpec": UnsupportedEnvSpec, "cd": cd, "Package": Package,
        "url_to_path": url_to_path, "PdmUsageError": PdmUsageError,
        "tomlkit": SimpleNamespace(inline_table=dict, array=TomlArray),
        "make_inline_table": dict, "make_array": lambda values, **kwargs: list(values),
    }
    candidate = runpy.run_path(str(HERE / "upstream/candidate.py"), init_globals=common)["Candidate"]
    common["Candidate"] = candidate
    readers = {label: runpy.run_path(str(HERE / f"upstream/{label}.py"), init_globals=common)["LockedRepository"]
               for label in ("before", "after")}
    export = runpy.run_path(str(HERE / "upstream/requirements.py"), init_globals=common)["export"]
    converter = runpy.run_path(str(HERE / "upstream/pylock.py"), init_globals=common)["PyLockConverter"]
    return candidate, readers, export, converter


CANDIDATE, READERS, EXPORT, CONVERTER = load_code()


def read_lock(label, lock, root):
    import copy
    repository = READERS[label]()  # Only the extracted methods; no BaseRepository initialization.
    repository.environment = SimpleNamespace(project=SimpleNamespace(
        root=root, backend=SimpleNamespace(expand_line=lambda url: url)))
    repository.packages = {}
    repository.targets = []
    repository._read_lockfile(copy.deepcopy(lock))  # Upstream reader pops package.name.
    return repository


def export_requirements(candidate, hashes=True):
    options = SimpleNamespace(hashes=hashes, expandvars=False, self=False, editable_self=False)
    project = SimpleNamespace(backend=SimpleNamespace(expand_line=lambda line, expandvars: line),
                              get_sources=lambda **kwargs: [])
    candidate_module = ModuleType("pdm.models.candidates")
    candidate_module.Candidate = CANDIDATE
    # The real export function has one local import. Supply the same extracted
    # Candidate class, without installing PDM or any third-party package.
    with patch.dict(sys.modules, {"pdm.models.candidates": candidate_module}):
        return EXPORT(project, [candidate], options)


def export_pylock_package(package):
    return CONVERTER().make_package(package)
