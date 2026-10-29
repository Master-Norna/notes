# Extracted verbatim from PDM (MIT). See provenance.json and LICENSE.
from __future__ import annotations

class PyLockConverter:
    def make_package(self, package: Package) -> dict[str, Any]:
        req = package.candidate.req
        candidate = package.candidate
        result: dict[str, Any] = {
            "name": candidate.req.key,
            "version": candidate.version,
        }
        if candidate.requires_python:
            result["requires-python"] = candidate.requires_python
        if isinstance(req, VcsRequirement):
            result["vcs"] = {
                "type": req.vcs,
                "url": req.repo,
                "commit-id": candidate.get_revision(),
            }
            if req.ref:
                result["vcs"]["requested-revision"] = req.ref
            if req.subdirectory:
                result["vcs"]["subdirectory"] = req.subdirectory
        elif isinstance(req, FileRequirement):
            if req.is_local_dir:
                result["directory"] = {
                    "path": req.str_path,
                    "editable": req.editable,
                }
                if req.subdirectory:
                    result["directory"]["subdirectory"] = req.subdirectory
            else:
                archive: dict[str, Any]
                archive = result["archive"] = {"url": req.get_full_url()}
                if req.path:
                    archive["path"] = req.str_path
                for hash_item in candidate.hashes:
                    hash_type, hash_value = hash_item["hash"].split(":", 1)
                    archive.setdefault("hashes", tomlkit.inline_table())[hash_type] = hash_value
        else:
            wheels: list[dict[str, Any]] = tomlkit.array().multiline(True)
            for hash_item in candidate.hashes:
                hash_type, hash_value = hash_item["hash"].split(":", 1)
                if hash_item.get("file", "").endswith(".whl") or hash_item.get("url", "").endswith(".whl"):
                    wheel: dict[str, Any] = {}
                    if "file" in hash_item:
                        wheel["name"] = hash_item["file"]
                    if "url" in hash_item:
                        wheel["url"] = hash_item["url"]
                    wheel["hashes"] = make_inline_table({hash_type: hash_value})
                    wheels.append(wheel)
                else:
                    sdist: dict[str, Any] = {}
                    if "file" in hash_item:
                        sdist["name"] = hash_item["file"]
                    if "url" in hash_item:
                        sdist["url"] = hash_item["url"]
                    sdist["hashes"] = make_inline_table({hash_type: hash_value})
                    result["sdist"] = make_inline_table(sdist)
            if wheels:
                result["wheels"] = wheels

            if package.dependencies is not None:
                result["tool"] = {"pdm": {"dependencies": make_array(package.dependencies, multiline=True)}}

        return result


