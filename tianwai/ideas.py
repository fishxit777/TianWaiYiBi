"""Blind-box idea classification and publication rules.

The classifier is deliberately deterministic: the owner can see why a vein was
recommended, override it, and run the service without sending raw ideas to a
third-party AI provider.
"""

from __future__ import annotations

import re
from collections import Counter


VEINS = {
    "守護脈": {
        "seal": "守",
        "description": "安全、防災、健康與風險降低",
        "keywords": ("安全", "危險", "事故", "爆胎", "車禍", "防災", "健康", "保護", "救援", "風險", "受傷", "警示"),
    },
    "造物脈": {
        "seal": "造",
        "description": "實體產品、機構、材料與空間",
        "keywords": ("輪胎", "機構", "模組", "材料", "裝置", "產品", "零件", "結構", "拆分", "硬體", "工具", "空間"),
    },
    "靈機脈": {
        "seal": "機",
        "description": "軟體、資料、AI、自動化與平台",
        "keywords": ("軟體", "資料", "數據", "ai", "自動化", "平台", "app", "系統", "演算法", "網站", "機器人", "api"),
    },
    "破局脈": {
        "seal": "局",
        "description": "商業、服務、營運與交易模式",
        "keywords": ("商業", "營運", "服務", "交易", "付款", "訂單", "成本", "收入", "客戶", "銷售", "流程", "創業", "市場"),
    },
    "人間脈": {
        "seal": "人",
        "description": "日常、家庭、公共與環境生活",
        "keywords": ("生活", "家庭", "日常", "公共", "環境", "社區", "老人", "兒童", "通勤", "居家", "城市", "無障礙"),
    },
    "傳音脈": {
        "seal": "音",
        "description": "內容、品牌、教育、文化與社群",
        "keywords": ("內容", "品牌", "教育", "文化", "社群", "課程", "故事", "媒體", "創作", "行銷", "溝通", "學習"),
    },
}

DEFAULT_VEIN = "破局脈"


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_idea(text: str) -> dict:
    """Return an explainable primary/secondary six-vein recommendation."""
    normalized = _normalized(text)
    scores = Counter()
    reasons = {}
    for vein, config in VEINS.items():
        matched = [word for word in config["keywords"] if word in normalized]
        scores[vein] = len(matched)
        reasons[vein] = matched

    # Harm-prevention is the value delivered by a safety concept, even when the
    # implementation is mechanical. This encodes the agreed value-first rule.
    safety_signals = ("爆胎", "車禍", "事故", "危險", "安全", "受傷", "防災")
    if any(signal in normalized for signal in safety_signals):
        scores["守護脈"] += 3

    ranked = sorted(VEINS, key=lambda vein: (-scores[vein], list(VEINS).index(vein)))
    primary = ranked[0] if scores[ranked[0]] else DEFAULT_VEIN
    secondary = next((vein for vein in ranked if vein != primary and scores[vein] > 0), "")
    total = sum(max(score, 0) for score in scores.values())
    confidence = 45 if not total else min(96, 55 + round(41 * scores[primary] / total))
    matched_tags = []
    for vein in (primary, secondary):
        matched_tags.extend(reasons.get(vein, []))
    tags = list(dict.fromkeys(matched_tags))[:6]
    return {
        "primary_vein": primary,
        "secondary_vein": secondary,
        "confidence": confidence,
        "tags": tags,
        "reason": "、".join(reasons.get(primary, [])) or "目前訊號較少，先依商業價值歸入破局脈",
    }


def publication_gaps(idea: dict) -> list[str]:
    """List missing buyer-facing fields that block publication."""
    required = {
        "public_title": "封印名稱",
        "title": "真實標題",
        "primary_vein": "主脈",
        "discipline": "公開領域線索",
        "summary": "公開摘要",
        "teaser": "購買前線索",
        "paid_content": "拆封後完整內容",
        "deliverables": "拆封內容清單",
        "maturity": "成熟度",
        "hero_image": "主視覺",
    }
    return [label for key, label in required.items() if not str(idea.get(key) or "").strip()]
