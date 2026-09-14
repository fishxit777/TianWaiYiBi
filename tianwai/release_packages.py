"""Validated private delivery packages and the existing ReLock concept guide.

Editorial packages contain no prices. Prices remain in the private database;
package readiness never implies that operational payment checks are complete.
"""

from urllib.parse import urlsplit

from . import concept_guides
from .commerce import PRICING_BATCH_SLUGS, commerce_status, valid_prepared_price
from .ideas import publication_gaps
from .release_packages_a import PACKAGES_A
from .release_packages_b import PACKAGES_B

CONCEPT_GUIDE_SLUG = "sealed-concept-v14"


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


def get_release_concept_guide(slug):
    """Only the approved existing guide is eligible for this publication flow."""
    if slug != CONCEPT_GUIDE_SLUG or slug not in PRICING_BATCH_SLUGS:
        return None
    guide = concept_guides.get_concept_guide(slug)
    return guide if isinstance(guide, dict) else None


def release_package_metadata(slug):
    if slug == CONCEPT_GUIDE_SLUG:
        guide = get_release_concept_guide(slug) or {}
        return {
            "format": "concept_guide", "title": guide.get("title", ""),
            "scope": guide.get("lead", ""), "boundary": guide.get("boundary", ""),
        }
    package = get_release_package(slug) or {}
    return {"format": "research_package", **{field: package.get(field, "") for field in ("title", "scope", "boundary")}}


def _guide_structure_gaps(guide, manuscript):
    """Validate the existing delivery format without inventing worksheet content."""
    guide = guide or {}
    gaps = []
    for field, label in (
        ("title", "導讀名稱"), ("lead", "導讀範圍"), ("caption", "導讀圖說"),
        ("state_summary", "狀態轉換說明"), ("boundary", "導讀使用邊界"), ("asset", "導讀素材設定"),
    ):
        if not _text(guide.get(field)):
            gaps.append(label)
    for field, required, label in (("steps", 7, "七步完整導讀"), ("validation_scenarios", 3, "三種待驗證模擬情境")):
        items = guide.get(field)
        if (
            not _sequence(items) or len(items) != required
            or any(not isinstance(item, dict) or not all(_text(item.get(key)) for key in ("title", "body")) for item in items)
            or len({item["title"].strip() for item in items}) != required
        ):
            gaps.append(label)
    sections = {}
    if _text(manuscript):
        for block in manuscript.replace("\r\n", "\n").split("\n\n"):
            title, _, body = block.strip().partition("\n")
            sections.setdefault(title, []).append(body.strip())
    mvp_count = 0
    for number in range(1, 7):
        prefix = f"Micro-MVP｜步驟 {number}｜"
        matches = [bodies for title, bodies in sections.items() if title.startswith(prefix) and title[len(prefix):].strip()]
        if len(matches) == 1 and len(matches[0]) == 1 and matches[0][0]:
            mvp_count += 1
    if mvp_count != 6 or sum(title.startswith("Micro-MVP｜步驟 ") for title in sections) != 6:
        gaps.append("原始內文六步 Micro-MVP")
    for title in ("模組與圖號對照", "狀態與人工操作", "測試空白紀錄", "限制與未知", "安全與使用邊界"):
        if len(sections.get(title, ())) != 1 or not sections[title][0]:
            gaps.append(f"原始內文：{title}")
    return gaps, mvp_count


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
    slug = idea.get("slug")
    package = get_release_package(slug)
    guide = get_release_concept_guide(slug)
    if slug == CONCEPT_GUIDE_SLUG:
        gaps, mvp_count = _guide_structure_gaps(guide, idea.get("paid_content"))
    else:
        gaps = release_package_structure_gaps(package)
    if idea.get("slug") not in PRICING_BATCH_SLUGS:
        gaps.insert(0, "本次十四卷範圍")
    gaps.extend(publication_gaps(idea))
    if not _text(idea.get("paid_content")) or len(idea["paid_content"].strip()) < 20:
        gaps.append("原始完整內文")
    asset_count = 0
    asset_paths = []
    for slot, field in ASSET_FIELDS.items():
        path = resolve_private_asset(idea.get(field))
        if path is None:
            gaps.append({"hero": "主視覺實際素材", "diagram": "機制圖實際素材", "scene": "情境圖實際素材"}[slot])
        else:
            asset_count += 1
            asset_paths.append(path)
    if slug == CONCEPT_GUIDE_SLUG:
        path = resolve_private_asset((guide or {}).get("asset"))
        if path is None:
            gaps.append("完整介紹流程實際素材")
        else:
            asset_count += 1
            asset_paths.append(path)
        if len(set(asset_paths)) != len(asset_paths):
            gaps.append("四張不同的交付素材")
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
    if slug == CONCEPT_GUIDE_SLUG:
        guide = guide or {}
        counts.update({key: 0 for key in (*_SECTION_RULES, "worksheets")})
        counts.update(
            flow_steps=len(guide["steps"]) if _sequence(guide.get("steps")) else 0,
            mvp_steps=mvp_count,
            tests=len(guide["validation_scenarios"]) if _sequence(guide.get("validation_scenarios")) else 0,
        )
    return {
        "ready": not gaps,
        "gaps": list(dict.fromkeys(gaps)),
        "counts": counts,
        "commerce": commerce_status(idea, payment_status, private=True),
    }
