# Extracted verbatim from PDM (MIT). See provenance.json and LICENSE.
from __future__ import annotations

class Candidate:
    def __init__(
        self,
        req: Requirement,
        name: str | None = None,
        version: str | None = None,
        link: Link | None = None,
        installed: im.Distribution | None = None,
    ):
        """
        :param req: the requirement that produces this candidate.
        :param name: the name of the candidate.
        :param version: the version of the candidate.
        :param link: the file link of the candidate.
        """
        self.req = req
        self.name = name or self.req.project_name
        self.version = version
        if link is None and not req.is_named:
            link = cast("Link", req.as_file_link())  # type: ignore[attr-defined]
        self.link = link
        self.summary = ""
        self.hashes: list[FileHash] = []
        self.requested = False
        self.installed: im.Distribution | None = installed

        self._requires_python: str | None = None
        self._prepared: PreparedCandidate | None = None
        self._revision = getattr(req, "revision", None)


    def identify(self) -> str:
        return self.req.identify()


    def __str__(self) -> str:
        if self.req.is_named:
            return f"{self.name}@{self.version}"
        assert self.link is not None
        return f"{self.name}@{self.link.url_without_fragment}"


