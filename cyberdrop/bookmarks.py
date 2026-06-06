"""
Domain model for bookmarks: Link, Creator, Bookmarks.
Owns YAML serialisation (Bookmarks.load / Bookmarks.save).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Link:
    name: str
    url: str
    downloaded: bool = False


@dataclass
class Creator:
    name: str
    links: list[Link] = field(default_factory=list)
    consolidation_path: str | None = None


@dataclass
class Bookmarks:
    creators: list[Creator] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Bookmarks":
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls._from_dict(data)

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self._to_dict(), f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    @classmethod
    def _from_dict(cls, data: dict) -> "Bookmarks":
        creators = []
        for c in data.get("creators", []):
            links = []
            for i, lnk in enumerate(c.get("links", [])):
                if isinstance(lnk, str):
                    links.append(Link(name=f"Link {i + 1}", url=lnk))
                else:
                    links.append(Link(
                        name=lnk.get("name", f"Link {i + 1}"),
                        url=lnk.get("url", ""),
                        downloaded=lnk.get("downloaded", False),
                    ))
            creators.append(Creator(
                name=c.get("name", "Unknown"),
                links=links,
                consolidation_path=c.get("consolidation_path"),
            ))
        return cls(creators=creators)

    def _to_dict(self) -> dict:
        result: dict = {"creators": []}
        for c in self.creators:
            c_dict: dict = {"name": c.name}
            if c.consolidation_path:
                c_dict["consolidation_path"] = c.consolidation_path
            c_dict["links"] = [
                {"name": lnk.name, "url": lnk.url, "downloaded": lnk.downloaded}
                for lnk in c.links
            ]
            result["creators"].append(c_dict)
        return result

    def find_creator(self, name: str) -> "Creator | None":
        lower = name.lower()
        return next((c for c in self.creators if c.name.lower() == lower), None)

    def add_link(self, creator_name: str, url: str, link_name: str | None = None) -> Link:
        creator = self.find_creator(creator_name)
        if creator is None:
            creator = Creator(name=creator_name)
            self.creators.append(creator)
        if link_name is None:
            link_name = f"{creator_name} {len(creator.links) + 1}"
        lnk = Link(name=link_name, url=url)
        creator.links.append(lnk)
        return lnk
