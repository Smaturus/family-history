#!/usr/bin/env python3
"""Generate family archive website from data/family.yaml and content/content.yaml."""

from __future__ import annotations

import html
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from collections import Counter

from parse_data import (
    Family,
    Person,
    canonical_place,
    counted,
    direct_lines,
    format_date,
    genitive_given_name,
    load_family,
    plural,
    stats,
    year_only,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "family.yaml"
CONTENT_PATH = ROOT / "content" / "content.yaml"
OUTPUT_PATH = ROOT / "index.html"
CSS = ROOT / "assets" / "site.css"
# Master artwork stays in the repo; published hero uses optimized derivatives
# generated from assets/Image 1.png (AVIF → WebP → JPEG, responsive widths).
HERO_IMAGE_SRC = "assets/Image 1.png"
HERO_IMAGE_AVIF = "assets/hero-bg.avif"
HERO_IMAGE_WEBP = "assets/hero-bg.webp"
HERO_IMAGE_JPG = "assets/hero-bg.jpg"
HERO_IMAGE_AVIF_MD = "assets/hero-bg-1280.avif"
HERO_IMAGE_WEBP_MD = "assets/hero-bg-1280.webp"
HERO_IMAGE_JPG_MD = "assets/hero-bg-1280.jpg"
HERO_IMAGE_AVIF_SM = "assets/hero-bg-768.avif"
HERO_IMAGE_WEBP_SM = "assets/hero-bg-768.webp"
HERO_IMAGE_JPG_SM = "assets/hero-bg-768.jpg"
HERO_SRCSET_AVIF = (
    f"{HERO_IMAGE_AVIF_SM} 768w, {HERO_IMAGE_AVIF_MD} 1280w, {HERO_IMAGE_AVIF} 1376w"
)
HERO_SRCSET_WEBP = (
    f"{HERO_IMAGE_WEBP_SM} 768w, {HERO_IMAGE_WEBP_MD} 1280w, {HERO_IMAGE_WEBP} 1376w"
)
HERO_SRCSET_JPG = (
    f"{HERO_IMAGE_JPG_SM} 768w, {HERO_IMAGE_JPG_MD} 1280w, {HERO_IMAGE_JPG} 1376w"
)
HERO_SIZES = "100vw"
# Hero date labels from the approved layout (Image 2): plain year text only.
# Positions are % of the hero frame (centers), measured on Image 2.
HERO_YEAR_SLOTS = [
    ("1834", 56.0, 11.4),
    ("1858", 87.7, 13.0),
    ("1870", 91.6, 46.5),
    ("1918", 95.2, 59.5),
    ("1945", 51.0, 66.9),
    ("1956", 42.4, 74.2),
    ("2001", 84.5, 73.5),
]
# Subtle dotted leaders under 1834 / 1858 (layout from Image 2; not in Image 1).
# Each: (top%, left%, width%, nodes) — nodes is "left", "right", or "both".
HERO_YEAR_LEADERS = [
    (16.13, 54.0, 7.3, "left"),   # under 1834
    (14.62, 80.2, 14.8, "both"),  # under 1858
]

STATUS_BADGE_W = {"ok": 100, "hyp": 74, "q": 86}
BADGE_H = 16

BOX_W = 214
BOX_H = 78
COL_W = 242
ROW_H = 92
TOP_PAD = 56
LEFT_PAD = 18

# Hero constellation: an open, airy branching network on a near-black field.
# It is a *background composition*, not an object: the primary ridges run past
# the viewBox on the top, right and bottom, the page crops them mid-stroke, so
# the network reads as a larger structure drifting beyond the frame. Only the
# left side (towards the headline) dissolves into the black instead of exiting.
HERO_VIEW_W = 780
HERO_VIEW_H = 720
# Fixed seed keeps the generated network identical between builds.
HERO_SEED = 1834
# Primary ridges. Each polyline starts on an earlier ridge, so the structure
# reads as one growing web: A is the trunk, B/C/D/E/F fork off it, G braids
# across the top, H/I close loops, and the arms fray outwards. The interior
# arrangement is fixed; the terminal points continue past the frame edges.
HERO_RIDGES = [
    # A — trunk: enters from below the frame, leaves through the top right
    [(332, 758), (352, 690), (378, 628), (340, 564), (392, 498), (372, 432),
     (436, 372), (470, 306), (508, 240), (556, 176), (612, 132), (686, 96),
     (744, 58), (808, 18)],
    # B — upper-left limb
    [(436, 372), (398, 330), (356, 300), (322, 246), (300, 196), (268, 150)],
    # C — long left reach down to the documentary anchor; its tail dies in the
    # dissolve zone towards the headline instead of exiting the frame
    [(392, 498), (344, 478), (296, 462), (232, 486), (176, 516), (124, 556),
     (86, 588), (36, 620)],
    # D — right limb, exits right
    [(508, 240), (566, 262), (620, 272), (676, 306), (722, 346), (784, 388),
     (832, 420)],
    # E — right descent, exits bottom right
    [(470, 306), (516, 352), (556, 404), (612, 468), (654, 522), (692, 570),
     (738, 634), (774, 700)],
    # F — lower limb, exits bottom
    [(378, 628), (428, 646), (486, 664), (548, 672), (596, 690), (650, 716),
     (696, 748)],
    # G — braid across the top, exits top
    [(556, 176), (508, 152), (452, 148), (404, 122), (352, 96), (312, 66),
     (282, 8), (262, -44)],
    # H — braid closing the lower-left loop
    [(232, 486), (286, 552), (352, 592), (428, 646)],
    # I — braid closing the right loop
    [(722, 346), (702, 402), (656, 438), (612, 468)],
    # frayed arms, most of them running off the frame
    [(268, 150), (222, 116), (198, 70), (176, 6), (162, -40)],
    [(340, 564), (282, 596), (238, 640), (208, 686), (186, 742)],
    [(620, 272), (650, 214), (694, 178), (734, 136), (772, 96), (802, 56)],
    [(556, 404), (600, 388), (652, 372), (716, 356), (772, 348)],
    [(296, 462), (262, 408), (246, 356)],
]
# Depth plane of each ridge, in the order above. The trunk and the two long
# reaches (A, C, E) come forward and stay in focus; the limbs braid through the
# middle; the closing braids and the frayed arms fall back out of focus behind
# the haze. Same silhouette, three planes.
HERO_RIDGE_PLANES = (
    "near", "mid", "near", "mid", "near", "mid", "mid",
    "far", "far", "far", "far", "far", "far", "far",
)
# Birth-year labels of the paternal line, newest first, pinned to points on
# the ridges like floating annotations around the network. The third value is
# the label side (1 = right of the node, -1 = left). The right edge of the
# composition leaves the screen, so labels near it sit on the inner side.
HERO_YEAR_ANCHORS = [
    (612, 132, -1),
    (452, 148, -1),
    (620, 272, -1),
    (322, 246, -1),
    (654, 522, -1),
    (296, 462, -1),
    (340, 564, -1),
]
# Documentary anchor: the 1834 revision list of Mokroe (not a birth year) sits
# at the far end of the oldest reach — Fedot, Grigory and Ilya.
HERO_ANCHOR = (124, 556, -1)
HERO_ANCHOR_LABEL = "1834"
# Nebula blooms behind the densest junctions: (cx, cy, r, opacity tier).
HERO_BLOOMS = [
    (392, 498, 168, 1),
    (470, 306, 152, 1),
    (300, 462, 132, 2),
    (556, 176, 138, 2),
    (620, 272, 120, 2),
    (428, 646, 126, 2),
    (640, 486, 108, 3),
    (330, 250, 104, 3),
]
# Major junctions where the light pools: (x, y, flare angle, flare scale). The
# first two values also drive the luminance field, so brightness concentrates
# here and the outer reaches stay thin and dim.
HERO_CORES = [
    (392, 498, -22, 1.0),
    (470, 306, -52, 0.94),
    (556, 176, -36, 0.7),
    (612, 468, 42, 0.62),
]
# Braided zones (dense weave) and void pockets (mesh nearly gone). Density is
# never uniform, so the triangulation stops reading as a diagram.
HERO_DENSE = [
    (392, 498, 116),
    (470, 306, 104),
    (556, 176, 84),
    (620, 272, 82),
    (428, 646, 80),
    (296, 462, 74),
]
HERO_VOIDS = [
    (214, 296, 132),
    (700, 618, 158),
    (312, 118, 118),
    (150, 664, 116),
    (536, 556, 96),
]
# Far translucent veils drifting behind the structure: (cx, cy, rx, ry, rot,
# tier). Tier 1 sits deepest and widest, tier 3 is a small drifting scrap.
HERO_VEILS = [
    (306, 424, 258, 186, -18, 1),
    (566, 296, 236, 202, 26, 1),
    (452, 618, 262, 152, -8, 2),
    (628, 168, 188, 146, 34, 2),
    (246, 218, 168, 148, 12, 3),
    (676, 470, 156, 168, -24, 3),
]
# Lit haze pockets that catch the glow of the trunk. The former dark occluding
# pockets are gone: near-black smoke masses read as a body in fog, and the
# composition must stay an open network, not an object.
HERO_FOG = [
    (430, 296, 128, 108, 8, "lit"),
    (388, 520, 114, 92, -30, "lit"),
]
# Foreground wisps: a little atmosphere in front of even the brightest ridges,
# so the crystal is seen through air rather than pressed against the glass.
HERO_WISPS = [
    (500, 396, 210, 150, -16),
    (300, 610, 176, 120, 24),
]
# Anisotropic flare streaks along a few main diagonals only:
# (x1, y1, x2, y2, width, tier).
HERO_STREAKS = [
    (372, 432, 686, 96, 30, 1),
    (392, 498, 124, 556, 22, 2),
    (470, 306, 692, 570, 26, 2),
    (556, 176, 312, 66, 18, 3),
]


def load_content() -> dict[str, Any]:
    """Load editorial texts from content/content.yaml."""
    with CONTENT_PATH.open(encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    validate_content(content)
    return content


def require_keys(data: dict[str, Any], path: str, keys: list[str]) -> None:
    """Fail fast with a clear error when editable YAML misses required keys."""
    missing = [key for key in keys if key not in data]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"Missing required key(s) in content/content.yaml at {path}: {missing_list}")


def require_mapping(data: Any, path: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in content/content.yaml at {path}")
    return data


def require_list(data: Any, path: str, min_len: int = 0) -> list[Any]:
    if not isinstance(data, list):
        raise ValueError(f"Expected list in content/content.yaml at {path}")
    if len(data) < min_len:
        raise ValueError(
            f"Expected at least {min_len} item(s) in content/content.yaml at {path}, got {len(data)}"
        )
    return data


def require_str(data: Any, path: str) -> str:
    if not isinstance(data, str):
        raise ValueError(f"Expected string in content/content.yaml at {path}")
    return data


def validate_branch(branch: Any, path: str) -> None:
    branch = require_mapping(branch, path)
    require_keys(branch, path, ["tag", "title", "basis", "paragraphs"])
    require_list(branch["paragraphs"], f"{path}.paragraphs")
    for key in ("tag", "title", "basis"):
        require_str(branch[key], f"{path}.{key}")


def validate_content(content: Any) -> None:
    """Schema checks for editor-facing YAML used by the generator."""
    content = require_mapping(content, "root")
    require_keys(
        content,
        "root",
        ["meta", "hero", "about", "archive", "archive_search", "sections", "tree", "footer"],
    )

    meta = require_mapping(content["meta"], "meta")
    require_keys(meta, "meta", ["title", "brand", "nav_items"])
    nav_items = require_list(meta["nav_items"], "meta.nav_items", min_len=1)
    for index, item in enumerate(nav_items):
        path = f"meta.nav_items[{index}]"
        item = require_mapping(item, path)
        require_keys(item, path, ["label", "target"])
        require_str(item["label"], f"{path}.label")
        require_str(item["target"], f"{path}.target")

    hero = require_mapping(content["hero"], "hero")
    require_keys(hero, "hero", ["h1", "sub", "cta", "cta_target"])
    for key in ("h1", "sub", "cta", "cta_target"):
        require_str(hero[key], f"hero.{key}")

    about = require_mapping(content["about"], "about")
    require_keys(about, "about", ["label", "text"])
    require_str(about["label"], "about.label")
    require_str(about["text"], "about.text")

    archive = require_mapping(content["archive"], "archive")
    require_keys(archive, "archive", ["label", "title", "entry_link", "tree_link"])
    for key in ("label", "title", "entry_link", "tree_link"):
        require_str(archive[key], f"archive.{key}")

    archive_search = require_mapping(content["archive_search"], "archive_search")
    require_keys(
        archive_search,
        "archive_search",
        ["label", "placeholder", "all", "no_results", "in_tree", "show_in_tree"],
    )
    for key in ("label", "placeholder", "all", "no_results", "in_tree", "show_in_tree"):
        require_str(archive_search[key], f"archive_search.{key}")

    sections = require_mapping(content["sections"], "sections")
    require_keys(sections, "sections", ["matyukhiny", "skiba"])
    expected_branches = {
        "matyukhiny": ("matyukhin_father", "astafyev_mother"),
        "skiba": ("skiba_father", "potashkin_mother"),
    }
    for section_key in ("matyukhiny", "skiba"):
        path = f"sections.{section_key}"
        section = require_mapping(sections[section_key], path)
        require_keys(
            section,
            path,
            [
                "title", "root", "page_id", "tree_page_id", "entry", "lead",
                "tree_title", "tree_lead", "branches_label", "branches_title",
                "branches", "sources", "places", "chronicle", "gallery",
            ],
        )
        for key in (
            "title", "root", "page_id", "tree_page_id", "entry", "lead",
            "tree_title", "tree_lead", "branches_label", "branches_title",
        ):
            require_str(section[key], f"{path}.{key}")
        branches = require_mapping(section["branches"], f"{path}.branches")
        for branch_key in expected_branches[section_key]:
            validate_branch(branches.get(branch_key), f"{path}.branches.{branch_key}")

        if "collateral" in section:
            collateral = require_mapping(section["collateral"], f"{path}.collateral")
            require_keys(collateral, f"{path}.collateral", ["label", "title", "lead", "items"])
            require_str(collateral["label"], f"{path}.collateral.label")
            require_str(collateral["title"], f"{path}.collateral.title")
            require_str(collateral["lead"], f"{path}.collateral.lead")
            items = require_list(collateral["items"], f"{path}.collateral.items", min_len=2)
            for index, item in enumerate(items):
                validate_branch(item, f"{path}.collateral.items[{index}]")

        sources = require_mapping(section["sources"], f"{path}.sources")
        require_keys(sources, f"{path}.sources", ["label", "title", "items"])
        require_str(sources["label"], f"{path}.sources.label")
        require_str(sources["title"], f"{path}.sources.title")
        items = require_list(sources["items"], f"{path}.sources.items", min_len=1)
        for index, item in enumerate(items):
            item_path = f"{path}.sources.items[{index}]"
            item = require_mapping(item, item_path)
            require_keys(item, item_path, ["id", "kind", "title"])
            for key in ("id", "kind", "title"):
                require_str(item[key], f"{item_path}.{key}")
            for optional in ("date", "reference"):
                if optional in item:
                    require_str(item[optional], f"{item_path}.{optional}")
            if "paragraphs" in item:
                require_list(item["paragraphs"], f"{item_path}.paragraphs")
            if "people" in item:
                for person_id in require_list(item["people"], f"{item_path}.people"):
                    require_str(person_id, f"{item_path}.people[]")
            if "image" in item:
                image = require_mapping(item["image"], f"{item_path}.image")
                require_keys(image, f"{item_path}.image", ["src", "alt"])

        places = require_mapping(section["places"], f"{path}.places")
        require_keys(places, f"{path}.places", ["label", "title", "items"])
        require_str(places["label"], f"{path}.places.label")
        require_str(places["title"], f"{path}.places.title")
        items = require_list(places["items"], f"{path}.places.items", min_len=1)
        for index, item in enumerate(items):
            item_path = f"{path}.places.items[{index}]"
            item = require_mapping(item, item_path)
            require_keys(item, item_path, ["id", "name"])
            for key in ("id", "name"):
                require_str(item[key], f"{item_path}.{key}")
            for optional in ("match", "note"):
                if optional in item:
                    require_str(item[optional], f"{item_path}.{optional}")
            if "people" in item:
                for person_index, person in enumerate(
                    require_list(item["people"], f"{item_path}.people")
                ):
                    person_path = f"{item_path}.people[{person_index}]"
                    person = require_mapping(person, person_path)
                    require_keys(person, person_path, ["id", "relation"])
                    require_str(person["id"], f"{person_path}.id")
                    require_str(person["relation"], f"{person_path}.relation")
            if "documents" in item:
                for document_id in require_list(item["documents"], f"{item_path}.documents"):
                    require_str(document_id, f"{item_path}.documents[]")

        chronicle = require_mapping(section["chronicle"], f"{path}.chronicle")
        require_keys(chronicle, f"{path}.chronicle", ["label", "title", "events"])
        require_str(chronicle["label"], f"{path}.chronicle.label")
        require_str(chronicle["title"], f"{path}.chronicle.title")
        events = require_list(chronicle["events"], f"{path}.chronicle.events", min_len=1)
        for index, event in enumerate(events):
            event_path = f"{path}.chronicle.events[{index}]"
            event = require_mapping(event, event_path)
            require_keys(event, event_path, ["date", "title"])
            require_str(event["date"], f"{event_path}.date")
            require_str(event["title"], f"{event_path}.title")
            if "place" in event:
                require_str(event["place"], f"{event_path}.place")

        gallery = require_mapping(section["gallery"], f"{path}.gallery")
        require_keys(gallery, f"{path}.gallery", ["title", "photos"])
        require_str(gallery["title"], f"{path}.gallery.title")
        photos = require_list(gallery["photos"], f"{path}.gallery.photos")
        for index, photo in enumerate(photos):
            photo_path = f"{path}.gallery.photos[{index}]"
            photo = require_mapping(photo, photo_path)
            require_keys(photo, photo_path, ["src", "alt"])
            require_str(photo["src"], f"{photo_path}.src")
            require_str(photo["alt"], f"{photo_path}.alt")

    if "person_biographies" in content:
        biographies = require_mapping(content["person_biographies"], "person_biographies")
        for person_id, text in biographies.items():
            require_str(text, f"person_biographies.{person_id}")

    tree = require_mapping(content["tree"], "tree")
    require_keys(
        tree,
        "tree",
        [
            "label", "h1", "column_titles", "status", "missing_father", "missing_mother",
            "search", "controls", "legend",
        ],
    )
    require_list(tree["column_titles"], "tree.column_titles", min_len=6)
    require_keys(require_mapping(tree["status"], "tree.status"), "tree.status", ["ok", "hyp", "q"])
    search = require_mapping(tree["search"], "tree.search")
    require_keys(search, "tree.search", ["label", "placeholder", "local", "global", "no_results"])
    controls = require_mapping(tree["controls"], "tree.controls")
    require_keys(controls, "tree.controls", ["group", "zoom_out", "zoom_in", "fit", "reset"])
    require_keys(
        require_mapping(tree["legend"], "tree.legend"),
        "tree.legend",
        ["unknown", "approx", "ok", "hyp", "q"],
    )
    require_str(tree["missing_father"], "tree.missing_father")
    require_str(tree["missing_mother"], "tree.missing_mother")

    footer = require_mapping(content["footer"], "footer")
    require_keys(footer, "footer", ["brand"])
    require_str(footer["brand"], "footer.brand")


def esc(text: str) -> str:
    return html.escape((text or "").rstrip(), quote=True)


def rich(text: str) -> str:
    """Trusted HTML from content.yaml (bold tags, spans)."""
    return (text or "").strip()


def paragraphs_html(paragraphs: list[str]) -> str:
    return "".join(f"<p>{rich(paragraph)}</p>" for paragraph in paragraphs)


def chain_text(people: list[Person]) -> str:
    return " → ".join(
        f"<b>{esc(p.surname)} {esc(p.name.split()[0] if p.name else '')}</b> ({esc(p.public_years)})"
        for p in people
    )


def count_generations(pid: str, people: dict[str, Person], families: dict[str, Family]) -> int:
    depth = 0
    current = pid
    while current in people and people[current].famc in families:
        depth += 1
        family = families[people[current].famc]
        parent = family.husb or family.wife
        if not parent:
            break
        current = parent
    return depth


def missing_parent_goals(
    root_ids: list[str],
    people: dict[str, Person],
    families: dict[str, Family],
    limit: int = 9,
) -> list[tuple[Person, int]]:
    """Gaps in the direct ancestor line only — closest generations first.

    One entry per person, whether the father, the mother or both are unknown.
    """
    goals: list[tuple[Person, int]] = []
    seen: set[str] = set()

    def walk(pid: str, depth: int) -> None:
        if pid in seen or pid not in people:
            return
        seen.add(pid)
        person = people[pid]
        family = families.get(person.famc) if person.famc else None

        if family is None:
            if depth > 0:
                goals.append((person, depth))
            return

        if not family.husb or not family.wife:
            goals.append((person, depth))

        for parent in (family.husb, family.wife):
            if parent:
                walk(parent, depth + 1)

    for root_id in root_ids:
        walk(root_id, 0)

    goals.sort(key=lambda item: (item[1], item[0].surname))
    return goals[:limit]


def generation_names(content: dict[str, Any]) -> dict[int, str]:
    raw = content["tree"]["generation_names"]
    return {int(key): value for key, value in raw.items()}


def status_labels(content: dict[str, Any]) -> dict[str, str]:
    return content["tree"]["status"]


def column_titles(content: dict[str, Any]) -> list[str]:
    return content["tree"]["column_titles"]


class TreeNode:
    """One slot in the ancestor chart; person is None when the ancestor is unknown."""

    def __init__(self, person: Person | None, gen: int, placeholder: str = ""):
        self.person = person
        self.gen = gen
        self.placeholder = placeholder
        self.children: list[TreeNode] = []
        self.y: float = 0.0

    @property
    def is_missing(self) -> bool:
        return self.person is None


def build_ancestor_tree(
    pid: str | None,
    people: dict[str, Person],
    families: dict[str, Family],
    content: dict[str, Any],
    max_gen: int,
    gen: int = 0,
    placeholder: str = "",
) -> TreeNode:
    person = people.get(pid) if pid else None
    node = TreeNode(person, gen, placeholder)

    if gen >= max_gen or person is None:
        return node

    family = families.get(person.famc) if person.famc else None
    if family is None:
        return node

    # Only draw an unknown-parent slot when at least one parent is known,
    # otherwise the chart fills up with empty pairs.
    if not family.husb and not family.wife:
        return node

    node.children.append(
        build_ancestor_tree(
            family.husb, people, families, content, max_gen, gen + 1, content["tree"]["missing_father"]
        )
    )
    node.children.append(
        build_ancestor_tree(
            family.wife, people, families, content, max_gen, gen + 1, content["tree"]["missing_mother"]
        )
    )
    return node


def assign_positions(node: TreeNode, cursor: list[float]) -> float:
    """Leaves stack top-down; parents centre on their children."""
    if not node.children:
        node.y = cursor[0]
        cursor[0] += ROW_H
        return node.y

    child_ys = [assign_positions(child, cursor) for child in node.children]
    node.y = (child_ys[0] + child_ys[-1]) / 2
    return node.y


def collect_nodes(node: TreeNode, acc: list[TreeNode]) -> None:
    acc.append(node)
    for child in node.children:
        collect_nodes(child, acc)


def render_connectors(node: TreeNode, max_gen: int) -> list[str]:
    """Draw the bracket between a person and their two parents."""
    if not node.children:
        return []

    out: list[str] = []
    x_right = LEFT_PAD + node.gen * COL_W + BOX_W
    x_mid = x_right + (COL_W - BOX_W) / 2
    x_parent = LEFT_PAD + (node.gen + 1) * COL_W
    tops = [child.y for child in node.children]

    out.append(f'<path class="ln" d="M{x_right} {node.y:.1f} H{x_mid:.1f}"/>')
    out.append(f'<path class="ln" d="M{x_mid:.1f} {min(tops):.1f} V{max(tops):.1f}"/>')
    for child in node.children:
        out.append(f'<path class="ln" d="M{x_mid:.1f} {child.y:.1f} H{x_parent}"/>')
        out.extend(render_connectors(child, max_gen))
    return out


def render_badge(x: float, cy: float, status: str, labels: dict[str, str]) -> str:
    """Status pill in the lower-left corner of a tree card.

    «ok» (есть запись в базе) не отрисовывается: запись в базе — дефолтное
    состояние, а не статус, и слово «Подтверждено» ложно намекало на
    документальное подтверждение."""
    if status == "ok":
        return ""
    width = STATUS_BADGE_W[status]
    if status == "hyp":
        bg_fill, text_fill = "rgba(111,102,144,.10)", "#6F6690"
    else:
        bg_fill, text_fill = "rgba(34,37,43,.05)", "#454A55"
    return (
        f'<rect class="bg" fill="{bg_fill}" x="{x + 12}" y="{cy + 18:.1f}" width="{width}" '
        f'height="{BADGE_H}" rx="{BADGE_H / 2}"/>'
        f'<text class="bdg" fill="{text_fill}" x="{x + 12 + width / 2:.1f}" y="{cy + 29.4:.1f}" '
        f'text-anchor="middle">{esc(labels[status])}</text>'
    )


def surname_search_forms(surname: str, sex: str) -> set[str]:
    """Use recorded spellings and their regular masculine/feminine counterparts."""
    forms = {surname}
    for match in re.finditer(r"\(([^)]*)\)", surname):
        for alternative in match.group(1).split(","):
            alternative = alternative.strip().rstrip("?")
            if alternative:
                forms.add(alternative)
    without_alternatives = re.sub(r"\([^)]*\)", "", surname).strip()
    if without_alternatives:
        forms.add(without_alternatives)

    for form in list(forms):
        for part in re.split(r"\s*[/—-]\s*", form):
            part = part.strip().rstrip("?")
            if part:
                forms.add(part)

    for form in list(forms):
        if re.search(r"[/—-]|\([^)]*\)", form):
            continue
        if sex != "M":
            if form.endswith("ая"):
                forms.add(form[:-2] + "ий")
            elif form.endswith(("ова", "ева", "ина")):
                forms.add(form[:-1])
        if sex != "F":
            if form.endswith("ий"):
                forms.add(form[:-2] + "ая")
            elif form.endswith(("ов", "ев", "ин")):
                forms.add(form + "а")
    return {form for form in forms if form}


def person_search_text(person: Person) -> str:
    """Public name forms only; notes, places and non-public dates stay out."""
    forms = {person.name, person.label, person.display_name}
    forms.update(surname_search_forms(person.surname, person.sex))
    for match in re.finditer(r"\(([^)]*)\)", person.name):
        alternative = match.group(1).strip().rstrip("?")
        if alternative and len(alternative) > 2:
            forms.add(alternative)
        if len(alternative) <= 2:
            forms.add(re.sub(r"\([^)]*\)", alternative, person.name))
    without_alternatives = re.sub(r"\([^)]*\)", "", person.name).strip()
    if without_alternatives:
        forms.add(without_alternatives)
    return " | ".join(sorted(form for form in forms if form))


def _box_paint(classes: list[str]) -> tuple[str, str]:
    """sRGB face and border. Kept equal to the pedigree CSS literals.

    Custom properties are not used here: when the SVG viewport is resized,
    a variable on the rectangle and a variable on the text can resolve apart,
    so a light face ends up under light text.
    """
    fill = "#E6E9EE" if "me" in classes else "#F8F9FB"
    if "hyp" in classes:
        stroke = "#6F6690"
    elif "me" in classes:
        stroke = "#454A55"
    elif "ok" in classes:
        stroke = "#6A7686"
    else:
        stroke = "#B4BBC6"
    return fill, stroke


def render_person_box(
    x: float,
    cy: float,
    person: Person,
    extra: list[str],
    labels: dict[str, str],
    card_id: str,
) -> str:
    status = "hyp" if person.is_hypothesis else "ok"
    classes = ["bx", status, *extra]
    if not person.birt and not person.deat:
        classes.append("unknown")
    if any(
        (value or "").split(" ", 1)[0] in {"ок.", "до", "после", "между"}
        for value in (person.birt, person.deat)
    ):
        classes.append("approx")
    surname = person.surname or person.name
    given = person.name if person.surname else ""
    years = person.public_years.replace("р. ", "").replace("ум. ", "† ")
    if years == "? – ?":
        years = "даты неизвестны"
    fill, stroke = _box_paint(classes)

    return (
        f'<a id="{esc(card_id)}" class="{" ".join(classes)}" href="#person-{esc(person.id)}" '
        f'data-person-id="{esc(person.id)}" data-search="{esc(person_search_text(person))}" '
        f'data-years="{esc(person.public_years)}">'
        f'<rect class="fr" fill="{fill}" stroke="{stroke}" x="{x}" y="{cy - BOX_H / 2:.1f}" '
        f'width="{BOX_W}" height="{BOX_H}" rx="10"/>'
        f'<text class="t1" fill="#22252B" x="{x + 12}" y="{cy - 22:.1f}">{esc(surname)}</text>'
        f'<text class="t2" fill="#22252B" x="{x + 12}" y="{cy - 5:.1f}">{esc(given)}</text>'
        f'<text class="t3" fill="#454A55" x="{x + 12}" y="{cy + 13:.1f}">{esc(years)}</text>'
        f'{render_badge(x, cy, status, labels)}</a>'
    )


def render_box(node: TreeNode, labels: dict[str, str], id_prefix: str) -> str:
    x = LEFT_PAD + node.gen * COL_W

    if node.is_missing:
        return (
            f'<g class="bx q">'
            f'<rect class="fr" fill="none" stroke="#B4BBC6" x="{x}" y="{node.y - BOX_H / 2:.1f}" '
            f'width="{BOX_W}" height="{BOX_H}" rx="10"/>'
            f'<text class="t1" fill="#565B66" x="{x + 12}" y="{node.y - 22:.1f}">—</text>'
            f'<text class="t2" fill="#565B66" x="{x + 12}" y="{node.y - 5:.1f}">{esc(node.placeholder)}</text>'
            f'{render_badge(x, node.y, "q", labels)}</g>'
        )

    person = node.person
    assert person is not None
    extra: list[str] = []
    if node.gen == 0:
        extra.append("me")
    elif not node.children:
        extra.append("deep")

    return render_person_box(
        x, node.y, person, extra, labels, f"{id_prefix}-{person.id}"
    )


def render_pedigree_svg(
    root: Person,
    spouse: Person,
    child: Person | None,
    people: dict[str, Person],
    families: dict[str, Family],
    content: dict[str, Any],
    max_gen: int = 4,
    include_spouse_ancestors: bool = True,
    id_prefix: str = "pedigree",
    description: str = "",
) -> str:
    """A selected ancestor chart with the spouse and shared child as anchors."""
    labels = status_labels(content)
    titles = column_titles(content)
    father_tree = build_ancestor_tree(root.id, people, families, content, max_gen)
    mother_tree = build_ancestor_tree(
        spouse.id,
        people,
        families,
        content,
        max_gen if include_spouse_ancestors else 0,
    )

    cursor = [TOP_PAD + BOX_H / 2]
    assign_positions(father_tree, cursor)
    cursor[0] += ROW_H * 1.5
    assign_positions(mother_tree, cursor)

    nodes: list[TreeNode] = []
    collect_nodes(father_tree, nodes)
    collect_nodes(mother_tree, nodes)

    parts: list[str] = []
    for index, title in enumerate(titles[: max_gen + 1]):
        parts.append(f'<text x="{LEFT_PAD + index * COL_W}" y="26" class="colhead">{esc(title)}</text>')

    parts.extend(render_connectors(father_tree, max_gen))
    parts.extend(render_connectors(mother_tree, max_gen))

    # Marriage bracket joining the two root people.
    x_mid = LEFT_PAD - 6
    parts.append(
        f'<path class="ln" d="M{x_mid} {father_tree.y:.1f} V{mother_tree.y:.1f}"/>'
        f'<path class="ln" d="M{x_mid} {father_tree.y:.1f} H{LEFT_PAD}"/>'
        f'<path class="ln" d="M{x_mid} {mother_tree.y:.1f} H{LEFT_PAD}"/>'
    )
    if child:
        y_child = (father_tree.y + mother_tree.y) / 2
        parts.append(f'<path class="ln" d="M{x_mid} {y_child:.1f} H{LEFT_PAD}"/>')
        parts.append(
            render_person_box(
                LEFT_PAD, y_child, child, ["me"], labels, f"{id_prefix}-{child.id}"
            )
        )

    for node in nodes:
        parts.append(render_box(node, labels, id_prefix))

    width = LEFT_PAD * 2 + (max_gen + 1) * COL_W
    height = max(node.y for node in nodes) + ROW_H

    return (
        f'<svg class="pedigree" style="color-scheme:light;forced-color-adjust:none" '
        f'viewBox="0 0 {width} {height:.0f}" '
        f'width="{width}" height="{height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-labelledby="{id_prefix}-title {id_prefix}-desc">'
        f'<title id="{id_prefix}-title">{esc(content["tree"]["h1"])}</title>'
        f'<desc id="{id_prefix}-desc">{esc(description or content["tree"]["h1"])}</desc>'
        + "".join(parts)
        + "</svg>"
    )


def branch_card(
    branch: dict[str, Any],
    tree_href: str = "",
    link_label: str = "",
) -> str:
    body = paragraphs_html(branch["paragraphs"])
    link = ""
    if tree_href:
        link = f'<a class="branch-link" href="{esc(tree_href)}">{esc(link_label)}</a>'
    return (
        f'<article class="card"><div class="tag">{esc(branch["tag"])}</div>'
        f'<h3>{esc(branch["title"])}</h3>'
        f'<div class="basis">{esc(branch["basis"])}</div>{body}{link}</article>'
    )


@dataclass(frozen=True)
class FamilyContext:
    """Root person, spouse and first child used across page sections."""

    root: Person
    spouse: Person
    child: Person | None


def resolve_family_context(
    people: dict[str, Person],
    families: dict[str, Family],
    root_id: str,
) -> FamilyContext:
    """Resolve the focal family from the root person id (family.yaml: root)."""
    root = people[root_id]
    spouse_fam = families[root.fams[0]]
    spouse_id = spouse_fam.wife if spouse_fam.husb == root_id else spouse_fam.husb
    spouse = people[spouse_id]
    children = [people[c] for c in spouse_fam.chil if c in people]
    child = children[0] if children else None
    return FamilyContext(root=root, spouse=spouse, child=child)


def published_places(database: dict[str, Any]) -> Counter[str]:
    """Place counts of the lost export, published verbatim on the site."""
    return Counter({entry["name"]: entry["count"] for entry in database.get("places", [])})


def build_places_html(places_content: dict[str, Any], place_counts: Counter[str]) -> str:
    """Render geography cards from aggregated place counts."""
    place_notes = places_content["notes"]
    place_default = places_content["default_note"]
    return "".join(
        f'<div class="card"><div class="tag">{esc(places_content["card_tag_prefix"])} '
        f'{counted(count, ("запись", "записи", "записей"))}</div><h4>{esc(place)}</h4>'
        f'<p>{esc(place_notes.get(place, place_default))}</p></div>'
        for place, count in place_counts.most_common(9)
    )


def build_surnames_html(surnames_content: dict[str, Any], top_surnames: list[tuple[str, int]]) -> str:
    """Render surname frequency cards."""
    surname_notes = surnames_content["notes"]
    surname_default = surnames_content["default_note"]
    return "".join(
        f'<div class="card"><h4>{esc(name)}</h4>'
        f'<p>{esc(surname_notes.get(name, surname_default))}</p>'
        f'<div class="mini">{counted(count, ("носитель", "носителя", "носителей"))} {esc(surnames_content["count_suffix"])}</div></div>'
        for name, count in top_surnames[:10]
    )


def build_timeline_html(
    timeline_content: dict[str, Any],
    timeline_people: list[Person],
    root_id: str,
) -> str:
    """Render generation timeline items."""
    timeline_html = ""
    for i, person in enumerate(timeline_people):
        me = " me" if person.id == root_id else ""
        timeline_html += f"""
      <div class="tl-item{me}">
        <div class="tl-gen">{esc(timeline_content["generation_prefix"])} {len(timeline_people) - i} {esc(timeline_content["generation_suffix"])}</div>
        <h3>{esc(person.label)}</h3>
        <div class="yrs">{esc(person.public_years)}</div>
        <p>{esc(person.public_place or timeline_content["place_fallback"])}</p>
      </div>"""
    return timeline_html


def build_goals_html(
    tree: dict[str, Any],
    goals: list[tuple[Person, int]],
    gen_names: dict[int, str],
) -> str:
    """Render search-goal rows for missing ancestors."""
    goals_text = tree["goals"]
    goals_html = ""
    for i, (person, depth) in enumerate(goals, 1):
        generation = gen_names.get(depth, f"{depth}{tree['generation_fallback_suffix']}")
        place = person.public_place
        if place:
            hint = (
                f'{goals_text["hint_known_place_prefix"]} {place}: '
                f'{goals_text["hint_known_place_suffix"]}'
            )
        else:
            hint = goals_text["hint_unknown_place"]
        goals_html += f"""
        <div class="goalrow"><div class="n">{i}</div><div>
          <b>{esc(goals_text["title_prefix"])} {esc(person.display_name)}</b>
          <p>{esc(person.public_years)} · {esc(generation)} {esc(goals_text["line_suffix"])} {esc(hint)}</p>
          <div class="st">{esc(generation.capitalize())} {esc(goals_text["status_suffix"])}</div>
        </div></div>"""
    return goals_html


def hero_graph_years(line: list[Person]) -> list[tuple[str, bool]]:
    """Birth years of the paternal line for the hero lattice: (year, is_approximate).

    Only year precision is used, so the entry for a living root person stays
    within the privacy policy (same as public_years).
    """
    years: list[tuple[str, bool]] = []
    for person in line:
        year = year_only(person.birt)
        if not year:
            continue
        years.append((year, person.has_derived_date))
        if len(years) == len(HERO_YEAR_ANCHORS):
            break
    return years


def hero_graph_caption(hero: dict[str, Any], years: list[tuple[str, bool]]) -> str:
    """Factual caption under the lattice: 'Отцовская линия…, ок. 1768 — 1971'."""
    prefix = hero["graph_caption_prefix"]
    if not years:
        return prefix
    newest = years[0][0]
    oldest_year, oldest_approx = years[-1]
    oldest = f"ок. {oldest_year}" if oldest_approx else oldest_year
    return f"{prefix} {oldest} — {newest}"


Limb = tuple[list[tuple[float, float]], int]


def _reflect_inside(
    x: float, y: float, angle: float, margin: float = -70.0
) -> tuple[float, float, float]:
    """Bounce a growth direction off a boundary well outside the viewBox: the
    network bleeds past the frame (the page crops it), twigs just may not run
    arbitrarily far into the void."""
    if x < margin:
        x, angle = margin, math.pi - angle
    elif x > HERO_VIEW_W - margin:
        x, angle = HERO_VIEW_W - margin, math.pi - angle
    if y < margin:
        y, angle = margin, -angle
    elif y > HERO_VIEW_H - margin:
        y, angle = HERO_VIEW_H - margin, -angle
    return x, y, angle


def _grow_branch(
    rng: random.Random,
    x: float,
    y: float,
    angle: float,
    length: float,
    depth: int,
    out: list[Limb],
) -> None:
    """Grow one kinked branch off the skeleton and fork it recursively.
    Depth 1 sits directly on a primary ridge, deeper levels are twigs."""
    steps = 3 if depth == 1 else 2
    pts = [(round(x, 1), round(y, 1))]
    for _ in range(steps):
        angle += rng.uniform(-0.3, 0.3)
        step = length / steps
        x, y, angle = _reflect_inside(
            x + math.cos(angle) * step, y + math.sin(angle) * step, angle
        )
        pts.append((round(x, 1), round(y, 1)))
    out.append((pts, depth))
    if depth >= 2:
        return
    for _ in range(2 if rng.random() < 0.4 else 1):
        if rng.random() < 0.24:
            continue
        side = 1 if rng.random() < 0.5 else -1
        _grow_branch(
            rng,
            x,
            y,
            angle + side * rng.uniform(0.4, 1.05),
            length * rng.uniform(0.52, 0.74),
            depth + 1,
            out,
        )


def _hero_limbs(rng: random.Random) -> list[Limb]:
    """Full skeleton of the crystal: the hand-authored primary ridges (depth 0)
    plus the branches and twigs grown off them (depth 1–3)."""
    limbs: list[Limb] = [(list(ridge), 0) for ridge in HERO_RIDGES]
    for ridge in HERO_RIDGES:
        for (x1, y1), (x2, y2) in zip(ridge, ridge[1:]):
            base = math.atan2(y2 - y1, x2 - x1)
            for _ in range(2):
                if rng.random() > 0.58:
                    continue
                t = rng.uniform(0.12, 0.9)
                side = 1 if rng.random() < 0.5 else -1
                _grow_branch(
                    rng,
                    x1 + (x2 - x1) * t,
                    y1 + (y2 - y1) * t,
                    base + side * rng.uniform(0.45, 1.25),
                    rng.uniform(34, 82),
                    1,
                    limbs,
                )
    return limbs


class _SkeletonField:
    """Grid of samples along the skeleton, for fast approximate distance from
    any point to the nearest ridge or twig. Drives every density decision:
    which facets survive, how bright an edge is, where the veil thins out."""

    CELL = 22.0

    def __init__(self, limbs: list[Limb]) -> None:
        self.grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for pts, _ in limbs:
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / 6))
                for i in range(steps + 1):
                    t = i / steps
                    sx, sy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                    key = (int(sx // self.CELL), int(sy // self.CELL))
                    self.grid.setdefault(key, []).append((sx, sy))

    def dist(self, x: float, y: float, rings: int = 4) -> float:
        cx, cy = int(x // self.CELL), int(y // self.CELL)
        best = math.inf
        for ring in range(rings + 1):
            for gx in range(cx - ring, cx + ring + 1):
                for gy in range(cy - ring, cy + ring + 1):
                    if ring and max(abs(gx - cx), abs(gy - cy)) != ring:
                        continue
                    for px, py in self.grid.get((gx, gy), ()):
                        best = min(best, (px - x) ** 2 + (py - y) ** 2)
            if best <= (ring * self.CELL) ** 2:
                break
        return math.sqrt(best) if best < math.inf else math.inf


def _hero_facet_points(
    rng: random.Random, limbs: list[Limb], field: _SkeletonField
) -> list[tuple[float, float]]:
    """Facet vertices sown along the skeleton — never over the whole frame — so
    the triangulated body follows the branching silhouette instead of filling a
    hull. Reach falls with branch depth: wide panes hug the trunk, fine chips
    cling to the twigs."""
    cell = 18.0
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    pts: list[tuple[float, float]] = []

    def place(x: float, y: float, min_d: float) -> None:
        if not (14 <= x <= HERO_VIEW_W - 14 and 18 <= y <= HERO_VIEW_H - 14):
            return
        gx, gy = int(x // cell), int(y // cell)
        for ax in range(gx - 1, gx + 2):
            for ay in range(gy - 1, gy + 2):
                for px, py in grid.get((ax, ay), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < min_d**2:
                        return
        grid.setdefault((gx, gy), []).append((x, y))
        pts.append((round(x, 1), round(y, 1)))

    reach_by_depth = (25.0, 17.0, 11.0, 9.0)
    for poly, depth in limbs:
        for px, py in poly:
            place(px, py, 10.0)
        # Per-limb jitter keeps facet size uneven: chunky panes along one limb,
        # fine chips along the next.
        reach = reach_by_depth[min(depth, 3)] * rng.uniform(0.72, 1.3)
        min_d = rng.uniform(12.0, 18.0)
        for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
            seg = math.hypot(x2 - x1, y2 - y1) or 1.0
            nx, ny = -(y2 - y1) / seg, (x2 - x1) / seg
            stations = max(1, int(seg / 13))
            for i in range(stations):
                t = (i + rng.uniform(0.2, 0.8)) / stations
                bx, by = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                for _ in range(2):
                    off = rng.uniform(6, reach) * (1 if rng.random() < 0.5 else -1)
                    place(bx + nx * off + rng.uniform(-3, 3), by + ny * off + rng.uniform(-3, 3), min_d)

    # Second, finer sowing inside the braided zones only: there the weave gets
    # small tight cells, while the quiet zones keep the coarse spacing above.
    for cx, cy, radius in HERO_DENSE:
        for _ in range(260):
            angle = rng.uniform(0, 2 * math.pi)
            r = radius * 0.95 * math.sqrt(rng.random())
            x, y = cx + math.cos(angle) * r, cy + math.sin(angle) * r
            if field.dist(x, y, rings=2) > 21:
                continue
            if rng.random() > _hero_density(x, y) ** 1.5:
                continue
            place(x, y, rng.uniform(9.0, 12.5))
    return pts


def _hero_density(x: float, y: float) -> float:
    """Weave density, 0…1. Peaks in the braided zones and collapses in the void
    pockets, so no two areas of the crystal carry the same amount of mesh."""
    value = 0.3
    for cx, cy, radius in HERO_DENSE:
        value += 0.85 * math.exp(-math.hypot(x - cx, y - cy) / radius)
    for cx, cy, radius in HERO_VOIDS:
        value -= 0.82 * math.exp(-math.hypot(x - cx, y - cy) / radius)
    return max(0.0, min(1.0, value))


def _hero_glow(x: float, y: float) -> float:
    """Luminance, 0…1. Light pools at the major junctions and falls off with
    distance, which keeps the outer branches thin and dim."""
    value = 0.0
    for cx, cy, _, scale in HERO_CORES:
        value += scale * math.exp(-math.hypot(x - cx, y - cy) / 150)
    return max(0.0, min(1.0, value))


def _closed_spline(pts: list[tuple[float, float]]) -> str:
    """Catmull–Rom loop through the points, emitted as closed cubic Béziers —
    the veils and fog pockets need soft organic outlines, not polygons."""
    count = len(pts)
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(count):
        p0, p1 = pts[(i - 1) % count], pts[i]
        p2, p3 = pts[(i + 1) % count], pts[(i + 2) % count]
        c1x, c1y = p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6
        c2x, c2y = p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6
        d += (
            f" C{c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2[0]:.1f} {p2[1]:.1f}"
        )
    return d + "Z"


def _blob(
    rng: random.Random,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    rot: float,
    lobes: int = 8,
    wobble: float = 0.38,
) -> str:
    """One irregular cloud: a rotated ellipse whose radius wanders per lobe."""
    rad = math.radians(rot)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    pts: list[tuple[float, float]] = []
    for i in range(lobes):
        angle = 2 * math.pi * (i + rng.uniform(-0.16, 0.16)) / lobes
        px = math.cos(angle) * rx * (1 + rng.uniform(-wobble, wobble))
        py = math.sin(angle) * ry * (1 + rng.uniform(-wobble, wobble))
        pts.append((cx + px * cos_r - py * sin_r, cy + px * sin_r + py * cos_r))
    return _closed_spline(pts)


def _hero_veil(
    rng: random.Random, field: _SkeletonField
) -> tuple[list[tuple[float, float, int]], list[tuple[float, float, float, float, bool]]]:
    """Far field: a dotted micro-lattice and long hairline edges that fade out
    of the black. Density decays exponentially with distance from the skeleton
    and follows the braided/void zones, so the crystal keeps an atmosphere
    instead of a hard edge — and tier 3 is the barely-there background dust."""
    dots: list[tuple[float, float, int]] = []
    for _ in range(7200):
        if len(dots) >= 620:
            break
        x = rng.uniform(16, HERO_VIEW_W - 14)
        y = rng.uniform(14, HERO_VIEW_H - 12)
        dist = field.dist(x, y, rings=9)
        if dist > 260:
            continue
        chance = math.exp(-dist / 88) * (0.35 + 0.65 * _hero_density(x, y))
        if rng.random() > chance:
            continue
        tier = 1 if dist < 58 else 2 if dist < 130 else 3
        dots.append((round(x, 1), round(y, 1), tier))

    near_dots = [dot for dot in dots if dot[2] < 3] or dots
    lines: list[tuple[float, float, float, float, bool]] = []
    attempts = 0
    while len(lines) < 104 and attempts < 3200:
        attempts += 1
        (x1, y1, _), (x2, y2, _) = rng.choice(near_dots), rng.choice(near_dots)
        span = math.hypot(x2 - x1, y2 - y1)
        if not 58 <= span <= 210:
            continue
        mid_dens = _hero_density((x1 + x2) / 2, (y1 + y2) / 2)
        if rng.random() > 0.25 + 0.75 * mid_dens:
            continue
        lines.append((x1, y1, x2, y2, rng.random() < 0.45))
    return dots, lines


def _delaunay(points: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Deterministic Bowyer–Watson Delaunay triangulation (pure Python,
    O(n²) insertion — fine for the ~150 hero vertices). Returns sorted
    vertex-index triples with super-triangle faces removed."""
    n = len(points)
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    span = max(max_x - min_x, max_y - min_y) or 1.0
    mid_x, mid_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    verts = list(points) + [
        (mid_x - 20 * span, mid_y - 10 * span),
        (mid_x + 20 * span, mid_y - 10 * span),
        (mid_x, mid_y + 20 * span),
    ]

    def circumcircle(tri: tuple[int, int, int]) -> tuple[float, float, float]:
        (ax, ay), (bx, by), (cx, cy) = (verts[v] for v in tri)
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-9:  # collinear: infinite circle, always invalidated
            return (0.0, 0.0, float("inf"))
        a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
        ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
        uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
        return (ux, uy, (ax - ux) ** 2 + (ay - uy) ** 2)

    first = (n, n + 1, n + 2)
    tris: dict[tuple[int, int, int], tuple[float, float, float]] = {first: circumcircle(first)}
    for i in range(n):
        px, py = verts[i]
        bad = [t for t, (ux, uy, r2) in tris.items() if (px - ux) ** 2 + (py - uy) ** 2 <= r2]
        boundary: Counter = Counter()
        for a, b, c in bad:
            for edge in ((a, b), (b, c), (a, c)):
                boundary[edge] += 1
            del tris[(a, b, c)]
        for (a, b), count in boundary.items():
            if count == 1:
                tri = tuple(sorted((a, b, i)))
                tris[tri] = circumcircle(tri)
    return sorted(t for t in tris if all(v < n for v in t))


def _hero_defs(air_blob: str) -> str:
    """Paints and filters for every depth plane: the nebula halo, the smoke
    turbulence that gives the veils and fog pockets irregular soft edges, the
    anisotropic streak blur for the flares, and the masks that dissolve the
    structure into the black."""
    return (
        "<defs>"
        # Volume behind the whole crystal: one wide, very dark lilac halo.
        '<radialGradient id="lat-halo">'
        '<stop offset="0" stop-color="#6F5FA8" stop-opacity=".3"/>'
        '<stop offset=".4" stop-color="#4B3F78" stop-opacity=".15"/>'
        '<stop offset=".72" stop-color="#2C2545" stop-opacity=".06"/>'
        '<stop offset="1" stop-color="#14111E" stop-opacity="0"/>'
        "</radialGradient>"
        '<radialGradient id="lat-bloom">'
        '<stop offset="0" stop-color="#9A8CD8" stop-opacity=".42"/>'
        '<stop offset=".45" stop-color="#7466B4" stop-opacity=".16"/>'
        '<stop offset="1" stop-color="#5B4E96" stop-opacity="0"/>'
        "</radialGradient>"
        # Translucent veils: light enters from one corner and dies out, so each
        # plane has its own direction instead of a flat wash.
        '<linearGradient id="lat-veil-a" x1="0" y1="0" x2=".82" y2="1">'
        '<stop offset="0" stop-color="#9789CE" stop-opacity=".34"/>'
        '<stop offset=".48" stop-color="#6B5F9E" stop-opacity=".15"/>'
        '<stop offset="1" stop-color="#241F38" stop-opacity="0"/>'
        "</linearGradient>"
        '<linearGradient id="lat-veil-b" x1="1" y1="0" x2="0" y2=".9">'
        '<stop offset="0" stop-color="#B6A9E6" stop-opacity=".26"/>'
        '<stop offset=".55" stop-color="#6E62A4" stop-opacity=".1"/>'
        '<stop offset="1" stop-color="#1E1A2C" stop-opacity="0"/>'
        "</linearGradient>"
        '<radialGradient id="lat-veil-c">'
        '<stop offset="0" stop-color="#C4B8F2" stop-opacity=".2"/>'
        '<stop offset=".6" stop-color="#7B6DB4" stop-opacity=".07"/>'
        '<stop offset="1" stop-color="#1B1826" stop-opacity="0"/>'
        "</radialGradient>"
        # Lit haze pockets catching the glow of the trunk.
        '<radialGradient id="lat-fog-lit">'
        '<stop offset="0" stop-color="#C9BDF4" stop-opacity=".17"/>'
        '<stop offset=".5" stop-color="#8578C0" stop-opacity=".08"/>'
        '<stop offset="1" stop-color="#3A3358" stop-opacity="0"/>'
        "</radialGradient>"
        # Streak flare: light along the axis, nothing at the ends.
        '<radialGradient id="lat-core">'
        '<stop offset="0" stop-color="#FBF8FF" stop-opacity=".5"/>'
        '<stop offset=".3" stop-color="#D9CFFF" stop-opacity=".22"/>'
        '<stop offset="1" stop-color="#9C8DDA" stop-opacity="0"/>'
        "</radialGradient>"
        '<linearGradient id="lat-streak-g" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#8A78D6" stop-opacity="0"/>'
        '<stop offset=".34" stop-color="#A491E8" stop-opacity=".3"/>'
        '<stop offset=".52" stop-color="#D6CBFF" stop-opacity=".5"/>'
        '<stop offset=".7" stop-color="#A491E8" stop-opacity=".26"/>'
        '<stop offset="1" stop-color="#8A78D6" stop-opacity="0"/>'
        "</linearGradient>"
        '<filter id="lat-soft" x="-70%" y="-70%" width="240%" height="240%">'
        '<feGaussianBlur stdDeviation="3.2"/>'
        "</filter>"
        '<filter id="lat-wide" x="-90%" y="-90%" width="280%" height="280%">'
        '<feGaussianBlur stdDeviation="13"/>'
        "</filter>"
        # Ridges on the far plane are out of focus, which is what puts them
        # behind the haze rather than merely making them dimmer.
        '<filter id="lat-defocus" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="2.1"/>'
        "</filter>"
        '<filter id="lat-blur1" x="-8%" y="-8%" width="116%" height="116%" '
        'color-interpolation-filters="sRGB">'
        '<feGaussianBlur stdDeviation="1.05"/>'
        "</filter>"
        '<filter id="lat-blur2" x="-10%" y="-10%" width="120%" height="120%" '
        'color-interpolation-filters="sRGB">'
        '<feGaussianBlur stdDeviation="1.9"/>'
        "</filter>"
        '<filter id="lat-blur3" x="-12%" y="-12%" width="124%" height="124%" '
        'color-interpolation-filters="sRGB">'
        '<feGaussianBlur stdDeviation="4.2"/>'
        "</filter>"
        # Flares stretch along one axis only: a wide blur in x, a tight one in y.
        '<filter id="lat-streak" x="-30%" y="-620%" width="160%" height="1340%" '
        'color-interpolation-filters="sRGB">'
        '<feGaussianBlur stdDeviation="15 3.4"/>'
        "</filter>"
        # Smoke: fractal turbulence displaces the blob outline, then a heavy
        # blur softens it — the veils get torn, wispy edges no polygon can give.
        '<filter id="lat-smoke" x="-42%" y="-42%" width="184%" height="184%" '
        'color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency=".004" numOctaves="3" '
        'seed="21" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="164" '
        'xChannelSelector="R" yChannelSelector="G"/>'
        '<feGaussianBlur stdDeviation="15"/>'
        "</filter>"
        '<filter id="lat-smoke-2" x="-42%" y="-42%" width="184%" height="184%" '
        'color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency=".0074" numOctaves="3" '
        'seed="7" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="104" '
        'xChannelSelector="G" yChannelSelector="B"/>'
        '<feGaussianBlur stdDeviation="10"/>'
        "</filter>"
        '<filter id="lat-fog" x="-42%" y="-42%" width="184%" height="184%" '
        'color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency=".0062" numOctaves="3" '
        'seed="43" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="86" '
        'xChannelSelector="R" yChannelSelector="B"/>'
        '<feGaussianBlur stdDeviation="12"/>'
        "</filter>"
        # Background dust: sparse turbulence speckle, thresholded down to a few
        # grains per hundred pixels and clipped to the layer rectangle.
        '<filter id="lat-dust" x="0" y="0" width="100%" height="100%" '
        'color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency=".72" numOctaves="1" '
        'seed="11" result="n"/>'
        '<feColorMatrix in="n" type="matrix" result="grain" values="'
        "0 0 0 0 .78  0 0 0 0 .79  0 0 0 0 .95  2.6 0 0 0 -1.94\"/>"
        '<feComposite in="grain" in2="SourceGraphic" operator="in"/>'
        "</filter>"
        # The mesh and the far field dissolve towards the periphery. The fade
        # is much wider than the visible crop, so inside the frame it reads as
        # edge dissolution, never as a contained oval silhouette: the bright
        # centre thins out and the main lines keep running off the screen.
        '<radialGradient id="lat-fade">'
        '<stop offset=".42" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset=".74" stop-color="#fff" stop-opacity=".62"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        "</radialGradient>"
        '<mask id="lat-mask">'
        f'<ellipse cx="{HERO_VIEW_W * 0.56:.0f}" cy="{HERO_VIEW_H * 0.5:.0f}" '
        f'rx="{HERO_VIEW_W * 0.76:.0f}" ry="{HERO_VIEW_H * 0.72:.0f}" fill="url(#lat-fade)"/>'
        "</mask>"
        # A softer, wider fade for the atmosphere, torn by the same turbulence
        # so the haze does not end on a clean ellipse.
        '<radialGradient id="lat-fade-wide">'
        '<stop offset=".3" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset=".66" stop-color="#fff" stop-opacity=".78"/>'
        '<stop offset=".88" stop-color="#fff" stop-opacity=".3"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        "</radialGradient>"
        # The atmosphere fades out along an irregular outline rather than a clean
        # ellipse. The wobble is geometry, not a filter: this mask is referenced
        # by five groups, and a turbulence here would be evaluated five times.
        '<mask id="lat-mask-air">'
        f'<path d="{air_blob}" fill="url(#lat-fade-wide)"/>'
        "</mask>"
        "</defs>"
    )


def _path_d(poly: list[tuple[float, float]]) -> str:
    return "M" + " L".join(f"{x} {y}" for x, y in poly)


def _streak(cx: float, cy: float, angle: float, length: float, width: float, cls: str) -> str:
    """One anisotropic flare: a gradient bar rotated onto the given axis and
    blurred far along it, hardly at all across it."""
    return (
        f'<g transform="rotate({angle:.1f} {cx:.1f} {cy:.1f})">'
        f'<rect class="{cls}" x="{cx - length / 2:.1f}" y="{cy - width / 2:.1f}" '
        f'width="{length:.1f}" height="{width:.1f}" rx="{width / 2:.1f}" '
        'filter="url(#lat-streak)"/>'
        "</g>"
    )


def render_hero_graph(years: list[tuple[str, bool]], caption: str) -> str:
    """Open branching network rendered as an atmospheric background layer, in
    stacked depth planes but with no body: nothing here encloses a silhouette.

    Not called any more: the hero now shows the reference artwork itself
    (assets/hero-reference.png) instead of this modelled approximation of it.
    Kept, together with its .lattice styles, as the generated-graphics variant.

    far    — halo, turbulence dust, nebula blooms, defocused ridges and the
             dimmest web, dissolving into the black under a torn mask;
    mid    — smoke veils drifting *across* the far plane, which is what makes
             some branches read as passing behind the haze;
    near   — crisp luminous ridges running off the frame, streak flares along a
             few main diagonals and pinpoint lights, brightest at the centre;
    haze    between mid and near: lit pockets catching the glow of the trunk.

    The web is lines and dots only — no filled facets, panes or fog masses that
    would read as a volume. Density follows the braided/void zones, biased to
    the centre; the periphery thins out and the main branches exit the frame."""
    rng = random.Random(HERO_SEED)
    air_blob = _blob(
        rng,
        HERO_VIEW_W * 0.52,
        HERO_VIEW_H * 0.5,
        HERO_VIEW_W * 0.82,
        HERO_VIEW_H * 0.78,
        -6,
        lobes=11,
        wobble=0.17,
    )
    limbs = _hero_limbs(rng)
    field = _SkeletonField(limbs)
    points = _hero_facet_points(rng, limbs, field)
    veil_dots, veil_lines = _hero_veil(rng, field)

    # Candidate faces of the web survive only near the skeleton, only if they
    # are compact, and only where the weave is dense. They are used solely to
    # pick which *edges* get drawn — the faces themselves are never filled.
    faces: list[tuple[tuple[int, int, int], float, float, float]] = []
    for tri in _delaunay(points):
        (x1, y1), (x2, y2), (x3, y3) = (points[v] for v in tri)
        longest = max(
            math.hypot(x1 - x2, y1 - y2),
            math.hypot(x2 - x3, y2 - y3),
            math.hypot(x1 - x3, y1 - y3),
        )
        area = abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2
        mx, my = (x1 + x2 + x3) / 3, (y1 + y2 + y3) / 3
        dist = field.dist(mx, my)
        if dist > 24 or longest > 54 or area < 28:
            continue
        # Needle-shaped faces are what makes a triangulation look like a
        # diagram, so slivers are dropped outright.
        if area / (longest * longest) < 0.14:
            continue
        density = _hero_density(mx, my)
        if rng.random() > 0.16 + 0.84 * density:
            continue
        faces.append((tri, dist, density, longest))

    air: list[str] = []
    dust: list[str] = []
    blooms: list[str] = []
    veils: list[str] = []
    far_weave: list[str] = []
    far_ridges: list[str] = []
    tissue: list[str] = []
    facets: list[str] = []
    mid_ridges: list[str] = []
    fog: list[str] = []
    filaments: list[str] = []
    streaks: list[str] = []
    ridges: list[str] = []
    wisps: list[str] = []
    sparks: list[str] = []
    flares: list[str] = []
    labels: list[str] = []

    # 1. Deepest plane: one wide halo giving the crystal a body of light, and a
    # grain of dust that is only just above the black.
    air.append(
        f'<ellipse class="halo" cx="{HERO_VIEW_W * 0.5:.0f}" cy="{HERO_VIEW_H * 0.5:.0f}" '
        f'rx="{HERO_VIEW_W * 0.52:.0f}" ry="{HERO_VIEW_H * 0.5:.0f}"/>'
    )
    air.append(
        f'<ellipse class="halo halo-2" cx="{HERO_VIEW_W * 0.46:.0f}" '
        f'cy="{HERO_VIEW_H * 0.62:.0f}" rx="{HERO_VIEW_W * 0.34:.0f}" '
        f'ry="{HERO_VIEW_H * 0.3:.0f}"/>'
    )
    dust.append(
        f'<rect class="grain" x="0" y="0" width="{HERO_VIEW_W}" height="{HERO_VIEW_H}" '
        'filter="url(#lat-dust)"/>'
    )

    # 2. Atmosphere: nebula blooms behind the densest junctions.
    for cx, cy, radius, tier in HERO_BLOOMS:
        blooms.append(f'<circle class="bloom b{tier}" cx="{cx}" cy="{cy}" r="{radius}"/>')

    # 3. Far veils: large irregular smoke planes, torn by turbulence, sitting
    # behind the branches. Each shape carries its own filter on purpose — one
    # filter over the whole group would run the turbulence across the union of
    # their boxes and costs several times more to paint.
    for cx, cy, rx, ry, rot, tier in HERO_VEILS:
        path = _blob(rng, cx, cy, rx, ry, rot, lobes=rng.choice((7, 8, 9)), wobble=0.4)
        filt = "lat-smoke" if tier == 1 else "lat-smoke-2"
        veils.append(f'<path class="vg v{tier}" d="{path}" filter="url(#{filt})"/>')

    # 4. Far field: hairline edges and a dotted micro-lattice, barely there.
    for x1, y1, x2, y2, dashed in veil_lines:
        cls = "vl vl-dash" if dashed else "vl"
        far_weave.append(f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
    for x, y, tier in veil_dots:
        radius = 0.9 if tier == 1 else 0.7 if tier == 2 else 0.55
        far_weave.append(f'<circle class="vp p{tier}" cx="{x}" cy="{y}" r="{radius}"/>')

    # 5. Web edges. Brightness follows the light pooling at the major
    # junctions, whole edges go missing where the weave thins out, and the
    # faintest ones drop to the far plane — so the triangulation never reads as
    # a continuous wireframe.
    edge_dist: dict[tuple[int, int], float] = {}
    for tri, dist, _, _ in faces:
        a, b, c = tri
        for edge in ((a, b), (b, c), (a, c)):
            edge_dist[edge] = min(edge_dist.get(edge, math.inf), dist)
    edges: dict[str, list[str]] = {"e3": [], "e2": [], "e1": []}
    far_edges: list[str] = []
    soft_edges: list[str] = []
    for (i, j), dist in edge_dist.items():
        (x1, y1), (x2, y2) = points[i], points[j]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        density, glow = _hero_density(mx, my), _hero_glow(mx, my)
        tier = "e1" if dist < 9 else "e2" if dist < 17 else "e3"
        base = 0.92 if tier == "e1" else 0.66 if tier == "e2" else 0.4
        # Two independent gates: the weave thins in the void zones, and it thins
        # again away from the lit junctions. Together they leave whole quiet
        # areas with almost nothing in them.
        if rng.random() > base * (0.2 + 0.8 * density) * (0.46 + 0.66 * glow):
            continue
        cls = f"eg {tier}"
        if rng.random() < (0.24 if tier == "e1" else 0.5):
            cls += " d1" if rng.random() < 0.55 else " d2"
        # Most edges are drawn only over part of their span: light catches a
        # stretch of an edge, it does not outline a cell. Closed triangles are
        # what made the weave read as a wireframe.
        if rng.random() < 0.62:
            t0 = rng.uniform(0, 0.36)
            t1 = min(1.0, t0 + rng.uniform(0.34, 0.78))
            x1, y1, x2, y2 = (
                round(x1 + (x2 - x1) * t0, 1),
                round(y1 + (y2 - y1) * t0, 1),
                round(x1 + (x2 - x1) * t1, 1),
                round(y1 + (y2 - y1) * t1, 1),
            )
        # Luminance falls off away from the junctions; the dimmest edges sink
        # behind the veils.
        alpha = round(0.2 + 0.95 * glow, 2)
        line = (
            f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke-opacity="{alpha}"/>'
        )
        # In the braided zones the bright edges also get a blurred copy in the
        # tissue layer, so the weave carries a glow instead of only outlines.
        if tier == "e1" and density > 0.5 and rng.random() < 0.7:
            tissue.append(
                f'<line class="eg tis-eg" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'
            )
        if tier == "e3" or (tier == "e2" and glow < 0.16):
            far_edges.append(line)
        elif rng.random() < 0.3:
            # A slice of the near weave is out of focus, so even one visual
            # plane has depth inside it.
            soft_edges.append(line)
        else:
            edges[tier].append(line)
    far_weave.extend(far_edges)
    if soft_edges:
        facets.append(
            '<g class="defocus" filter="url(#lat-blur2)">' + "".join(soft_edges) + "</g>"
        )
    for tier in ("e3", "e2", "e1"):
        facets.extend(edges[tier])

    # 6. Twigs and branches: thin filaments, many of them interrupted, thinner
    # and dimmer the further they are from the lit junctions. The faintest ones
    # belong to the far plane.
    for poly, depth in limbs:
        if depth == 0:
            continue
        mx, my = poly[len(poly) // 2]
        glow = _hero_glow(mx, my)
        cls = "br b-near" if depth == 1 else "br b-far"
        if rng.random() < (0.3 if depth == 1 else 0.5):
            cls += " d1" if rng.random() < 0.5 else " d2"
        alpha = round(0.14 + 0.9 * glow, 2)
        width = round((1.0 if depth == 1 else 0.78) * (0.55 + 0.55 * glow), 2)
        limb = (
            f'<path class="{cls}" d="{_path_d(poly)}" stroke-opacity="{alpha}" '
            f'stroke-width="{width}"/>'
        )
        if glow < 0.2 or (depth >= 2 and glow < 0.34):
            far_weave.append(limb)
        else:
            filaments.append(limb)

    # 7. Lit haze pockets in front of the midground, catching the glow of the
    # trunk. Screened onto the network — they add air, never occlusion.
    lit_pockets: list[str] = []
    for cx, cy, rx, ry, rot, kind in HERO_FOG:
        path = _blob(rng, cx, cy, rx, ry, rot, lobes=rng.choice((7, 8)), wobble=0.44)
        lit_pockets.append(
            f'<path class="fg fg-{kind}" d="{path}" filter="url(#lat-fog)"/>'
        )
    fog.append('<g class="fog-lit">' + "".join(lit_pockets) + "</g>")

    # 8. The luminous ridges, split across three planes. Far ridges are
    # defocused and sit behind the veils; the mid ones braid through the mesh;
    # the near ones stay crisp in front of the fog, with a wide bloom, a tight
    # glow and a near-white core. Brightness weight (k1…k3) is independent of
    # the plane, so only a few paths burn.
    ridge_paths = [_path_d(list(ridge)) for ridge in HERO_RIDGES]
    planes: dict[str, tuple[list[str], int]] = {
        "far": (far_ridges, 3),
        "mid": (mid_ridges, 2),
        "near": (ridges, 1),
    }
    dashed_ridges = {
        i
        for i, plane in enumerate(HERO_RIDGE_PLANES)
        if plane != "near" and rng.random() < 0.55
    }
    for i, plane in enumerate(HERO_RIDGE_PLANES):
        bucket, weight = planes[plane]
        path = ridge_paths[i]
        if plane == "far":
            bucket.append(
                f'<path class="rg rg-wide k3" d="{path}" filter="url(#lat-wide)"/>'
            )
            bucket.append(
                f'<path class="rg rg-core rg-blur k3" d="{path}" '
                'filter="url(#lat-defocus)"/>'
            )
            continue
        layers_for_plane = [
            ("rg-wide", ' filter="url(#lat-wide)"'),
            ("rg-soft", ' filter="url(#lat-soft)"'),
            ("rg-core", ""),
        ]
        if plane == "near":
            layers_for_plane.insert(0, ("rg-halo", ' filter="url(#lat-wide)"'))
        for layer, extra in layers_for_plane:
            cls = f"rg {layer} k{weight}"
            attrs = extra
            if layer == "rg-core":
                if i in dashed_ridges:
                    cls += " rg-dash"
                else:
                    attrs = ' pathLength="1"'
            bucket.append(f'<path class="{cls}" d="{path}"{attrs}/>')

    # 9. Streak flares: anisotropic glows along a few main diagonals only, so
    # the light has direction instead of an even halo everywhere.
    for x1, y1, x2, y2, width, tier in HERO_STREAKS:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        streaks.append(_streak(mx, my, angle, length * 0.82, width, f"sk s{tier}"))

    # 10. Foreground wisps: thin smoke drifting in front of the near ridges.
    for cx, cy, rx, ry, rot in HERO_WISPS:
        path = _blob(rng, cx, cy, rx, ry, rot, lobes=7, wobble=0.46)
        wisps.append(f'<path class="wp" d="{path}" filter="url(#lat-smoke-2)"/>')

    # 11. Local flare at the major junctions: a long spike along the ridge and a
    # short one across it, over a tight core.
    for cx, cy, angle, scale in HERO_CORES:
        flares.append(_streak(cx, cy, angle, 210 * scale, 4.2 * scale, "fl fl-a"))
        flares.append(_streak(cx, cy, angle + 74, 104 * scale, 3.2 * scale, "fl fl-b"))
        blooms.append(
            f'<circle class="bloom bc" cx="{cx}" cy="{cy}" r="{58 * scale:.0f}"/>'
        )
        # A tight white core under the flare: the light has a source, not just
        # an even halo.
        flares.append(
            f'<circle class="fl-core" cx="{cx}" cy="{cy}" r="{30 * scale:.0f}"/>'
        )

    # 12. Pinpoint lights: dim sparks on the twigs, brighter ones on the ridge
    # junctions, a handful of hot cores with a bloom. All of them dim away from
    # the lit junctions.
    label_pts = {(x, y) for x, y, _ in HERO_YEAR_ANCHORS} | {HERO_ANCHOR[:2]}
    twig_tips = [poly[-1] for poly, depth in limbs if depth >= 2]
    for x, y in rng.sample(twig_tips, min(52, len(twig_tips))):
        glow = _hero_glow(x, y)
        if rng.random() > 0.3 + 0.7 * _hero_density(x, y):
            continue
        target = sparks if glow > 0.24 else far_weave
        target.append(
            f'<circle class="nd dim" cx="{x}" cy="{y}" r="{0.75 + 0.5 * glow:.2f}" '
            f'opacity="{0.2 + 0.6 * glow:.2f}"/>'
        )
    # Pinpoint lights strung along the ridges themselves, between the junctions.
    for ridge in HERO_RIDGES:
        for (x1, y1), (x2, y2) in zip(ridge, ridge[1:]):
            span = math.hypot(x2 - x1, y2 - y1)
            for _ in range(max(1, int(span / 34))):
                if rng.random() < 0.32:
                    continue
                t = rng.uniform(0.18, 0.82)
                sx, sy = round(x1 + (x2 - x1) * t, 1), round(y1 + (y2 - y1) * t, 1)
                glow = _hero_glow(sx, sy)
                radius = (1.5 if rng.random() < 0.3 else 1.0) * (0.66 + 0.5 * glow)
                sparks.append(
                    f'<circle class="nd" cx="{sx}" cy="{sy}" r="{radius:.2f}" '
                    f'opacity="{0.3 + 0.7 * glow:.2f}"/>'
                )
    ridge_verts = sorted({p for ridge in HERO_RIDGES for p in ridge if p not in label_pts})
    # The hottest junctions are the lit ones, not a random handful.
    hot = set(
        sorted(ridge_verts, key=lambda p: -_hero_glow(*p))[:9]
        + rng.sample(ridge_verts, 4)
    )
    # Soft halos sit in the bloom layer under the brightest junctions.
    for x, y in sorted(hot | label_pts):
        blooms.append(f'<circle class="bloom bn" cx="{x}" cy="{y}" r="{rng.choice((28, 34, 42))}"/>')
    for x, y in ridge_verts:
        glow = _hero_glow(x, y)
        if (x, y) in hot:
            sparks.append(f'<circle class="nd hot" cx="{x}" cy="{y}" r="{2.1 + 0.9 * glow:.2f}"/>')
        else:
            sparks.append(
                f'<circle class="nd" cx="{x}" cy="{y}" r="{1.1 + 0.6 * glow:.2f}" '
                f'opacity="{0.34 + 0.66 * glow:.2f}"/>'
            )

    # 13. Year labels floating around the network like annotations, each pinned
    # to a ridge junction by a hairline tick. Approximate years keep a hollow
    # node; the 1834 revision list is a dashed documentary ring.
    def pin(x: float, y: float, side: int, text: str, node_class: str, radius: float) -> None:
        labels.append(f'<circle class="{node_class}" cx="{x}" cy="{y}" r="{radius}"/>')
        labels.append(
            f'<line class="tick" x1="{x + side * (radius + 3)}" y1="{y}" '
            f'x2="{x + side * (radius + 10)}" y2="{y}"/>'
        )
        labels.append(
            f'<text class="yr" x="{x + side * (radius + 15)}" y="{y + 4.6}" '
            f'text-anchor="{"start" if side > 0 else "end"}">{esc(text)}</text>'
        )

    for (x, y, side), year in zip(HERO_YEAR_ANCHORS, years):
        value, approximate = year
        pin(
            x,
            y,
            side,
            f"ок. {value}" if approximate else value,
            "nd key approx" if approximate else "nd key",
            3.0,
        )
    ax, ay, aside = HERO_ANCHOR
    pin(ax, ay, aside, HERO_ANCHOR_LABEL, "nd key doc", 3.0)

    # Draw order is the depth order: everything from here on overlaps what came
    # before, which is where the volume comes from. The masks make each plane
    # dissolve into the black at its own rate.
    # (group, contents, mask, filter). The far planes are blurred as whole
    # groups: aerial perspective, not just lower opacity, is what pushes them
    # behind the haze.
    layers = (
        ("air", air, None, None),
        ("dust", dust, "lat-mask-air", None),
        ("blooms", blooms, None, None),
        ("veil-far", veils, "lat-mask-air", None),
        ("weave-far", far_weave, "lat-mask", "lat-blur1"),
        ("ridges-far", far_ridges, "lat-mask-air", None),
        ("tissue", tissue, "lat-mask", "lat-blur3"),
        ("facets", facets, "lat-mask", None),
        ("ridges-mid", mid_ridges, None, None),
        ("fog", fog, None, None),
        ("filaments", filaments, "lat-mask", None),
        ("streaks", streaks, None, None),
        ("ridges", ridges, None, None),
        ("veil-near", wisps, "lat-mask-air", None),
        ("sparks", sparks, None, None),
        ("flares", flares, None, None),
        ("labels", labels, None, None),
    )
    body = ""
    for name, items, mask, filt in layers:
        attrs = f' mask="url(#{mask})"' if mask else ""
        if filt:
            attrs += f' filter="url(#{filt})"'
        body += f'<g class="{name}"{attrs}>' + "".join(items) + "</g>"
    return (
        f'<svg class="lattice" viewBox="0 0 {HERO_VIEW_W} {HERO_VIEW_H}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(caption)}">'
        + _hero_defs(air_blob)
        + body
        + "</svg>"
    )


def child_line_text(child: Person | None, meeting: dict[str, Any]) -> str:
    """Meeting-section suffix for the focal child, if present."""
    if child:
        return f" {esc(genitive_given_name(child.name, child.sex))} ({esc(child.public_years)})"
    return meeting["child_fallback"]


def family_anchor_text(family: FamilyContext) -> str:
    text = (
        f"Семья: {family.root.short} ({family.root.public_years}) и "
        f"{family.spouse.short} ({family.spouse.public_years})"
    )
    if family.child:
        text += f"; общий ребёнок {family.child.short} ({family.child.public_years})"
    return text + "."


def render_document_start(meta_content: dict[str, Any], css: str) -> str:
    """HTML document preamble through opening body tag."""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(meta_content["title"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="image" type="image/avif" imagesrcset="{HERO_SRCSET_AVIF}" imagesizes="{HERO_SIZES}" fetchpriority="high">
<link href="https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,400;7..72,500;7..72,600&family=Golos+Text:wght@400;500;600&display=swap" rel="stylesheet">
<noscript><style>.page{{display:block}}</style></noscript>
<style>{css}</style>
</head>
<body class="over-hero">
"""


def render_nav(
    meta_content: dict[str, Any],
    search: dict[str, Any],
    sections: dict[str, Any],
) -> str:
    """Section links plus archive search. The search is outside the home page."""
    items = []
    for index, item in enumerate(meta_content["nav_items"]):
        active = " active" if index == 0 else ""
        nid = f' id="nb{index + 1}"' if index == 0 else ""
        aria = ' aria-current="true"' if index == 0 else ""
        items.append(
            f'<a class="navbtn{active}"{nid}{aria} href="#{esc(item["target"])}" '
            f'data-section="{esc(item["target"])}">{esc(item["label"])}</a>'
        )
    options = [f'<option value="all">{esc(search["all"])}</option>']
    for key, section in sections.items():
        options.append(f'<option value="{esc(key)}">{esc(section["title"])}</option>')
    return f"""<nav>
  <div class="wrap">
    <div class="nav-links">{"".join(items)}</div>
    <div class="nav-search" data-person-search data-no-results="{esc(search["no_results"])}" data-in-tree="{esc(search["in_tree"])}">
      <label class="sr-only" for="archive-search">{esc(search["label"])}</label>
      <div class="search-fields">
        <input id="archive-search" type="search" placeholder="{esc(search["placeholder"])}" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="archive-results">
        <label class="sr-only" for="archive-scope">Область поиска</label>
        <select id="archive-scope" aria-label="Область поиска">
          {"".join(options)}
        </select>
      </div>
      <div class="search-results" id="archive-results" role="listbox" aria-label="{esc(search["label"])}" hidden></div>
    </div>
  </div>
</nav>

"""


def render_hero_year_labels() -> str:
    """Float plain year marks over the master artwork (layout from Image 2)."""
    parts = [
        (
            f'<span class="hero-year" style="left:{left:.1f}%;top:{top:.1f}%">'
            f"{esc(year)}</span>"
        )
        for year, left, top in HERO_YEAR_SLOTS
    ]
    for top, left, width, nodes in HERO_YEAR_LEADERS:
        node_html = ""
        if nodes in ("left", "both"):
            node_html += '<i class="hero-leader-node start"></i>'
        if nodes in ("right", "both"):
            node_html += '<i class="hero-leader-node end"></i>'
        parts.append(
            f'<span class="hero-leader" '
            f'style="top:{top:.2f}%;left:{left:.1f}%;width:{width:.1f}%">'
            f"{node_html}</span>"
        )
    if not parts:
        return ""
    return f'<div class="hero-years" aria-hidden="true">{"".join(parts)}</div>'


def render_hero_section(hero: dict[str, Any]) -> str:
    """Approved hero artwork, typography and year labels, without public statistics."""
    year_labels = render_hero_year_labels()
    return f"""<header class="hero" id="top">
  <div class="hero-art" aria-hidden="true">
    <picture>
      <source type="image/avif" srcset="{HERO_SRCSET_AVIF}" sizes="{HERO_SIZES}">
      <source type="image/webp" srcset="{HERO_SRCSET_WEBP}" sizes="{HERO_SIZES}">
      <img src="{HERO_IMAGE_JPG}" srcset="{HERO_SRCSET_JPG}" sizes="{HERO_SIZES}" alt="" width="1376" height="768" decoding="sync" fetchpriority="high">
    </picture>
    {year_labels}
  </div>
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <h1>{esc(hero["h1"])}</h1>
      <p class="sub">{rich(hero["sub"])}</p>
      <a class="cta-link" href="#{esc(hero["cta_target"])}">{esc(hero["cta"])}</a>
    </div>
  </div>
</header>

"""


def render_lines_section(
    lines: dict[str, Any],
    father_line: list[Person],
    mother_line: list[Person],
    skiba_father: list[Person],
    skiba_mother: list[Person],
) -> str:
    """Four direct-line branch cards."""
    line_cards = "".join(
        line_branch_card(lines["branches"][key], chain_text(chain))
        for key, chain in (
            ("matyukhin_father", father_line[:5]),
            ("astafyev_mother", mother_line[:4]),
            ("skiba_father", skiba_father[:5]),
            ("potashkin_mother", skiba_mother[:5]),
        )
    )
    return f"""<section id="line">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(lines["label"])}</div>
      <h2>{esc(lines["title"])}</h2>
      <p>{esc(lines["lead"])}</p>
      <div class="hr"></div>
    </div>
    <div class="grid g2" style="margin-bottom:44px">
      {line_cards}
    </div>
  </div>
</section>

"""


def render_alekseevs_section(alekseevs: dict[str, Any]) -> str:
    """Alekseev collateral branch cards."""
    return f"""<section>
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(alekseevs["label"])}</div>
      <h2>{esc(alekseevs["title"])}</h2>
      <p>{rich(alekseevs["lead"])}</p>
      <div class="hr"></div>
    </div>
    <div class="grid g2">
      {alekseev_card(alekseevs["tatar"])}
      {alekseev_card(alekseevs["donbass"])}
    </div>
  </div>
</section>

"""


def render_timeline_section(timeline: dict[str, Any], timeline_html: str) -> str:
    """Generation timeline section wrapper."""
    return f"""<section class="alt" id="timeline">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(timeline["label"])}</div>
      <h2>{esc(timeline["title"])}</h2>
      <p>{esc(timeline["lead"])}</p>
      <div class="hr"></div>
    </div>
    <div class="tl">{timeline_html}
    </div>
  </div>
</section>

"""


def render_surnames_section(surnames: dict[str, Any], surnames_html: str) -> str:
    """Surname frequency section wrapper."""
    return f"""<section id="surnames">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(surnames["label"])}</div>
      <h2>{esc(surnames["title"])}</h2>
      <p>{esc(surnames["lead"])}</p>
      <div class="hr"></div>
    </div>
    <div class="grid g2">{surnames_html}</div>
  </div>
</section>

"""


def render_places_section(places: dict[str, Any], places_html: str) -> str:
    """Geography section wrapper."""
    return f"""<section class="alt" id="places">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(places["label"])}</div>
      <h2>{esc(places["title"])}</h2>
      <p>{esc(places["lead"])}</p>
      <div class="hr"></div>
    </div>
    <div class="grid g3">{places_html}</div>
  </div>
</section>

"""


def render_meeting_section(
    meeting: dict[str, Any],
    root: Person,
    spouse: Person,
    child_suffix: str,
    export_date: str,
    st: dict[str, Any],
) -> str:
    """Marriage meeting point and living-family cards."""
    return f"""<section>
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(meeting["label"])}</div>
      <h2>{esc(meeting["title"])}</h2>
      <p>{rich(meeting["lead_prefix"])} <b>{esc(root.short)}</b> ({esc(root.public_years)}) и <b>{esc(spouse.short)}</b> ({esc(spouse.public_years)}) {esc(meeting["lead_suffix"])}{child_suffix}.</p>
      <div class="hr"></div>
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="tag">{esc(meeting["living"]["tag"])}</div>
        <h3>{esc(meeting["living"]["title"])}</h3>
        <p>{rich(meeting["living"]["body"])}</p>
      </div>
      <div class="card">
        <div class="tag">{esc(meeting["source"]["tag"])}</div>
        <h3>{esc(meeting["source"]["title"])}</h3>
        <p>{esc(meeting["source"]["intro_prefix"])} {esc(export_date)}: {counted(st['people'], ('человек', 'человека', 'человек'))}, {counted(st['families'], ('семейная запись', 'семейные записи', 'семейных записей'))}, {counted(st['with_death'], ('дата', 'даты', 'дат'))} {esc(meeting["source"]["intro_suffix"])}</p>
      </div>
    </div>
  </div>
</section>

"""


def render_sources_section(sources: dict[str, Any], st: dict[str, Any]) -> str:
    """Provenance, gaps, legend and archive guidance."""
    provenance = sources["provenance"]
    missing = sources["missing"]
    legend = sources["legend"]
    archives = sources["archives"]
    return f"""<section class="src" id="sources">
  <div class="wrap">
      <div class="sect-head">
      <div class="label">{esc(sources["label"])}</div>
      <h2>{esc(sources["title"])}</h2>
      <p>{rich(sources["lead"])}</p>
      <div class="hr"></div>
    </div>
    <div class="grid g2">
      <div class="scard">
        <h3>{esc(provenance["title"])}</h3>
        <ul>
          <li>{rich(provenance["data_item"])}</li>
          <li>{rich(provenance["copy_item"])}</li>
        </ul>
        <p style="margin:10px 0">{esc(provenance["birth_intro_prefix"])} {counted(st['people'], ('человека', 'человек', 'человек'))} {esc(provenance["birth_intro_middle"])} {st['with_birth']}. {esc(provenance["birth_intro_suffix"])}</p>
        <ul>
          <li>{rich(provenance["birth_buckets"]["full"])} — {counted(st['birth_full'], ('запись', 'записи', 'записей'))}</li>
          <li>{rich(provenance["birth_buckets"]["year_only"])} — {st['birth_year_only']}; {esc(provenance["birth_buckets"]["month_year"])} — {st['birth_month_year']}</li>
          <li>{rich(provenance["birth_buckets"]["qualified"])} — {st['birth_qualified']}: {esc(provenance["birth_buckets"]["qualified_note"])}</li>
          <li>{rich(provenance["birth_buckets"]["missing"])} — {st['birth_missing']} {plural(st['birth_missing'], ('человек', 'человека', 'человек'))}</li>
        </ul>
      </div>
      <div class="scard">
        <h3>{esc(missing["title"])}</h3>
        <p style="margin-bottom:10px">{rich(missing["intro"])}</p>
        <ul>
          <li><b>{counted(st['matched'], ('запись', 'записи', 'записей'))}</b> {esc(missing["match_suffix"])}</li>
          <li>{rich(missing["match_caveat"])}</li>
          <li>{esc(missing["no_archives"])}</li>
        </ul>
      </div>
      <div class="scard">
        <h3>{esc(legend["title"])}</h3>
        <ul>
          <li>{rich(legend["hypothesis"])}</li>
          <li>{rich(legend["calculated_dates"])}</li>
          <li>{rich(legend["dashed_card"])}</li>
        </ul>
      </div>
      <div class="scard">
        <h3>{esc(archives["title"])}</h3>
        <ul>
          <li>{rich(archives["mokroe"])}</li>
          <li>{rich(archives["valday"])}</li>
          <li>{rich(archives["chistopol"])}</li>
          <li>{rich(archives["slavyanoserbsk"])}</li>
          <li>{rich(archives["khimki"])}</li>
        </ul>
      </div>
    </div>
  </div>
</section>
"""


def _parent_ids(person: Person, families: dict[str, Family]) -> list[str]:
    if not person.famc or person.famc not in families:
        return []
    family = families[person.famc]
    return [pid for pid in (family.husb, family.wife) if pid]


def _child_ids(person: Person, families: dict[str, Family]) -> list[str]:
    children: list[str] = []
    for family_id in person.fams:
        children.extend(families[family_id].chil)
    return list(dict.fromkeys(children))


def _spouse_ids(person: Person, families: dict[str, Family]) -> list[str]:
    spouses: list[str] = []
    for family_id in person.fams:
        family = families[family_id]
        other = family.wife if family.husb == person.id else family.husb
        if other:
            spouses.append(other)
    return list(dict.fromkeys(spouses))


def ancestor_ids(
    anchor_id: str,
    people: dict[str, Person],
    families: dict[str, Family],
) -> set[str]:
    """Anchor and ancestors already stored as parent links."""
    seen: set[str] = set()
    stack = [anchor_id]
    while stack:
        pid = stack.pop()
        if pid in seen or pid not in people:
            continue
        seen.add(pid)
        stack.extend(_parent_ids(people[pid], families))
    return seen


def descendant_ids(
    roots: set[str],
    people: dict[str, Person],
    families: dict[str, Family],
) -> set[str]:
    """Roots plus descendants already stored as child links."""
    seen = {pid for pid in roots if pid in people}
    stack = list(seen)
    while stack:
        pid = stack.pop()
        for child_id in _child_ids(people[pid], families):
            if child_id in people and child_id not in seen:
                seen.add(child_id)
                stack.append(child_id)
    return seen


def section_person_ids(
    anchor_id: str,
    people: dict[str, Person],
    families: dict[str, Family],
) -> set[str]:
    """Blood of one section anchor, plus spouses of those people.

    Walking only up from the anchor and then down from those ancestors keeps
    siblings, other descendants and collateral kin. A spouse is included once;
    the spouse's own parents stay in their section instead of being inferred.
    """
    blood = descendant_ids(ancestor_ids(anchor_id, people, families), people, families)
    spouses: set[str] = set()
    for pid in blood:
        spouses.update(sid for sid in _spouse_ids(people[pid], families) if sid in people)
    return blood | spouses


def sibling_ids(
    person: Person,
    people: dict[str, Person],
    families: dict[str, Family],
) -> list[str]:
    """People who already share a parent with this person."""
    mine = set(_parent_ids(person, families))
    if not mine:
        return []
    found = []
    for other in people.values():
        if other.id == person.id:
            continue
        if mine & set(_parent_ids(other, families)):
            found.append(other.id)
    return found


def _person_sort_key(pid: str, people: dict[str, Person]) -> tuple[str, str, str]:
    person = people[pid]
    return (person.surname.casefold(), person.name.casefold(), person.id)


def recorded_alternate_surnames(person: Person) -> list[str]:
    """Parenthetical and slash-separated surnames already written in the record."""
    surname = re.sub(r"\s+", " ", person.surname or "").strip()
    if not surname:
        return []
    extras: list[str] = []
    for match in re.finditer(r"\(([^)]*)\)", surname):
        for part in match.group(1).split(","):
            part = part.strip()
            if part:
                extras.append(part)
    without = re.sub(r"\s*\([^)]*\)", "", surname).strip()
    parts = [part.strip() for part in re.split(r"\s*/\s*", without) if part.strip()]
    if len(parts) > 1:
        extras.extend(parts)
    seen: set[str] = set()
    result: list[str] = []
    for item in extras:
        if item == surname or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def public_birth(person: Person) -> str:
    """Birth text safe to publish. Living people keep a year, or nothing."""
    if person.is_living:
        return year_only(person.birt)
    return format_date(person.birt)


def public_death(person: Person) -> str:
    if person.is_living:
        return ""
    return format_date(person.deat)


def public_life_brief(person: Person) -> str:
    """Compact public dates. Missing dates produce no placeholder."""
    birth = public_birth(person)
    death = public_death(person)
    if person.is_living:
        return f"р. {birth}" if birth else "ныне живущий"
    if birth and death:
        return f"{birth} – {death}"
    if birth:
        return f"р. {birth}"
    if death:
        return f"ум. {death}"
    return ""


def public_birth_place(person: Person) -> str:
    if person.is_living:
        return ""
    return canonical_place(person.birt_plac)


def public_residence(person: Person) -> str:
    if person.is_living:
        return ""
    return canonical_place(person.residence)


def public_death_place(person: Person) -> str:
    if person.is_living:
        return ""
    return canonical_place(person.deat_plac)


PLACE_RELATION_LABELS = {
    "birth": "Место рождения",
    "last_residence": "Последний адрес",
    "marriage": "Место брака",
}


def editorial_place_facts(
    content: dict[str, Any],
    published: set[str],
) -> dict[str, list[tuple[str, str]]]:
    """Move facts from former place notes to cards without copying them into YAML data."""
    facts: dict[str, list[tuple[str, str]]] = {}
    seen: set[tuple[str, str, str]] = set()
    for section in content["sections"].values():
        for place in section["places"]["items"]:
            for association in place.get("people", []):
                person_id = association["id"]
                label = PLACE_RELATION_LABELS.get(association["relation"], "")
                key = (person_id, label, place["name"])
                if person_id not in published or not label or key in seen:
                    continue
                seen.add(key)
                facts.setdefault(person_id, []).append((label, place["name"]))
    return facts


def _render_fact(label: str, value_html: str) -> str:
    if not value_html or not value_html.strip():
        return ""
    return f"<div><dt>{esc(label)}</dt><dd>{value_html}</dd></div>"


def _render_related_people(
    ids: list[str],
    people: dict[str, Person],
    published: set[str],
) -> str:
    """Names of relatives. A published person links to the stable card."""
    if not ids:
        return ""
    items = []
    for pid in sorted(dict.fromkeys(ids), key=lambda item: _person_sort_key(item, people)):
        if pid not in people:
            continue
        person = people[pid]
        brief = public_life_brief(person)
        text = esc(person.display_name)
        if brief:
            text += f" ({esc(brief)})"
        if pid in published:
            text = f'<a href="#person-{esc(pid)}">{text}</a>'
        items.append(f"<li>{text}</li>")
    if not items:
        return ""
    return f"<ul>{''.join(items)}</ul>"


def _render_related_links(
    ids: list[str],
    people: dict[str, Person],
    published: set[str],
) -> str:
    links = []
    available = {pid for pid in ids if pid in published}
    for pid in sorted(available, key=lambda item: _person_sort_key(item, people)):
        links.append(f'<a href="#person-{esc(pid)}">{esc(people[pid].display_name)}</a>')
    return " · ".join(links)


def render_tree_actions(
    person_id: str,
    section_links: list[tuple[str, str]],
    tree_cards: dict[str, dict[str, str]],
    label: str,
) -> str:
    """Links that open a family tree already containing this person."""
    found: list[tuple[str, str, str]] = []
    for key, title in section_links:
        card = tree_cards.get(key, {}).get(person_id)
        if card:
            found.append((key, title, card))
    if not found:
        return ""
    links = []
    for key, title, card in found:
        text = label if len(found) == 1 else f"{label} · {title}"
        links.append(
            f'<a href="#{esc(key)}-tree" data-show-tree="{esc(key)}" '
            f'data-card-id="{esc(card)}">{esc(text)}</a>'
        )
    return f'<p class="person-actions">{"".join(links)}</p>'


def render_person_card(
    person: Person,
    people: dict[str, Person],
    families: dict[str, Family],
    content: dict[str, Any],
    section_links: list[tuple[str, str]],
    tree_cards: dict[str, dict[str, str]],
    published: set[str],
    place_facts: list[tuple[str, str]],
) -> str:
    """One person card addressed by the existing person id.

    Photos and memories are not rendered. ``note`` is an imported line that
    already contains an exact date and a technical mark, including for living
    people, so it is not a public biography or research comment. ``source``
    on the record is the technical mark ``import``, not a citation.
    Empty rows are omitted; no biography is composed from the links.
    """
    back = "".join(
        f'<a href="#{esc(section_key)}-people">{esc(title)}</a>'
        for section_key, title in section_links
    )
    editorial_facts = []
    if not person.is_living:
        editorial_facts.append(
            _render_fact(
                "Семейные сведения",
                esc(content.get("person_biographies", {}).get(person.id, "")),
            )
        )
    for label, place in place_facts:
        # Places of living people stay out of the card, including marriage.
        if person.is_living:
            continue
        editorial_facts.append(_render_fact(label, esc(place)))
    facts = "".join((
        _render_fact("Другие записанные фамилии", esc(", ".join(recorded_alternate_surnames(person)))),
        _render_fact("Статус", esc(content["tree"]["status"]["hyp"]) if person.is_hypothesis else ""),
        _render_fact("Рождение", esc(public_birth(person))),
        _render_fact("Смерть", esc(public_death(person))),
        _render_fact("Место рождения", esc(public_birth_place(person))),
        _render_fact("Место проживания", esc(public_residence(person))),
        _render_fact("Место смерти", esc(public_death_place(person))),
        *editorial_facts,
        _render_fact("Родители", _render_related_people(_parent_ids(person, families), people, published)),
        _render_fact("Супруги", _render_related_people(_spouse_ids(person, families), people, published)),
        _render_fact("Дети", _render_related_people(_child_ids(person, families), people, published)),
        _render_fact(
            "Братья и сёстры",
            _render_related_people(sibling_ids(person, people, families), people, published),
        ),
        _render_fact("Профессия и образование", esc(person.occu)),
    ))
    facts_html = f'<dl class="person-facts">{facts}</dl>' if facts else ""
    actions = render_tree_actions(
        person.id,
        section_links,
        tree_cards,
        content["archive_search"]["show_in_tree"],
    )
    return (
        f'<article class="person-card" id="person-{esc(person.id)}" '
        f'data-person-id="{esc(person.id)}">'
        f'<div class="wrap"><p class="person-back">{back}</p>'
        f"<h1>{esc(person.display_name)}</h1>{facts_html}{actions}</div></article>\n"
    )


def render_person_cards_page(
    people: dict[str, Person],
    families: dict[str, Family],
    content: dict[str, Any],
    membership: dict[str, list[tuple[str, str]]],
    tree_cards: dict[str, dict[str, str]],
) -> str:
    """One adaptive sheet per published person, addressed by person id."""
    published = set(membership)
    place_facts = editorial_place_facts(content, published)
    cards = []
    for pid in sorted(membership, key=lambda item: _person_sort_key(item, people)):
        cards.append(
            render_person_card(
                people[pid],
                people,
                families,
                content,
                membership[pid],
                tree_cards,
                published,
                place_facts.get(pid, []),
            )
        )
    return f'<div class="page" id="page-persons">\n{"".join(cards)}</div>\n\n'


def svg_person_cards(svg: str) -> dict[str, str]:
    """Map a person id to the tree-card id actually drawn in one SVG."""
    return {
        person_id: card_id
        for card_id, person_id in re.findall(
            r'id="([^"]+)" class="bx[^"]*" href="#person-[^"]+" data-person-id="([^"]+)"',
            svg,
        )
    }


def public_search_records(
    people: dict[str, Person],
    membership: dict[str, list[tuple[str, str]]],
    tree_cards: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Rows for the public search index.

    Names, public life dates and section labels only. Notes, places and
    non-public dates are not copied into the index.
    """
    records = []
    for pid in sorted(membership, key=lambda item: _person_sort_key(item, people)):
        person = people[pid]
        sections = [{"key": key, "title": title} for key, title in membership[pid]]
        trees = []
        for key, title in membership[pid]:
            card = tree_cards.get(key, {}).get(pid)
            if card:
                trees.append({"key": key, "title": title, "card": card})
        records.append({
            "id": person.id,
            "name": person.display_name,
            "search": person_search_text(person),
            "years": public_life_brief(person),
            "sections": sections,
            "trees": trees,
        })
    return records


def render_person_index(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/json" id="person-index">{payload}</script>\n'


def render_family_people(section_key: str, listed: list[Person]) -> str:
    """Name index for one section. Each item opens that person's stable card."""
    items = []
    for person in listed:
        brief = public_life_brief(person)
        years = f'<span class="person-years">{esc(brief)}</span>' if brief else ""
        items.append(
            f'<li><a href="#person-{esc(person.id)}">'
            f'<span class="person-name">{esc(person.display_name)}</span>{years}</a></li>'
        )
    return f"""<section id="{esc(section_key)}-people">
  <div class="wrap">
    <div class="sect-head">
      <h2>Персоны</h2>
      <div class="hr"></div>
    </div>
    <ul class="person-index">{"".join(items)}</ul>
  </div>
</section>
"""


def render_part_page(
    page_id: str,
    section_key: str,
    section: dict[str, Any],
    inner: str,
) -> str:
    """One semantic part of a family section, with the same five-way navigation."""
    if not inner:
        return ""
    return (
        f'<div class="page" id="{esc(page_id)}">\n'
        f"{render_section_nav(section_key, section)}{inner}</div>\n\n"
    )


def render_home_page(content: dict[str, Any]) -> str:
    """Approved hero, founder note and two equal archive entrances.

    Branch descriptions stay in the family sections. Archive search lives in
    the navigation, not in this page.
    """
    about = content["about"]
    archive = content["archive"]
    entries = "".join(
        f'<a class="card family-entry" href="#{esc(key)}">'
        f'<div class="tag">Семейный раздел</div><h3>{esc(section["title"])}</h3>'
        f'<span class="entry-link">{esc(archive["entry_link"])}</span></a>'
        for key, section in content["sections"].items()
    )
    return (
        '<div class="page visible" id="page1">\n'
        + render_hero_section(content["hero"])
        + f"""<section class="about" id="about">
  <div class="wrap">
    <div class="label">{esc(about["label"])}</div>
    <p class="about-text">{rich(about["text"])}</p>
  </div>
</section>

<section id="archive">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(archive["label"])}</div>
      <h2>{esc(archive["title"])}</h2>
      <div class="hr"></div>
    </div>
    <div class="grid g2">{entries}</div>
  </div>
</section>
</div>

"""
    )


def render_section_nav(section_key: str, section: dict[str, Any]) -> str:
    """Five semantic parts. Chronicle stays reachable by its own anchor, not here."""
    links = [
        (f"#{section_key}-branches", "Родовые ветви"),
        (f"#{section_key}-tree", "Генеалогическое древо"),
        (f"#{section_key}-people", "Персоны"),
        (f"#{section_key}-sources", "Документы"),
        (f"#{section_key}-places", "Географический указатель"),
    ]
    if section["gallery"]["photos"]:
        links.append((f"#{section_key}-gallery", section["gallery"]["title"]))
    items = "".join(f'<a href="{esc(target)}">{esc(label)}</a>' for target, label in links)
    return f'<div class="section-nav"><div class="wrap">{items}</div></div>\n'


def render_family_sources(
    section_key: str,
    sources: dict[str, Any],
    people: dict[str, Person],
    published: set[str],
) -> str:
    documents = []
    for item in sources["items"]:
        meta = " · ".join(esc(value) for value in (item["kind"], item.get("date", "")) if value)
        reference = ""
        if item.get("reference"):
            reference = f'<div class="reference">{esc(item["reference"])}</div>'
        image = ""
        if item.get("image"):
            image = (
                f'<img src="{esc(item["image"]["src"])}" alt="{esc(item["image"]["alt"])}" '
                'loading="lazy">'
            )
        related = _render_related_links(item.get("people", []), people, published)
        related_html = (
            f'<p class="document-related"><b>Связанные персоны:</b> {related}</p>'
            if related else ""
        )
        documents.append(
            f'<article class="document" id="{esc(item["id"])}"><div class="kind">{meta}</div>'
            f'<h3>{esc(item["title"])}</h3>{reference}'
            f'{paragraphs_html(item.get("paragraphs", []))}{related_html}{image}</article>'
        )
    return f"""<section class="src" id="{esc(section_key)}-sources">
  <div class="wrap">
    <div class="sect-head">
      <h2>{esc(sources["title"])}</h2>
      <div class="hr"></div>
    </div>
    <div class="documents">{"".join(documents)}</div>
  </div>
</section>

"""


def render_family_places(
    section_key: str,
    places: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    people: dict[str, Person],
    published: set[str],
) -> str:
    items = []
    for item in places["items"]:
        match = item.get("match", item["name"])
        source_ids = [entry["id"] for entry in item.get("people", [])]
        related_ids = [
            pid for pid in source_ids
            if pid in published and pid in people and not people[pid].is_living
        ]
        for pid in published:
            person = people[pid]
            if person.is_living:
                continue
            if match in (public_birth_place(person), public_residence(person), public_death_place(person)):
                related_ids.append(pid)
        # A settlement listed only for living people is itself a place leak.
        living_only = bool(source_ids) and all(
            pid in people and people[pid].is_living for pid in source_ids
        )
        has_documents = any(
            document_id in documents for document_id in item.get("documents", [])
        )
        if living_only and not related_ids and not has_documents:
            continue
        related = _render_related_links(related_ids, people, published)
        related_html = f'<p><b>Персоны:</b> {related}</p>' if related else ""
        document_links = " · ".join(
            f'<a href="#{esc(document_id)}">{esc(documents[document_id]["title"])}</a>'
            for document_id in item.get("documents", [])
            if document_id in documents
        )
        documents_html = f'<p><b>Документы:</b> {document_links}</p>' if document_links else ""
        note_html = f'<p>{esc(item["note"])}</p>' if item.get("note") else ""
        name_html = f'<h3>{esc(item["name"])}</h3>'
        if related_html or documents_html or note_html:
            items.append(
                f'<details class="place-item" id="{esc(item["id"])}">'
                f'<summary>{name_html}</summary>{note_html}{related_html}{documents_html}</details>'
            )
        else:
            items.append(f'<article class="place-item" id="{esc(item["id"])}">{name_html}</article>')
    return f"""<section class="alt" id="{esc(section_key)}-places">
  <div class="wrap">
    <div class="sect-head">
      <h2>{esc(places["title"])}</h2>
      <div class="hr"></div>
    </div>
    <div class="place-list">{"".join(items)}</div>
  </div>
</section>

"""


def render_family_chronicle(section_key: str, chronicle: dict[str, Any]) -> str:
    events = []
    for event in chronicle["events"]:
        place = f'<p>{esc(event["place"])}</p>' if event.get("place") else ""
        events.append(
            f'<div class="tl-item"><div class="tl-gen">{esc(event["date"])}</div>'
            f'<h3>{esc(event["title"])}</h3>{place}</div>'
        )
    return f"""<section id="{esc(section_key)}-timeline">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(chronicle["label"])}</div>
      <h2>{esc(chronicle["title"])}</h2>
      <div class="hr"></div>
    </div>
    <div class="tl">{"".join(events)}</div>
  </div>
</section>

"""


def render_family_gallery(section_key: str, gallery: dict[str, Any]) -> str:
    """Reserve gallery support without publishing an empty section or navigation item."""
    if not gallery["photos"]:
        return ""
    figures = []
    for photo in gallery["photos"]:
        caption = " · ".join(
            esc(value) for value in (photo.get("date", ""), photo.get("caption", "")) if value
        )
        figures.append(
            f'<figure><img src="{esc(photo["src"])}" alt="{esc(photo["alt"])}" loading="lazy">'
            f'<figcaption>{caption}</figcaption></figure>'
        )
    return f"""<section class="alt" id="{esc(section_key)}-gallery">
  <div class="wrap">
    <div class="sect-head">
      <h2>{esc(gallery["title"])}</h2>
      <div class="hr"></div>
    </div>
    <div class="gallery-grid">{"".join(figures)}</div>
  </div>
</section>

"""


def render_family_hub(section_key: str, section: dict[str, Any]) -> str:
    """Short entrance to a family section. The materials live in their own parts."""
    return f"""<div class="page" id="{esc(section["page_id"])}">
<section class="pagehead" id="{esc(section_key)}">
  <div class="wrap">
    <h1>{esc(section["title"])}</h1>
    <p class="sub">{esc(section["lead"])}</p>
  </div>
</section>
{render_section_nav(section_key, section)}</div>

"""


def render_family_branches(
    section_key: str,
    section: dict[str, Any],
    archive: dict[str, Any],
) -> str:
    cards = "".join(
        branch_card(branch, f"#{section_key}-tree", archive["tree_link"])
        for branch in section["branches"].values()
    )
    collateral = ""
    if section.get("collateral"):
        extra = section["collateral"]
        extra_cards = "".join(branch_card(item) for item in extra["items"])
        collateral = f"""<div class="collateral">
  <div class="subsection-head">
    <div class="label">{esc(extra["label"])}</div>
    <h3>{esc(extra["title"])}</h3>
    <p>{rich(extra["lead"])}</p>
  </div>
  <div class="grid g2">{extra_cards}</div>
</div>"""
    return f"""<section id="{esc(section_key)}-branches">
  <div class="wrap">
    <div class="sect-head">
      <div class="label">{esc(section["branches_label"])}</div>
      <h2>{esc(section["branches_title"])}</h2>
      <div class="hr"></div>
    </div>
    <div class="grid g2">{cards}</div>
{collateral}
  </div>
</section>
"""


def render_tree_page(
    section_key: str,
    section: dict[str, Any],
    tree: dict[str, Any],
    pedigree_svg: str,
    archive_search: dict[str, Any],
) -> str:
    """One pedigree with scoped public search and independent view controls."""
    search = tree["search"]
    controls = tree["controls"]
    search_id = f"search-{section_key}"
    results_id = f"results-{section_key}"
    return f"""<div class="page page-tree" id="{esc(section["tree_page_id"])}">
<div class="tree-stack" id="{esc(section_key)}-tree">
{render_section_nav(section_key, section)}
<section class="pagehead tree-pagehead">
  <div class="wrap">
    <h1>{esc(section["tree_title"])}</h1>
    <div class="tree-toolbar">
      <div class="tree-search" data-search-tree="{esc(section_key)}" data-no-results="{esc(search["no_results"])}" data-no-results-all="{esc(archive_search["no_results"])}" data-in-tree="{esc(archive_search["in_tree"])}">
        <label class="sr-only" for="{search_id}">{esc(search["label"])}</label>
        <div class="search-fields">
          <input id="{search_id}" type="search" placeholder="{esc(search["placeholder"])}" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="{results_id}">
          <label class="sr-only" for="scope-{section_key}">Область поиска</label>
          <select id="scope-{section_key}" aria-label="Область поиска">
            <option value="local">{esc(search["local"])}</option>
            <option value="global">{esc(search["global"])}</option>
          </select>
        </div>
        <div class="search-results" id="{results_id}" role="listbox" aria-label="{esc(search["label"])}" hidden></div>
      </div>
      <div class="tree-controls" data-controls-tree="{esc(section_key)}" role="group" aria-label="{esc(controls["group"])}">
        <button type="button" data-tree-action="zoom-out" aria-label="{esc(controls["zoom_out"])}" title="{esc(controls["zoom_out"])}">−</button>
        <output data-zoom-value aria-live="polite" aria-label="Текущий масштаб">100%</output>
        <button type="button" data-tree-action="zoom-in" aria-label="{esc(controls["zoom_in"])}" title="{esc(controls["zoom_in"])}">+</button>
        <button type="button" class="tree-view-button" data-tree-action="fit">{esc(controls["fit"])}</button>
        <button type="button" class="tree-view-button" data-tree-action="reset">{esc(controls["reset"])}</button>
      </div>
    </div>
    <details class="legend">
      <summary>Условные обозначения</summary>
      <div class="legend-items">
        <span><i class="unknown" aria-hidden="true">?</i>{esc(tree["legend"]["unknown"])}</span>
        <span><i class="approx" aria-hidden="true">ок.</i>{esc(tree["legend"]["approx"])}</span>
        <span><i class="ok" aria-hidden="true"></i>{esc(tree["legend"]["ok"])}</span>
        <span><i class="hyp" aria-hidden="true"></i>{esc(tree["legend"]["hyp"])}</span>
        <span><i class="q" aria-hidden="true"></i>{esc(tree["legend"]["q"])}</span>
      </div>
    </details>
  </div>
</section>
<section class="treewrap" tabindex="0" role="region" aria-label="{esc(section["tree_title"])}" data-tree="{esc(section_key)}" data-section-title="{esc(section["title"])}" data-no-results="{esc(search["no_results"])}">
  <div class="tree-stage">{pedigree_svg}</div>
</section>
</div>
</div>

"""


def render_footer(footer: dict[str, Any]) -> str:
    """Site footer: archive name only."""
    return f"""<footer id="contacts">
  <div class="wrap">
    <b>{esc(footer["brand"])}</b>
  </div>
</footer>

"""


def render_page_script() -> str:
    """Hash routing, scoped public search and independent SVG pan/zoom."""
    return """<script>
var cachedNavH = 56;
var treeViews = {};
var pendingTreeFocus = null;

function measureNavHeight() {
  var nav = document.querySelector('nav');
  if (!nav) return cachedNavH;
  var h = Math.ceil(nav.getBoundingClientRect().height);
  if (h > 0 && h !== cachedNavH) {
    cachedNavH = h;
    document.documentElement.style.setProperty('--navh', cachedNavH + 'px');
  }
  return cachedNavH;
}

function syncOverHero() {
  var heroEl = document.querySelector('#page1 .hero');
  var home = document.getElementById('page1');
  if (!heroEl || !home || !home.classList.contains('visible')) {
    document.body.classList.remove('over-hero');
    return;
  }
  var rect = heroEl.getBoundingClientRect();
  document.body.classList.toggle('over-hero', rect.bottom > cachedNavH + 8);
}

function applyTreeScale(view, requested) {
  var next = Math.max(0.05, Math.min(4, requested));
  view.scale = next;
  view.svg.style.width = (view.baseWidth * next) + 'px';
  view.svg.style.height = (view.baseHeight * next) + 'px';
  view.wrap.setAttribute('data-scale', next.toFixed(3));
  view.wrap.setAttribute('data-detail', next < 0.45 ? 'compact' : 'full');
  var output = document.querySelector('[data-controls-tree="' + view.key + '"] [data-zoom-value]');
  if (output) output.textContent = Math.round(next * 100) + '%';
}

function zoomTree(view, factor, clientX, clientY) {
  if (!view.wrap.closest('.page').classList.contains('visible')) return;
  var next = Math.max(0.05, Math.min(4, view.scale * factor));
  if (next === view.scale) return;
  var rect = view.wrap.getBoundingClientRect();
  var px = clientX == null ? view.wrap.clientWidth / 2 : clientX - rect.left;
  var py = clientY == null ? view.wrap.clientHeight / 2 : clientY - rect.top;
  var treeX = (view.wrap.scrollLeft + px - view.svg.offsetLeft) / view.scale;
  var treeY = (view.wrap.scrollTop + py - view.svg.offsetTop) / view.scale;
  applyTreeScale(view, next);
  view.wrap.scrollLeft = view.svg.offsetLeft + treeX * next - px;
  view.wrap.scrollTop = view.svg.offsetTop + treeY * next - py;
}

function fitTree(view) {
  if (!view.wrap.closest('.page').classList.contains('visible')) return;
  view.stage.style.paddingLeft = '';
  view.stage.style.paddingRight = '';
  view.stage.style.paddingTop = '';
  view.stage.style.paddingBottom = '';
  var style = getComputedStyle(view.stage);
  var horizontal = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  var vertical = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  var next = Math.min(
    (view.wrap.clientWidth - horizontal) / view.baseWidth,
    (view.wrap.clientHeight - vertical) / view.baseHeight
  );
  applyTreeScale(view, next);
  view.wrap.scrollLeft = Math.max(0, (view.wrap.scrollWidth - view.wrap.clientWidth) / 2);
  view.wrap.scrollTop = Math.max(0, (view.wrap.scrollHeight - view.wrap.clientHeight) / 2);
}

function resetTree(view) {
  view.stage.style.paddingLeft = '';
  view.stage.style.paddingRight = '';
  view.stage.style.paddingTop = '';
  view.stage.style.paddingBottom = '';
  applyTreeScale(view, 1);
  view.wrap.scrollLeft = 0;
  view.wrap.scrollTop = 0;
}

function clearTreeHighlight() {
  document.querySelectorAll('.pedigree .search-hit').forEach(function(card) {
    card.classList.remove('search-hit');
  });
}

function focusTreeCard(focus) {
  var view = treeViews[focus.tree];
  var card = document.getElementById(focus.cardId);
  if (!view || !card) return;
  clearTreeHighlight();
  var gutterX = Math.ceil(view.wrap.clientWidth / 2);
  var gutterY = Math.ceil(view.wrap.clientHeight / 2);
  view.stage.style.paddingLeft = gutterX + 'px';
  view.stage.style.paddingRight = gutterX + 'px';
  view.stage.style.paddingTop = gutterY + 'px';
  view.stage.style.paddingBottom = gutterY + 'px';
  applyTreeScale(view, 1);
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      var wrapRect = view.wrap.getBoundingClientRect();
      var cardRect = card.getBoundingClientRect();
      view.wrap.scrollLeft += cardRect.left + cardRect.width / 2 - wrapRect.left - view.wrap.clientWidth / 2;
      view.wrap.scrollTop += cardRect.top + cardRect.height / 2 - wrapRect.top - view.wrap.clientHeight / 2;
      card.classList.add('search-hit');
      view.wrap.focus({preventScroll: true});
    });
  });
}

function openPerson(id) {
  if (!id) return;
  if (window.location.hash === '#person-' + id) resolveRoute();
  else window.location.hash = 'person-' + id;
}

function showPersonInTree(tree, cardId) {
  var focus = {tree: tree, cardId: cardId};
  document.querySelectorAll('.search-results').forEach(function(node) { node.hidden = true; });
  document.querySelectorAll('input[aria-expanded="true"]').forEach(function(input) {
    input.setAttribute('aria-expanded', 'false');
  });
  if (window.location.hash === '#' + tree + '-tree') {
    pendingTreeFocus = null;
    requestAnimationFrame(function() { focusTreeCard(focus); });
  } else {
    pendingTreeFocus = focus;
    window.location.hash = tree + '-tree';
  }
}

function initTree(wrap) {
  var svg = wrap.querySelector('.pedigree');
  if (!svg) return;
  var box = svg.viewBox.baseVal;
  var view = {
    key: wrap.getAttribute('data-tree'),
    wrap: wrap,
    stage: wrap.querySelector('.tree-stage'),
    svg: svg,
    baseWidth: box.width,
    baseHeight: box.height,
    scale: 1
  };
  treeViews[view.key] = view;
  applyTreeScale(view, 1);

  var controls = document.querySelector('[data-controls-tree="' + view.key + '"]');
  if (controls) {
    controls.querySelectorAll('[data-tree-action]').forEach(function(button) {
      button.addEventListener('click', function() {
        var action = button.getAttribute('data-tree-action');
        if (action === 'zoom-in') zoomTree(view, 1.25);
        if (action === 'zoom-out') zoomTree(view, 0.8);
        if (action === 'fit') fitTree(view);
        if (action === 'reset') resetTree(view);
      });
    });
  }

  var pointers = new Map();
  var drag = null;
  var pinch = null;
  var tap = null;

  function pointerPair() {
    return Array.from(pointers.values()).slice(0, 2);
  }

  function startPinch() {
    var pair = pointerPair();
    if (pair.length < 2) return;
    var rect = wrap.getBoundingClientRect();
    var mx = (pair[0].x + pair[1].x) / 2 - rect.left;
    var my = (pair[0].y + pair[1].y) / 2 - rect.top;
    pinch = {
      distance: Math.max(1, Math.hypot(pair[0].x - pair[1].x, pair[0].y - pair[1].y)),
      scale: view.scale,
      treeX: (wrap.scrollLeft + mx - svg.offsetLeft) / view.scale,
      treeY: (wrap.scrollTop + my - svg.offsetTop) / view.scale
    };
    drag = null;
  }

  wrap.addEventListener('pointerdown', function(event) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    pointers.set(event.pointerId, {id: event.pointerId, x: event.clientX, y: event.clientY});
    wrap.setPointerCapture(event.pointerId);
    wrap.classList.add('is-panning');
    if (pointers.size === 1) {
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY, left: wrap.scrollLeft, top: wrap.scrollTop};
      tap = {id: event.pointerId, x: event.clientX, y: event.clientY, moved: false};
      pinch = null;
    } else if (pointers.size === 2) {
      tap = null;
      startPinch();
    }
    event.preventDefault();
  });

  wrap.addEventListener('pointermove', function(event) {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, {id: event.pointerId, x: event.clientX, y: event.clientY});
    if (tap && tap.id === event.pointerId && Math.hypot(event.clientX - tap.x, event.clientY - tap.y) > 8) {
      tap.moved = true;
    }
    if (pointers.size >= 2) tap = null;
    if (pointers.size >= 2) {
      if (!pinch) startPinch();
      var pair = pointerPair();
      var distance = Math.max(1, Math.hypot(pair[0].x - pair[1].x, pair[0].y - pair[1].y));
      var rect = wrap.getBoundingClientRect();
      var mx = (pair[0].x + pair[1].x) / 2 - rect.left;
      var my = (pair[0].y + pair[1].y) / 2 - rect.top;
      applyTreeScale(view, pinch.scale * distance / pinch.distance);
      wrap.scrollLeft = svg.offsetLeft + pinch.treeX * view.scale - mx;
      wrap.scrollTop = svg.offsetTop + pinch.treeY * view.scale - my;
    } else if (drag && drag.id === event.pointerId) {
      wrap.scrollLeft = drag.left - (event.clientX - drag.x);
      wrap.scrollTop = drag.top - (event.clientY - drag.y);
    }
    event.preventDefault();
  });

  function endPointer(event) {
    if (!pointers.has(event.pointerId)) return;
    if (tap && event.pointerId === tap.id && !tap.moved && pointers.size === 1) {
      var hit = document.elementFromPoint(event.clientX, event.clientY);
      var node = hit && hit.closest && hit.closest('a.bx[data-person-id]');
      if (node) openPerson(node.getAttribute('data-person-id'));
    }
    if (tap && event.pointerId === tap.id) tap = null;
    pointers.delete(event.pointerId);
    pinch = null;
    drag = null;
    if (pointers.size === 1) {
      var remaining = pointerPair()[0];
      drag = {id: remaining.id, x: remaining.x, y: remaining.y, left: wrap.scrollLeft, top: wrap.scrollTop};
    }
    if (pointers.size === 0) wrap.classList.remove('is-panning');
  }
  wrap.addEventListener('pointerup', endPointer);
  wrap.addEventListener('pointercancel', endPointer);
  wrap.addEventListener('lostpointercapture', endPointer);
  wrap.addEventListener('dragstart', function(event) { event.preventDefault(); });
}

function normalizedSearch(value) {
  return (value || '').toLocaleLowerCase('ru-RU').replace(/ё/g, 'е').replace(/[^a-zа-я0-9]+/gi, ' ').trim();
}

function loadPersonIndex() {
  if (loadPersonIndex.data) return loadPersonIndex.data;
  var node = document.getElementById('person-index');
  loadPersonIndex.data = node ? JSON.parse(node.textContent) : [];
  return loadPersonIndex.data;
}

function matchPeople(query, scope, treeKey) {
  var tokens = normalizedSearch(query).split(/\\s+/).filter(Boolean);
  if (!tokens.length) return [];
  return loadPersonIndex().filter(function(person) {
    if (treeKey && !person.trees.some(function(tree) { return tree.key === treeKey; })) return false;
    if (scope && scope !== 'all' && !person.sections.some(function(section) { return section.key === scope; })) return false;
    var haystack = normalizedSearch(person.search);
    return tokens.every(function(token) { return haystack.indexOf(token) !== -1; });
  }).sort(function(a, b) {
    return a.name.localeCompare(b.name, 'ru') || a.id.localeCompare(b.id);
  });
}

function hideSearchResults(search) {
  var results = search.querySelector('.search-results');
  if (!results) return;
  results.hidden = true;
  var input = search.querySelector('input');
  if (input) input.setAttribute('aria-expanded', 'false');
}

function placementFor(person, preferredTree) {
  var trees = person.trees || [];
  var index;
  for (index = 0; index < trees.length; index++) {
    if (trees[index].key === preferredTree) return trees[index];
  }
  return trees.length ? trees[0] : null;
}

function appendResultText(parent, person, showSection) {
  var nameEl = document.createElement('span');
  nameEl.className = 'result-name';
  nameEl.textContent = person.name;
  parent.appendChild(nameEl);
  if (person.years) {
    var yearsEl = document.createElement('span');
    yearsEl.className = 'result-years';
    yearsEl.textContent = person.years;
    parent.appendChild(yearsEl);
  }
  if (showSection && person.sections && person.sections.length) {
    var sectionEl = document.createElement('span');
    sectionEl.className = 'result-section';
    sectionEl.textContent = person.sections.map(function(section) { return section.title; }).join(' · ');
    parent.appendChild(sectionEl);
  }
}

function chooseSearchResult(search, button) {
  hideSearchResults(search);
  var cardId = button.getAttribute('data-card-id');
  if (!cardId) {
    openPerson(button.getAttribute('data-person-id'));
    return;
  }
  showPersonInTree(button.getAttribute('data-tree'), cardId);
}

function renderSearchResults(search) {
  var input = search.querySelector('input');
  var scope = search.querySelector('select').value;
  var localTree = search.getAttribute('data-search-tree');
  var results = search.querySelector('.search-results');
  var query = normalizedSearch(input.value);
  results.textContent = '';
  if (!query) {
    hideSearchResults(search);
    return;
  }
  var matches = matchPeople(input.value, 'all', scope === 'local' ? localTree : '');
  if (!matches.length) {
    var empty = document.createElement('div');
    empty.className = 'search-empty';
    empty.textContent = scope === 'global'
      ? (search.getAttribute('data-no-results-all') || search.getAttribute('data-no-results') || '')
      : (search.getAttribute('data-no-results') || '');
    results.appendChild(empty);
  }
  matches.forEach(function(person) {
    var placement = placementFor(person, localTree);
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'search-result';
    button.setAttribute('role', 'option');
    button.setAttribute('aria-selected', 'false');
    button.setAttribute('data-person-id', person.id);
    if (placement && (scope === 'local' || person.trees.length)) {
      if (scope === 'local' || placement) {
        button.setAttribute('data-card-id', placement.card);
        button.setAttribute('data-tree', placement.key);
      }
    }
    if (scope !== 'local' && !placement) {
      button.removeAttribute('data-card-id');
    }
    appendResultText(button, person, scope === 'global');
    button.addEventListener('click', function() { chooseSearchResult(search, button); });
    button.addEventListener('keydown', function(event) {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      var sibling = event.key === 'ArrowDown' ? button.nextElementSibling : button.previousElementSibling;
      if (sibling && sibling.classList.contains('search-result')) sibling.focus();
    });
    results.appendChild(button);
  });
  results.hidden = false;
  input.setAttribute('aria-expanded', 'true');
}

function renderNavResults(search) {
  var input = search.querySelector('input');
  var scope = search.querySelector('select').value;
  var results = search.querySelector('.search-results');
  var query = normalizedSearch(input.value);
  results.textContent = '';
  if (!query) {
    hideSearchResults(search);
    return;
  }
  var matches = matchPeople(input.value, scope, '');
  var inTreeLabel = search.getAttribute('data-in-tree') || '';
  if (!matches.length) {
    var empty = document.createElement('div');
    empty.className = 'search-empty';
    empty.textContent = search.getAttribute('data-no-results') || '';
    results.appendChild(empty);
  }
  matches.forEach(function(person) {
    var row = document.createElement('div');
    row.className = 'search-result';
    row.setAttribute('role', 'option');
    var open = document.createElement('a');
    open.className = 'result-open';
    open.href = '#person-' + person.id;
    appendResultText(open, person, true);
    open.addEventListener('click', function() { hideSearchResults(search); });
    row.appendChild(open);
    (person.trees || []).forEach(function(tree) {
      var treeLink = document.createElement('a');
      treeLink.className = 'result-tree';
      treeLink.href = '#' + tree.key + '-tree';
      treeLink.setAttribute('data-show-tree', tree.key);
      treeLink.setAttribute('data-card-id', tree.card);
      treeLink.textContent = person.trees.length > 1 ? inTreeLabel + ' · ' + tree.title : inTreeLabel;
      row.appendChild(treeLink);
    });
    results.appendChild(row);
  });
  results.hidden = false;
  input.setAttribute('aria-expanded', 'true');
}

function bindSearchKeys(search, render) {
  var input = search.querySelector('input');
  input.addEventListener('input', function() {
    if (!normalizedSearch(input.value)) clearTreeHighlight();
    render(search);
  });
  input.addEventListener('focus', function() { render(search); });
  input.addEventListener('keydown', function(event) {
    var first = search.querySelector('button.search-result, a.result-open');
    if (event.key === 'ArrowDown' && first) {
      event.preventDefault();
      first.focus();
    } else if (event.key === 'Enter') {
      var open = search.querySelector('a.result-open');
      var button = search.querySelector('button.search-result');
      if (open) {
        event.preventDefault();
        openPerson(open.getAttribute('href').slice(8));
        hideSearchResults(search);
      } else if (button) {
        event.preventDefault();
        chooseSearchResult(search, button);
      }
    } else if (event.key === 'Escape') {
      hideSearchResults(search);
    }
  });
  input.addEventListener('blur', function() {
    setTimeout(function() {
      if (!search.contains(document.activeElement)) hideSearchResults(search);
    }, 150);
  });
  var select = search.querySelector('select');
  if (select) select.addEventListener('change', function() { render(search); });
}

function initSearch(search) {
  bindSearchKeys(search, renderSearchResults);
}

function initPersonSearch(search) {
  bindSearchKeys(search, renderNavResults);
}

function resolveRoute() {
  var hash = window.location.hash.slice(1) || 'top';
  var target = document.getElementById(hash);
  if (!target) {
    hash = 'top';
    target = document.getElementById('top');
  }
  var page = target.closest('.page');
  if (!page) return;
  document.querySelectorAll('.page').forEach(function(candidate) {
    candidate.classList.toggle('visible', candidate === page);
  });
  var current = 'about';
  if (hash.indexOf('person-') === 0) current = '';
  if (hash.indexOf('matyukhiny') === 0) current = 'matyukhiny';
  if (hash.indexOf('skiba') === 0) current = 'skiba';
  document.querySelectorAll('nav .navbtn').forEach(function(link) {
    var isActive = link.getAttribute('data-section') === current;
    link.classList.toggle('active', isActive);
    if (isActive) {
      link.setAttribute('aria-current', 'true');
    } else {
      link.removeAttribute('aria-current');
    }
  });
  syncOverHero();
  function alignRoute() {
    if (page.querySelector('.treewrap')) window.scrollTo(0, 0);
    else target.scrollIntoView({block:'start'});
  }
  function clearNavOverlap() {
    var navEl = document.querySelector('nav');
    var sectionNav = page.querySelector('.section-nav');
    if (!navEl || !sectionNav) return;
    var navBottom = navEl.getBoundingClientRect().bottom;
    var sectionRect = sectionNav.getBoundingClientRect();
    if (sectionRect.top < navBottom - 1 && sectionRect.bottom > 0) {
      window.scrollBy(0, sectionRect.top - navBottom);
    }
  }
  requestAnimationFrame(function() {
    alignRoute();
    requestAnimationFrame(function() { clearNavOverlap(); });
    setTimeout(clearNavOverlap, 60);
    syncOverHero();
    if (pendingTreeFocus) {
      var focus = pendingTreeFocus;
      pendingTreeFocus = null;
      focusTreeCard(focus);
    }
  });
}

document.querySelectorAll('.treewrap').forEach(initTree);
document.querySelectorAll('.tree-search').forEach(initSearch);
document.querySelectorAll('[data-person-search]').forEach(initPersonSearch);
document.addEventListener('click', function(event) {
  var link = event.target.closest('[data-show-tree]');
  if (!link) return;
  event.preventDefault();
  showPersonInTree(link.getAttribute('data-show-tree'), link.getAttribute('data-card-id'));
});
window.addEventListener('hashchange', resolveRoute);
var heroEl = document.querySelector('#page1 .hero');
if (heroEl && 'IntersectionObserver' in window) {
  new IntersectionObserver(syncOverHero, {threshold: [0, 0.01, 0.1, 0.25, 0.5, 1]}).observe(heroEl);
}
window.addEventListener('scroll', syncOverHero, {passive: true});
window.addEventListener('resize', function() {
  measureNavHeight();
  syncOverHero();
});
measureNavHeight();
resolveRoute();
requestAnimationFrame(function() {
  measureNavHeight();
  syncOverHero();
});
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(function() {
    measureNavHeight();
    syncOverHero();
  });
}
</script>
</body>
</html>"""


def build_html(
    people: dict[str, Person],
    families: dict[str, Family],
    meta: dict[str, str],
    content: dict[str, Any],
) -> str:
    family = resolve_family_context(people, families, meta["root"])
    css = CSS.read_text(encoding="utf-8") if CSS.exists() else ""
    parts = [
        render_document_start(content["meta"], css),
        render_nav(content["meta"], content["archive_search"], content["sections"]),
        render_home_page(content),
    ]

    roots = {"root": family.root, "spouse": family.spouse}
    section_ids: dict[str, set[str]] = {}
    for section_key, section in content["sections"].items():
        anchor = roots[section["root"]]
        section_ids[section_key] = section_person_ids(anchor.id, people, families)

    membership: dict[str, list[tuple[str, str]]] = {}
    for section_key, section in content["sections"].items():
        for pid in section_ids[section_key]:
            membership.setdefault(pid, []).append((section_key, section["title"]))

    for section_key, section in content["sections"].items():
        listed = [
            people[pid]
            for pid in sorted(section_ids[section_key], key=lambda item: _person_sort_key(item, people))
        ]
        parts.append(render_family_hub(section_key, section))
        parts.append(render_part_page(
            f"page-{section_key}-branches",
            section_key,
            section,
            render_family_branches(section_key, section, content["archive"]),
        ))
        parts.append(render_part_page(
            f"page-{section_key}-people",
            section_key,
            section,
            render_family_people(section_key, listed),
        ))
        parts.append(render_part_page(
            f"page-{section_key}-sources",
            section_key,
            section,
            render_family_sources(
                section_key,
                section["sources"],
                people,
                section_ids[section_key],
            ),
        ))
        parts.append(render_part_page(
            f"page-{section_key}-places",
            section_key,
            section,
            render_family_places(
                section_key,
                section["places"],
                {item["id"]: item for item in section["sources"]["items"]},
                people,
                section_ids[section_key],
            ),
        ))
        parts.append(render_part_page(
            f"page-{section_key}-timeline",
            section_key,
            section,
            render_family_chronicle(section_key, section["chronicle"]),
        ))
        gallery = render_family_gallery(section_key, section["gallery"])
        if gallery:
            parts.append(render_part_page(
                f"page-{section_key}-gallery",
                section_key,
                section,
                gallery,
            ))

    tree_cards: dict[str, dict[str, str]] = {}
    for section_key, section in content["sections"].items():
        root = roots[section["root"]]
        spouse = family.spouse if root.id == family.root.id else family.root
        id_prefix = "pedigree" if section_key == "matyukhiny" else f"pedigree-{section_key}"
        pedigree_svg = render_pedigree_svg(
            root,
            spouse,
            family.child,
            people,
            families,
            content,
            max_gen=7,
            include_spouse_ancestors=False,
            id_prefix=id_prefix,
            description=section["tree_lead"],
        )
        tree_cards[section_key] = svg_person_cards(pedigree_svg)
        parts.append(
            render_tree_page(
                section_key,
                section,
                content["tree"],
                pedigree_svg,
                content["archive_search"],
            )
        )

    parts.append(render_person_cards_page(people, families, content, membership, tree_cards))
    parts.append(render_person_index(public_search_records(people, membership, tree_cards)))
    parts.extend([render_footer(content["footer"]), render_page_script()])
    return "".join(parts)


def validate_inputs() -> None:
    """Fail fast with a clear message when input files are missing or unreadable."""
    if not CONTENT_PATH.exists():
        sys.exit(f"Ошибка: не найден {CONTENT_PATH.relative_to(ROOT)} — файл редакционных текстов обязателен для сборки.")

    if not DATA_PATH.exists():
        sys.exit(
            f"Ошибка: файл данных не найден ({DATA_PATH.relative_to(ROOT)}).\n"
            "family.yaml хранится только локально и не коммитится; при необходимости "
            "восстановите его скриптом scripts/extract_data.py из опубликованного index.html."
        )

    raw = DATA_PATH.read_bytes()
    if not raw.strip():
        sys.exit(f"Ошибка: файл данных пуст ({DATA_PATH.relative_to(ROOT)}).")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        sys.exit(
            f"Ошибка: {DATA_PATH.relative_to(ROOT)} не в кодировке UTF-8 (байт {exc.start}).\n"
            "Пересохраните файл в UTF-8 и запустите сборку снова."
        )

    if not re.search(r"^persons:", text, re.MULTILINE):
        sys.exit(
            f"Ошибка: в {DATA_PATH.relative_to(ROOT)} нет раздела «persons» — файл не похож "
            "на данные семейного архива. Проверьте структуру (meta/root/persons/families)."
        )


def main() -> None:
    validate_inputs()
    content = load_content()
    people, families, meta = load_family(DATA_PATH)
    html_content = build_html(people, families, meta, content)

    # Post-build safety validation (P0 invariant check):
    # Ensure no exact birth dates or places of living people leaked into the generated HTML.
    for person in people.values():
        if person.is_living:
            if person.birt and len(person.birt) > 4:
                # If exact birth date exists (e.g. "17 APR 1971"), it must not be in the output
                if person.birt in html_content:
                    raise ValueError(f"CRITICAL PRIVACY LEAK: Exact birth date '{person.birt}' of living person {person.id} ({person.label}) leaked into generated HTML!")
                # Also check common formatted variations of exact dates to be safe
                formatted = format_date(person.birt)
                if formatted and len(formatted) > 4 and formatted in html_content:
                    raise ValueError(f"CRITICAL PRIVACY LEAK: Formatted birth date '{formatted}' of living person {person.id} ({person.label}) leaked into generated HTML!")
            if person.birt_plac and person.public_place:
                raise ValueError(
                    f"CRITICAL PRIVACY LEAK: public_place is not empty for living person {person.id}"
                )
            card_match = re.search(
                rf'<article class="person-card" id="person-{re.escape(person.id)}"[\s\S]*?</article>',
                html_content,
            )
            if card_match and "<dt>Место" in card_match.group(0):
                raise ValueError(
                    f"CRITICAL PRIVACY LEAK: place fact rendered for living person {person.id}"
                )
    for block in re.findall(
        r'<(?:details|article) class="place-item"[\s\S]*?</(?:details|article)>',
        html_content,
    ):
        for person in people.values():
            if person.is_living and f'#person-{person.id}"' in block:
                raise ValueError(
                    f"CRITICAL PRIVACY LEAK: living person {person.id} linked from a place item"
                )

    OUTPUT_PATH.write_text(html_content, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
