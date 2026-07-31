# -*- coding: utf-8 -*-
"""反向流程：從上方「文字腳本」表格（純文字，同事直接打字，不一定填鏡位/角度/秒數），
自動展開/重建下方「分鏡內容」的勾選框跟文字欄位。

角度/運鏡、鏡位的勾選是用 angle_matcher.py 的關鍵字比對（同一份邏輯來源，不是另外用 LLM 猜）。
每個「鏡頭」是整段覆蓋重建：以上方表格那一列為準，重新判斷勾選、重新寫入動作/對白/秒數，
不管那個鏡頭原本有沒有手動填過。上方表格沒有的欄位（例如場景/道具、音樂、音效，表格裡本來就
沒有這幾欄）維持原樣，不會被清空。

同步規則：
- 上方表格新增的「分鏡」「鏡頭」→ 在下方對應位置插入新區塊
- 上方表格拿掉的「分鏡」「鏡頭」→ 下方對應區塊會被整段刪除
- 上方表格還在的「鏡頭」→ 整段覆蓋重建該鏡頭的勾選框跟文字欄位

順便會把「總秒數」那列重算（加總上方表格目前每一列的秒數），不用手動加、也不用另外按
「更新摘要」才會更新。
"""
import re
import requests

import angle_matcher
from notion_parser import _headers, _text, _rt_plain, API, fetch_tree
from summary import _find_first_table

CONTENT_HEADING = "分鏡內容"
KNOWN_TOP_LEVEL_TYPES = {
    "heading_1", "heading_2", "heading_3", "paragraph", "bulleted_list_item",
    "toggle", "divider", "quote", "callout", "table",
}


def _patch_block(block_id, payload, token):
    r = requests.patch(f"{API}/blocks/{block_id}", headers={**_headers(token), "Content-Type": "application/json"},
                        json=payload, timeout=30)
    r.raise_for_status()


def _append_children(parent_id, children, token, after=None):
    payload = {"children": children}
    if after:
        payload["after"] = after
    r = requests.patch(f"{API}/blocks/{parent_id}/children",
                        headers={**_headers(token), "Content-Type": "application/json"}, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["results"]


def _delete_block(block_id, token):
    try:
        r = requests.delete(f"{API}/blocks/{block_id}", headers=_headers(token), timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        pass  # 舊區塊刪不掉不影響這次同步的其他部分，最多是留著沒清乾淨


def _plain_rt(text, bold=False):
    node = {"type": "text", "text": {"content": text}}
    if bold:
        node["annotations"] = {"bold": True}
    return [node]


def _label_value_rt(label, value):
    rt = [{"type": "text", "text": {"content": f"{label}："}, "annotations": {"color": "yellow_background"}}]
    if value:
        rt.append({"type": "text", "text": {"content": value}})
    return rt


def _cell_rt(text):
    return [{"type": "text", "text": {"content": str(text)}}] if text else []


def _total_seconds_from_rows(rows):
    total = 0.0
    for r in rows:
        m = re.match(r"([\d.]+)", str(r.get("seconds") or "0"))
        if m:
            total += float(m.group(1))
    if total == int(total):
        return f"{int(total)}s"
    return f"{total}s"


def _sync_total_row(table, total_str, token):
    """把「總秒數」那列的秒數欄，換成用上方表格目前每一列秒數加總算出來的值——這樣直接在上方
    表格打字（不透過「更新摘要」按鈕）也不用自己手動加總、手動改這格。"""
    new_cells = [_cell_rt("總秒數"), _cell_rt(""), _cell_rt(total_str), _cell_rt(""), _cell_rt(""), _cell_rt("")]
    for row in table.get("_children", [])[1:]:
        cells = row.get("table_row", {}).get("cells", [])
        if cells and _rt_plain(cells[0]).strip() == "總秒數":
            _patch_block(row["id"], {"table_row": {"cells": new_cells}}, token)
            return
    _append_children(table["id"], [{"type": "table_row", "table_row": {"cells": new_cells}}], token)


def _parse_table_rows(table):
    """表格第一列是表頭，跳過；「總秒數」那列是彙總列，也跳過。"""
    all_rows = table.get("_children", [])
    out = []
    for row in all_rows[1:]:
        cells = row.get("table_row", {}).get("cells", [])
        vals = [_rt_plain(c) for c in cells]
        vals += [""] * (6 - len(vals))
        scene_id, shot_no, seconds, position_text, action, line = [v.strip() for v in vals[:6]]
        if not scene_id or scene_id == "總秒數":
            continue
        out.append({
            "scene_id": scene_id, "shot_no": shot_no, "seconds": seconds,
            "position_text": position_text, "action": action, "line": line,
        })
    return out


def _index_toggle(block):
    todo_ids = {}
    for c in block.get("_children", []):
        if c.get("type") == "to_do":
            todo_ids[_text(c).strip()] = c["id"]
    return {"id": block["id"], "todo_ids": todo_ids}


def _index_scenes(scene_blocks):
    scenes = {}
    cur = None
    cur_shot = None
    for b in scene_blocks:
        t = b.get("type")
        text = _text(b)

        m = re.match(r"^分鏡\s*(\d+)", text) if t in ("heading_2", "heading_3") else None
        if m:
            sid = m.group(1)
            cur = {"id": sid, "shots": {}, "all_ids": [b["id"]]}
            scenes[sid] = cur
            cur_shot = None
            continue

        if cur is None:
            continue
        if t not in KNOWN_TOP_LEVEL_TYPES:
            # 按鈕之類我們不認得的區塊：不算進這個分鏡的範圍，避免被誤判成「分鏡的一部分」
            # 而在整段刪除分鏡時，連按鈕一起刪掉
            continue
        cur["all_ids"].append(b["id"])

        m = re.match(r"^鏡頭\s*(\d+)", text)
        if m:
            cur_shot = {
                "marker_id": b["id"], "angle_toggle": None, "position_toggle": None,
                "action": None, "line": None, "seconds": None,
            }
            cur["shots"][m.group(1)] = cur_shot
            continue

        if cur_shot is None:
            continue

        if t == "toggle":
            title = text.strip()
            if title.startswith("角度/運鏡"):
                cur_shot["angle_toggle"] = _index_toggle(b)
            elif title.startswith("鏡位"):
                cur_shot["position_toggle"] = _index_toggle(b)
        elif t in ("paragraph", "bulleted_list_item"):
            # 範本裡這幾個欄位實際上是 bulleted_list_item（有項目符號），不是 paragraph，
            # 所以要記住這個區塊「原本的類型」，PATCH 時才不會送錯 key 被 Notion 判 400
            if text.startswith("動作描述"):
                cur_shot["action"] = {"id": b["id"], "type": t}
            elif text.startswith("對白/字卡文案"):
                cur_shot["line"] = {"id": b["id"], "type": t}
            elif text.startswith("秒數"):
                cur_shot["seconds"] = {"id": b["id"], "type": t}

    for sc in scenes.values():
        sc["last_id"] = sc["all_ids"][-1]
    return scenes


def _last_content_block_id(tree):
    for b in reversed(tree):
        if b.get("type") in KNOWN_TOP_LEVEL_TYPES:
            return b["id"]
    return tree[-1]["id"] if tree else None


def _new_shot_blocks(shot_no, row):
    marker = f"鏡頭 {shot_no}：" if shot_no == "1" else f"鏡頭 {shot_no}（沒有可刪除）："
    combined = f"{row['position_text']} {row['action']}"
    angle_val = angle_matcher.detect_angle(combined)
    pos_val = angle_matcher.detect_position(combined)

    angle_children = [
        {"type": "to_do", "to_do": {"rich_text": _plain_rt(opt), "checked": opt == angle_val}}
        for opt in angle_matcher.ANGLE_OPTIONS
    ] + [{"type": "to_do", "to_do": {"rich_text": _plain_rt("其他："), "checked": False}}]
    position_children = [
        {"type": "to_do", "to_do": {"rich_text": _plain_rt(opt), "checked": opt == pos_val}}
        for opt in angle_matcher.POSITION_OPTIONS
    ]

    return [
        {"type": "paragraph", "paragraph": {"rich_text": _plain_rt(marker, bold=True)}},
        {"type": "toggle", "toggle": {"rich_text": _plain_rt("角度/運鏡"), "color": "yellow_background"},
         "children": angle_children},
        {"type": "toggle", "toggle": {"rich_text": _plain_rt("鏡位"), "color": "yellow_background"},
         "children": position_children},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _label_value_rt("動作描述", row["action"])}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _label_value_rt("對白/字卡文案", row["line"])}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _label_value_rt("秒數", row["seconds"])}},
    ]


def _new_scene_blocks(scene_id, srows):
    blocks = [
        {"type": "heading_2", "heading_2": {"rich_text": _plain_rt(f"分鏡 {scene_id}")}},
        {"type": "bulleted_list_item", "bulleted_list_item": {
            "rich_text": _label_value_rt("場景/道具（跟前一鏡相同可直接寫「同前一cut」）", "")}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _label_value_rt("音樂", "")}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _label_value_rt("音效", "")}},
    ]
    for i, row in enumerate(srows, start=1):
        blocks.extend(_new_shot_blocks(row["shot_no"] or str(i), row))
    blocks.append({"type": "divider", "divider": {}})
    return blocks


def _sync_toggle(toggle_idx, options, checked_value, token):
    for opt in options:
        if opt not in toggle_idx["todo_ids"]:
            appended = _append_children(
                toggle_idx["id"],
                [{"type": "to_do", "to_do": {"rich_text": _plain_rt(opt), "checked": opt == checked_value}}],
                token,
            )
            toggle_idx["todo_ids"][opt] = appended[0]["id"]
        else:
            _patch_block(toggle_idx["todo_ids"][opt], {"to_do": {"checked": opt == checked_value}}, token)


def _patch_field(field, label, value, token):
    _patch_block(field["id"], {field["type"]: {"rich_text": _label_value_rt(label, value)}}, token)


def _sync_existing_scene(page_id, scene_idx, srows, token):
    used = set()
    last_id = scene_idx["last_id"]
    for i, row in enumerate(srows, start=1):
        shot_no = row["shot_no"] or str(i)
        used.add(shot_no)
        combined = f"{row['position_text']} {row['action']}"
        angle_val = angle_matcher.detect_angle(combined)
        pos_val = angle_matcher.detect_position(combined)

        if shot_no in scene_idx["shots"]:
            shot = scene_idx["shots"][shot_no]
            _sync_toggle(shot["angle_toggle"], angle_matcher.ANGLE_OPTIONS, angle_val, token)
            _sync_toggle(shot["position_toggle"], angle_matcher.POSITION_OPTIONS, pos_val, token)
            _patch_field(shot["action"], "動作描述", row["action"], token)
            _patch_field(shot["line"], "對白/字卡文案", row["line"], token)
            _patch_field(shot["seconds"], "秒數", row["seconds"], token)
            last_id = shot["seconds"]["id"]  # 這個鏡頭區塊裡最後一塊，後面如果要插入新鏡頭要接在這之後
        else:
            appended = _append_children(page_id, _new_shot_blocks(shot_no, row), token, after=last_id)
            last_id = appended[-1]["id"]

    for shot_no, shot in scene_idx["shots"].items():
        if shot_no in used:
            continue
        for bid in [shot["marker_id"], shot["angle_toggle"]["id"], shot["position_toggle"]["id"],
                    shot["action"]["id"], shot["line"]["id"], shot["seconds"]["id"]]:
            _delete_block(bid, token)


def _delete_scene(scene_idx, token):
    for bid in scene_idx["all_ids"]:
        _delete_block(bid, token)


def expand_to_detail(page_id, token):
    tree = fetch_tree(page_id, token)

    table = _find_first_table(tree)
    if table is None:
        raise RuntimeError("頁面上找不到「文字腳本」表格，請確認上方摘要表格還在")
    rows = _parse_table_rows(table)
    if not rows:
        raise RuntimeError("「文字腳本」表格沒有資料列，先在上面打幾行文字再產生分鏡內容")

    scene_order = []
    scene_rows = {}
    for r in rows:
        if r["scene_id"] not in scene_rows:
            scene_rows[r["scene_id"]] = []
            scene_order.append(r["scene_id"])
        scene_rows[r["scene_id"]].append(r)

    split_idx = None
    for i, b in enumerate(tree):
        if b.get("type") == "heading_1" and _text(b).strip() == CONTENT_HEADING:
            split_idx = i
            break
    if split_idx is None:
        raise RuntimeError(f"頁面上找不到「{CONTENT_HEADING}」標題，無法定位要寫入的位置")

    scene_blocks = tree[split_idx + 1:]
    existing = _index_scenes(scene_blocks)

    append_anchor = _last_content_block_id(tree)
    for sid in scene_order:
        srows = scene_rows[sid]
        if sid in existing:
            _sync_existing_scene(page_id, existing[sid], srows, token)
        else:
            appended = _append_children(page_id, _new_scene_blocks(sid, srows), token, after=append_anchor)
            append_anchor = appended[-1]["id"]

    for sid, scene_idx in existing.items():
        if sid not in scene_rows:
            _delete_scene(scene_idx, token)

    _sync_total_row(table, _total_seconds_from_rows(rows), token)
