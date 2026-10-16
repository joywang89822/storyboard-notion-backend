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


def _image_url(block):
    """從一個 Notion "image" 區塊拿出可以直接下載的網址。同事直接把圖片貼到頁面裡
    （拖曳上傳或貼上網址皆可）就會產生這種區塊。"""
    img = block.get("image", {})
    if img.get("type") == "external":
        return img.get("external", {}).get("url")
    if img.get("type") == "file":
        return img.get("file", {}).get("url")
    return None


def _should_skip(block):
    text = _text(block).strip()
    return any(text.startswith(p) for p in SKIP_SUBTREE_PREFIXES)


def fetch_tree(block_id, token):
    """遞迴抓整棵區塊樹，每個 block dict 會多一個 "_children" key。

    同一層的子節點平行抓取（Notion API 是 I/O bound，序列抓十幾個 toggle 很容易在
    Render 免費方案上逾時），並跳過 SKIP_SUBTREE_PREFIXES 裡列的、我們用不到的子樹。

    注意：每一層遞迴都開自己獨立的 ThreadPoolExecutor，用完就關掉，不會跨層共用同一個
    池子——共用池子 + 遞迴呼叫時阻塞等待子任務結果，會有 thread pool 死鎖的風險
    （worker 全部卡在互相等待，永遠不會有人真的去執行排隊中的子任務）。
    """
    children = _get_children(block_id, token)
    to_fetch = [b for b in children if b.get("has_children") and not _should_skip(b)]
    if to_fetch:
        with ThreadPoolExecutor(max_workers=min(len(to_fetch), 8)) as executor:
            results = list(executor.map(lambda b: fetch_tree(b["id"], token), to_fetch))
        fetched = dict(zip((b["id"] for b in to_fetch), results))
    else:
        fetched = {}
    for b in children:
        b["_children"] = fetched.get(b["id"], [])
    return children


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


def _find_heading(blocks, title_prefix):
    """新版排版把「素材尺寸需求」這種區塊改成 toggle heading（heading_2 帶 is_toggleable），
    不是 toggle 區塊，type 會是 heading_1/2/3。"""
    for b in blocks:
        if b.get("type") in ("heading_1", "heading_2", "heading_3") and _text(b).strip().startswith(title_prefix):
            return b
    return None


def _column_list_label(block):
    """columns 區塊第一欄放的是欄位名稱（例如「遊戲」「角度/運鏡」），取出它的純文字。"""
    cols = block.get("_children", [])
    if not cols:
        return ""
    return "".join(_text(c) for c in cols[0].get("_children", [])).strip()


def _find_column_field(blocks, label_prefix):
    """新版排版：勾選欄位改成 columns 並排（不是收合的 toggle），第一欄是欄位名稱，
    其餘每一欄各放一個 to_do 選項。"""
    for b in blocks:
        if b.get("type") == "column_list" and _column_list_label(b).startswith(label_prefix):
            return b
    return None


def _checked_todos_from_columns(column_list_block):
    out = []
    for col in column_list_block.get("_children", [])[1:]:
        for c in col.get("_children", []):
            if c.get("type") == "to_do" and c["to_do"].get("checked"):
                out.append(_text(c).strip())
    return out


def _field_checked_options(blocks, label):
    """同一個欄位新舊兩種排版都要看得懂：新版是 columns 並排勾選，舊版是 toggle 收合勾選清單。"""
    col = _find_column_field(blocks, label)
    if col is not None:
        return [v for v in _checked_todos_from_columns(col) if not v.startswith("其他")]
    tog = _find_toggle(blocks, label)
    if tog is not None:
        return [v for v in _checked_todos(tog["_children"]) if not v.startswith("其他")]
    return []


def parse_meta(meta_blocks):
    meta = {}
    for field in ["遊戲", "投放媒體", "單支秒數上限", "是否做長短秒", "素材類型", "影像特殊需求", "音效特殊需求"]:
        meta[field] = _field_checked_options(meta_blocks, field)

    # 素材尺寸需求：舊版是外層 toggle 底下再一層 toggle（優先對稿尺寸 / Banner / Video / ...），
    # 新版是 toggle heading 底下一組 columns（每個尺寸類別一個 columns 區塊）。
    size_root = _find_toggle(meta_blocks, "素材尺寸需求") or _find_heading(meta_blocks, "素材尺寸需求")
    sizes = {}
    priority = []
    if size_root:
        children = size_root.get("_children", [])
        priority = _field_checked_options(children, "優先對稿尺寸")
        for title, key in SIZE_CATEGORY_MAP.items():
            checked = _field_checked_options(children, title)
            if checked:
                sizes.setdefault(key, [])
                sizes[key] = sorted(set(sizes[key]) | set(checked))
    meta["素材尺寸"] = sizes
    meta["優先對稿尺寸"] = priority

    # 自由文字欄位：段落文字是「標籤：內容」（label 比對時忽略「廣告 TA」這種標籤中間多打的空格）
    for b in meta_blocks:
        if b.get("type") not in ("paragraph", "bulleted_list_item"):
            continue
        full = _text(b)
        full_nospace = full.replace(" ", "")
        for label in ["畫面風格", "配樂風格", "廣告TA", "廣告目的", "廣告鉤子"]:
            if full_nospace.startswith(label):
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

        if t == "image":
            url = _image_url(b)
            if url:
                if cur_shot is not None:
                    cur_shot["image_url"] = url
                else:
                    cur_scene["image_url"] = url
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

        if t == "column_list" and cur_shot is not None:
            label = _column_list_label(b)
            checked = [v for v in _checked_todos_from_columns(b) if not v.startswith("其他")]
            if label.startswith("角度/運鏡"):
                cur_shot["angle"] = "、".join(checked)
            elif label.startswith("鏡位"):
                cur_shot["position"] = "、".join(checked)
            continue

        if t == "table" and cur_shot is not None:
            # 新版排版：動作描述/對白/字卡文案/秒數合併成一個表格（表頭列 + 一列資料）
            rows = b.get("_children", [])
            if len(rows) >= 2:
                cells = rows[1].get("table_row", {}).get("cells", [])
                vals = [_rt_plain(c) for c in cells]
                vals += [""] * (3 - len(vals))
                cur_shot["action"], cur_shot["line"], cur_shot["seconds"] = [v.strip() for v in vals[:3]]
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


def _flatten_meta_blocks(blocks):
    """新版排版把「素材基本資訊」整個包成一個 toggle heading，欄位（columns/素材尺寸需求...）
    變成它的巢狀 children，不再跟舊版一樣是同一層的 sibling。遞迴展開成扁平清單，
    上面那些 _find_* 欄位搜尋函式才找得到。只展開「容器類」外層（heading／toggle），
    column_list/table 內部結構固定，交給對應的 _find_* 函式自己去讀 children，不用打散。"""
    out = []
    for b in blocks:
        out.append(b)
        if b.get("type") in ("heading_1", "heading_2", "heading_3", "toggle"):
            out.extend(_flatten_meta_blocks(b.get("_children", [])))
    return out


def fetch_page_title(page_id, token):
    """直接跟 Notion 要這個頁面自己的標題，不依賴呼叫端另外傳。"""
    r = _session.get(f"{API}/pages/{page_id}", headers=_headers(token), timeout=30)
    r.raise_for_status()
    props = r.json().get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            return _rt_plain(prop.get("title", []))
    return ""


def parse_page(page_id, token, title=None, today_str=None, source="table"):
    """source="table"（產 PPTX 用）：以最上方文字腳本表格為準，下方完整版只當補充，並自動推測角度/鏡位；
    頁面沒有文字腳本表格時自動退回讀下方完整版。
    source="detail"（「更新摘要」用）：只讀下方完整版，維持舊行為。"""
    from datetime import date
    today_str = today_str or date.today().strftime("%Y%m%d")
    if title is None:
        title = fetch_page_title(page_id, token)

    tree = fetch_tree(page_id, token)

    split_idx = None
    for i, b in enumerate(tree):
        if b.get("type") == "heading_1" and _text(b).strip() == "分鏡內容":
            split_idx = i
            break
    meta_blocks = _flatten_meta_blocks(tree[:split_idx] if split_idx is not None else tree)
    scene_blocks = tree[split_idx + 1:] if split_idx is not None else []

    meta = parse_meta(meta_blocks)
    meta["素材名稱"] = compute_asset_name(meta, title or "", today_str)
    total, note = compute_total_count(meta)
    meta["總支數"] = str(total)
    meta["總支數備註"] = note

    scenes = parse_scenes(scene_blocks)
    data = {"meta": meta, "scenes": scenes}
    if source == "table":
        import script_table
        table = script_table.find_script_table(tree[:split_idx] if split_idx is not None else tree)
        rows, cmap = script_table.read_rows(table) if table else ([], {})
        if rows:
            data["scenes"] = script_table.build_scenes(rows, scenes)
            data["_script_table"] = (table, cmap)
        script_table.enrich(data["scenes"], meta.get("影像特殊需求") or [])
        # 配樂通常整支一樣：分鏡沒另外寫音樂時，直接用基本資訊的「配樂風格」
        for sc in data["scenes"]:
            sc["music"] = sc.get("music") or meta.get("配樂風格", "")
    return data


if __name__ == "__main__":
    import sys
    import json
    token = os.environ["NOTION_TOKEN"]
    page_id = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else ""
    data = parse_page(page_id, token, title=title)
    data.pop("_script_table", None)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
