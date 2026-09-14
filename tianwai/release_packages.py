"""Validated private delivery packages for the first thirteen concept volumes.

Editorial packages contain no prices. Prices remain in the private database;
package readiness never implies that operational payment checks are complete.
"""

from urllib.parse import urlsplit

from .commerce import PRICING_BATCH_SLUGS, commerce_status, valid_prepared_price
from .ideas import publication_gaps
from .release_packages_a import PACKAGES_A
from .release_packages_b import PACKAGES_B


_SECTION_RULES = {
    "flow_steps": ("六步流程", 6, 6, ("title", "body", "input", "output")),
    "specs": ("規格與待驗證項", 5, None, ("item", "proposal", "verify")),
    "mvp_steps": ("六步 Micro-MVP", 6, 6, ("title", "action", "record", "stop")),
    "tests": ("驗證案例", 6, None, ("case", "setup", "expected", "record")),
    "handoff": ("交付清單", 5, None, ("item", "example", "fill_in")),
    "sources": ("參考來源", 1, None, ("label", "url", "note")),
}


def get_release_package(slug):
    """Return only an approved volume's package; missing/duplicate data fails closed."""
    if slug not in PRICING_BATCH_SLUGS:
        return None
    matches = []
    for collection in (PACKAGES_A, PACKAGES_B):
        if isinstance(collection, dict) and slug in collection:
            matches.append(collection[slug])
    return matches[0] if len(matches) == 1 and isinstance(matches[0], dict) else None


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _sequence(value):
    return isinstance(value, (list, tuple))


def _source_url(value):
    if not _text(value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def release_package_structure_gaps(package):
    """Check the deliverable structure without publishing private text in errors."""
    if not isinstance(package, dict):
        return ["完整交付套件"]
    gaps = []
    for field, label in (("title", "套件名稱"), ("scope", "交付範圍"), ("boundary", "使用限制與邊界")):
        if not _text(package.get(field)):
            gaps.append(label)
    for field, (label, minimum, maximum, keys) in _SECTION_RULES.items():
        items = package.get(field)
        if (
            not _sequence(items) or len(items) < minimum
            or (maximum is not None and len(items) > maximum)
            or any(not isinstance(item, dict) or any(not _text(item.get(key)) for key in keys) for item in items)
        ):
            gaps.append(label)
    notes = package.get("figure_notes")
    if not isinstance(notes, dict) or any(not _text(notes.get(slot)) for slot in ("hero", "diagram", "scene")):
        gaps.append("三張圖的專屬解說")
    sources = package.get("sources")
    if _sequence(sources) and any(not isinstance(source, dict) or not _source_url(source.get("url")) for source in sources):
        gaps.append("可用的 HTTPS 來源連結")
    worksheets = package.get("worksheets")
    worksheets_valid = _sequence(worksheets) and len(worksheets) >= 3
    if worksheets_valid:
        for sheet in worksheets:
            if not isinstance(sheet, dict) or not _text(sheet.get("title")):
                worksheets_valid = False
                break
            columns, rows = sheet.get("columns"), sheet.get("rows")
            if (
                not _sequence(columns) or len(columns) < 2 or not all(_text(column) for column in columns)
                or len(set(columns)) != len(columns) or not _sequence(rows) or not rows
            ):
                worksheets_valid = False
                break
            for row in rows:
                cells = row if _sequence(row) and len(row) == len(columns) else None
                if cells is None or any(not isinstance(cell, str) for cell in cells):
                    worksheets_valid = False
                    break
    if not worksheets_valid:
        gaps.append("至少三份欄列完整的工作表")
    return list(dict.fromkeys(gaps))


def release_package_status(idea, payment_status):
    """Private editorial gate. This does not grant operational sale approval."""
    # Keep private_content's access-session imports out of module initialization;
    # the paid reader can safely import get_release_package from this module.
    from .private_content import ASSET_FIELDS, resolve_private_asset

    idea = dict(idea)
    package = get_release_package(idea.get("slug"))
    gaps = release_package_structure_gaps(package)
    if idea.get("slug") not in PRICING_BATCH_SLUGS:
        gaps.insert(0, "本次前十三卷範圍")
    gaps.extend(publication_gaps(idea))
    if not _text(idea.get("paid_content")) or len(idea["paid_content"].strip()) < 20:
        gaps.append("原始完整內文")
    asset_count = 0
    for slot, field in ASSET_FIELDS.items():
        if resolve_private_asset(idea.get(field)) is None:
            gaps.append({"hero": "主視覺實際素材", "diagram": "機制圖實際素材", "scene": "情境圖實際素材"}[slot])
        else:
            asset_count += 1
    if not valid_prepared_price(idea.get("prepared_price")):
        gaps.append("已確認的逐卷預備價格")
    if idea.get("workflow_status") not in {"ready", "published"}:
        gaps.append("已完成內容檢查的工作狀態")
    if idea.get("sale_state") not in {"preparing", "price_listed", "for_sale"}:
        gaps.append("有效的銷售狀態")
    package = package or {}
    counts = {
        key: len(package.get(key, ())) if _sequence(package.get(key)) else 0
        for key in (*_SECTION_RULES, "worksheets")
    }
    counts["figures"] = asset_count
    return {
        "ready": not gaps,
        "gaps": list(dict.fromkeys(gaps)),
        "counts": counts,
        "commerce": commerce_status(idea, payment_status, private=True),
    }
