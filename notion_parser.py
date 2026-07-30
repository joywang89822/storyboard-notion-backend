# -*- coding: utf-8 -*-
"""把「分鏡工具」Notion 範本頁面的內容，解析成 pptx_builder.py 吃的 JSON 結構。

跟這份 Notion 範本頁面的排版是綁死的（詳見 SCHEMA.md 開頭說明），如果之後同事改動範本的
區塊結構（例如砍掉某個 toggle、改欄位名稱），這支程式就要跟著調整。

需要環境變數 NOTION_TOKEN（Notion 內部整合的 secret，見 SETUP.md 申請步驟）。
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

# 這些子樹我們解析時用不到（例如純參考用的尺寸對照表），遞迴抓取時直接跳過，
# 避免浪費 API 呼叫次數拖慢整體速度（Render 免費方案本來就慢，頁面 toggle 一多很容易逾時）。
SKIP_SUBTREE_PREFIXES = ["原始尺寸對照表"]

_session = requests.Session()

FIELD_PREFIXES = [
    "場景/道具", "音樂", "音效", "動作描述", "對白/字卡文案", "秒數",
    "畫面風格", "配樂風格", "廣告TA", "廣告目的", "廣告鉤子", "備註",
]

SIZE_CATEGORIES = ["Banner", "Video", "Gif（JPG）", "Gif（mp4）", "Screenshot（JPG）— 橫",
                    "Screenshot（JPG）— 直", "主題圖片", "Liveops", "主題影片", "Icon"]
# Notion toggle 標題跟 pptx_builder.SIZE_TAXONOMY 的素材類型 key 對照
SIZE_CATEGORY_MAP = {
    "Banner（JPG）": "Banner",
    "Video（mp4）": "Video",
    "Gif（JPG）": "Gif",
    "Gif（mp4）": "Gif",
    "Screenshot（JPG）— 橫": "Screenshot",
    "Screenshot（JPG）— 直": "Screenshot",
    "主題圖片（JPG）": "主題圖片",
    "Liveops（JPG）": "Liveops",
    "主題影片（mp4）": "主題影片",
    "Icon（JPG，<1MB）": "Icon",
}


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}


def _get_children(block_id, token):
    results = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = _session.get(f"{API}/blocks/{block_id}/children", headers=_headers(token), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return results


def _should_skip(block):
    text = _text(block).strip()
    return any(text.startswith(p) for p in SKIP_SUBTREE_PREFIXES)


def fetch_tree(block_id, token, _executor=None):
    """遞迴抓整棵區塊樹，每個 block dict 會多一個 "_children" key。

    同一層的子節點平行抓取（Notion API 是 I/O bound，序列抓十幾個 toggle 很容易在
    Render 免費方案上逾時），並跳過 SKIP_SUBTREE_PREFIXES 裡列的、我們用不到的子樹。
    """
    owns_executor = _executor is None
    executor = _executor or ThreadPoolExecutor(max_workers=4)
    try:
        children = _get_children(block_id, token)
        to_fetch = [b for b in children if b.get("has_children") and not _should_skip(b)]
        futures = {b["id"]: executor.submit(fetch_tree, b["id"], token, executor) for b in to_fetch}
        for b in children:
            if b["id"] in futures:
                b["_children"] = futures[b["id"]].result()
            else:
                b["_children"] = []
        return children
    finally:
        if owns_executor:
            executor.shutdown(wait=True)


def _rt_plain(rich_text):
    return "".join(rt.get("plain_text", "") for rt in rich_text or [])


def _text(block):
    t = block.get("type")
    obj = block.get(t, {}) if t else {}
    if "rich_text" in obj:
        return _rt_plain(obj["rich_text"])
    return ""


def _checked_todos(children):
    """toggle 的子區塊如果是一串 to_do，回傳打勾項目的文字。"""
    out = []
    for c in children:
        if c.get("type") == "to_do" and c["to_do"].get("checked"):
            label = _text(c).strip()
            # 「其他：」這種帶冒號的選項，勾了才有意義，這裡原樣保留給呼叫端判斷
            out.append(label)
    return out


def _find_toggle(blocks, title_prefix):
    for b in blocks:
        if b.get("type") == "toggle" and _text(b).strip().startswith(title_prefix):
            return b
    return None


def parse_meta(meta_blocks):
    meta = {}
    for field in ["遊戲", "投放媒體", "單支秒數上限", "是否做長短秒", "素材類型", "影像特殊需求", "音效特殊需求"]:
        tog = _find_toggle(meta_blocks, field)
        if tog:
            meta[field] = [v for v in _checked_todos(tog["_children"]) if not v.startswith("其他")]

    # 素材尺寸需求：外層 toggle 底下還有一層 toggle（優先對稿尺寸 / Banner / Video / ...）
    size_root = _find_toggle(meta_blocks, "素材尺寸需求")
    sizes = {}
    priority = []
    if size_root:
        for child in size_root["_children"]:
            if child.get("type") != "toggle":
                continue
            title = _text(child).strip()
            if title.startswith("優先對稿尺寸"):
                priority = _checked_todos(child["_children"])
            elif title.startswith("原始尺寸對照表"):
                continue
            else:
                key = SIZE_CATEGORY_MAP.get(title)
                if key:
                    checked = _checked_todos(child["_children"])
                    sizes.setdefault(key, [])
                    sizes[key] = sorted(set(sizes[key]) | set(checked))
    meta["素材尺寸"] = sizes
    meta["優先對稿尺寸"] = priority

    # 自由文字欄位：段落文字是「標籤：內容」
    for b in meta_blocks:
        if b.get("type") not in ("paragraph", "bulleted_list_item"):
            continue
        full = _text(b)
        for label in ["畫面風格", "配樂風格", "廣告TA", "廣告目的", "廣告鉤子"]:
            if full.startswith(label):
                _, _, val = full.partition("：")
                meta[label] = val.strip()
    return meta


def compute_asset_name(meta, title, today_str):
    games = meta.get("遊戲") or []
    game_part = "、".join(games)
    sizes = meta.get("素材尺寸") or {}
    type_parts = []
    if any(sizes.get(k) for k in ("Video",)):
        type_parts.append("video廣宣")
    if any(sizes.get(k) for k in ("Banner",)):
        type_parts.append("banner廣宣")
    if any(sizes.get(k) for k in ("Gif",)):
        type_parts.append("gif廣宣")
    type_part = "+".join(type_parts) if type_parts else ""
    parts = [today_str, game_part, type_part, title]
    return "_".join(p for p in parts if p)


def compute_total_count(meta):
    n_games = len(meta.get("遊戲") or [])
    n_duration = len(meta.get("是否做長短秒") or [])
    sizes = meta.get("素材尺寸") or {}
    n_sizes = sum(len(v) for v in sizes.values())
    total = n_games * n_duration * n_sizes
    note = f"{n_games}遊戲 × 長短秒{n_duration}版本 × {n_sizes}尺寸"
    return total, note


def parse_scenes(scene_blocks):
    scenes = []
    cur_scene = None
    cur_shot = None

    def flush_shot():
        if cur_shot is not None and cur_scene is not None:
            cur_scene["shots"].append(cur_shot)

    for b in scene_blocks:
        t = b.get("type")
        text = _text(b)

        m = re.match(r"^分鏡\s*(\d+)", text) if t == "heading_2" or t == "heading_3" else None
        if m:
            flush_shot()
            cur_shot = None
            cur_scene = {"id": int(m.group(1)), "layoutObjects": [], "music": "", "sfx": "", "note": "", "shots": []}
            scenes.append(cur_scene)
            continue

        if cur_scene is None:
            continue

        m = re.match(r"^鏡頭\s*(\d+)", text)
        if m:
            flush_shot()
            cur_shot = {"angle": "", "position": "", "action": "", "line": "", "seconds": "", "note": ""}
            continue

        if t == "toggle" and cur_shot is not None:
            title = text.strip()
            if title.startswith("角度/運鏡"):
                checked = [v for v in _checked_todos(b["_children"]) if not v.startswith("其他")]
                cur_shot["angle"] = "、".join(checked)
            elif title.startswith("鏡位"):
                checked = [v for v in _checked_todos(b["_children"]) if not v.startswith("其他")]
                cur_shot["position"] = "、".join(checked)
            continue

        if t in ("paragraph", "bulleted_list_item"):
            if text.startswith("場景/道具"):
                for child in b.get("_children", []):
                    child_text = _text(child)
                    label, sep, desc = child_text.partition(":")
                    if not sep:
                        label, sep, desc = child_text.partition("：")
                    cur_scene["layoutObjects"].append({"label": label.strip(), "desc": desc.strip() or child_text.strip()})
                continue
            for label, key, target in [
                ("音樂", "music", "scene"), ("音效", "sfx", "scene"), ("備註", "note", "scene"),
                ("動作描述", "action", "shot"), ("對白/字卡文案", "line", "shot"), ("秒數", "seconds", "shot"),
            ]:
                if text.startswith(label):
                    _, _, val = text.partition("：")
                    if target == "scene":
                        cur_scene[key] = val.strip()
                    elif cur_shot is not None:
                        cur_shot[key] = val.strip()
                    break
    flush_shot()
    return scenes


def parse_page(page_id, token, title=None, today_str=None):
    from datetime import date
    today_str = today_str or date.today().strftime("%Y%m%d")

    tree = fetch_tree(page_id, token)

    split_idx = None
    for i, b in enumerate(tree):
        if b.get("type") == "heading_1" and _text(b).strip() == "分鏡內容":
            split_idx = i
            break
    meta_blocks = tree[:split_idx] if split_idx is not None else tree
    scene_blocks = tree[split_idx + 1:] if split_idx is not None else []

    meta = parse_meta(meta_blocks)
    meta["素材名稱"] = compute_asset_name(meta, title or "", today_str)
    total, note = compute_total_count(meta)
    meta["總支數"] = str(total)
    meta["總支數備註"] = note

    scenes = parse_scenes(scene_blocks)
    return {"meta": meta, "scenes": scenes}


if __name__ == "__main__":
    import sys
    import json
    token = os.environ["NOTION_TOKEN"]
    page_id = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else ""
    data = parse_page(page_id, token, title=title)
    print(json.dumps(data, ensure_ascii=False, indent=2))
