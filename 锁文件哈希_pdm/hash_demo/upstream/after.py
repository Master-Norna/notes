# Extracted verbatim from PDM (MIT). See provenance.json and LICENSE.
from __future__ import annotations

class LockedRepository:
    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        if lockfile.get("lock-version"):
            return self._read_pylock(lockfile)
        else:
            return self._read_pdm_lock(lockfile)


    def _read_pylock(self, lockfile: Mapping[str, Any]) -> None:
        root = self.environment.project.root

        if "targets" in lockfile.get("tool", {}).get("pdm", {}):
            self.targets = [EnvSpec.from_spec(**t) for t in lockfile["tool"]["pdm"]["targets"]]
        else:
            for marker in lockfile.get("environments", []):  # pragma: no cover
                self.targets.append(EnvSpec.from_marker(get_marker(cast(str, marker))))

        with cd(root):
            for package in lockfile.get("packages", []):
                group_marker = AnyMarker()
                package_name = package.pop("name")
                req_dict: dict[str, str | bool] = {}
                if "version" in package:
                    req_dict["version"] = f"=={package['version']}"
                if "marker" in package:
                    package_marker = get_marker(cast(str, package["marker"]))
                    req_marker = exclude_multi(package_marker, "extras", "dependency_groups")
                    group_marker = package_marker.inner.only("extras", "dependency_groups")
                    if not req_marker.is_any():
                        req_dict["marker"] = str(req_marker)
                if vcs := package.get("vcs"):  # pragma: no cover
                    req_dict[vcs["type"]] = vcs["url"]
                    req_dict["ref"] = vcs.get("requested-revision")
                    req_dict["revision"] = vcs.get("commit-id")
                    req_dict["subdirectory"] = vcs.get("subdirectory")
                elif directory := package.get("directory"):  # pragma: no cover
                    req_dict["path"] = directory["path"]
                    req_dict["editable"] = directory.get("editable", False)
                    req_dict["subdirectory"] = directory.get("subdirectory")
                elif archive := package.get("archive"):  # pragma: no cover
                    req_dict["url"] = archive.get("url")
                    req_dict["path"] = archive.get("path")
                    req_dict["subdirectory"] = archive.get("subdirectory")
                req = Requirement.from_req_dict(package_name, req_dict)
                if req.is_file_or_url and req.path and not req.url:  # type: ignore[attr-defined]
                    req.url = root.joinpath(req.path).as_uri()  # type: ignore[attr-defined]
                candidate = Candidate(req=req, name=package_name, version=package.get("version"))
                candidate.requires_python = package.get("requires-python", "")
                if archive := package.get("archive"):
                    link = candidate.link
                    assert link is not None
                    candidate.hashes = [
                        {"url": link.url_without_fragment, "file": link.filename, "hash": f"{algo}:{value}"}
                        for algo, value in archive.get("hashes", {}).items()
                    ]
                for artifact in itertools.chain(
                    package.get("wheels", []), [sdist] if (sdist := package.get("sdist")) else []
                ):
                    algo, hash_value = next(iter(artifact["hashes"].items()))
                    hash_item: FileHash = {"hash": f"{algo}:{hash_value}"}
                    if "url" in artifact:
                        hash_item["url"] = artifact["url"]
                    if "name" in artifact:
                        hash_item["file"] = artifact["name"]
                    candidate.hashes.append(hash_item)
                dependencies = package.get("tool", {}).get("pdm", {}).get("dependencies")
                self.packages[self._identify_candidate(candidate)] = Package(candidate, dependencies, "", group_marker)


    def _identify_candidate(self, candidate: Candidate) -> CandidateKey:
        url: str | None = None
        if not candidate.req.is_named and candidate.link is not None:
            url = candidate.link.url_without_fragment
            url = self.environment.project.backend.expand_line(cast(str, url))
            if url.startswith("file://"):
                path = posixpath.normpath(url_to_path(url))
                url = Path(path).as_uri()
        return (
            candidate.identify(),
            candidate.version if not url else None,
            url,
            candidate.req.editable,
        )


    def get_hashes(self, candidate: Candidate) -> list[FileHash]:
        return candidate.hashes


