# -*- coding: utf-8 -*-
"""「只寫一次」流程：以頁面最上方的「文字腳本」表格為準，直接產出 PPTX 要的 scenes。

- 表格欄位靠表頭名稱辨識（分鏡/鏡頭/秒數/鏡位/動作/對白…），之後在表格多加
  「角度」「場景/道具」「音樂」「音效」「備註」欄也讀得到；表頭認不得時退回舊的固定欄位順序
- 下方「分鏡內容」完整版變成選填：有填的場景/道具、音樂、音效、貼的圖、手動勾的角度/鏡位會併進來
- 角度/鏡位：表格「鏡位」欄有人工寫的 > 下方完整版有勾的 > angle_matcher.infer_shot 自動推測
- 自動推測的結果會寫回表格「鏡位」欄，加上「(自動)」標記：看得到判斷結果，覺得不對直接改那格
  （拿掉「(自動)」就會被當成人工指定，之後不再覆蓋）
"""
import re

import angle_matcher
import scene_props
from asset_matcher import match_asset
from notion_parser import _rt_plain

AUTO_MARK = "(自動)"
HEADER_ALIASES = {
    "scene": ["分鏡"],
    "shot": ["鏡頭"],
    "seconds": ["秒數"],
    "position": ["鏡位", "角度/鏡位", "鏡位/角度"],
    "angle": ["角度", "角度/運鏡", "運鏡"],
    "action": ["動作", "動作描述"],
    "line": ["對白/文案", "對白/字卡文案", "對白", "文案", "字卡"],
    "layout": ["場景/道具", "場景", "道具"],
    "music": ["音樂"],
    "sfx": ["音效"],
    "note": ["備註"],
}
LEGACY_ORDER = ["scene", "shot", "seconds", "position", "action", "line"]


def find_script_table(top_blocks):
    """頁面上第一個表頭有「動作」的表格（就是最上方的文字腳本）。"""
    for b in top_blocks:
        if b.get("type") != "table":
            continue
        rows = b.get("_children", [])
        if rows and any("動作" in _rt_plain(c) for c in rows[0].get("table_row", {}).get("cells", [])):
            return b
    return None


def _column_map(header_cells):
    names = [_rt_plain(c).strip() for c in header_cells]
    cmap = {}
    for key, aliases in HEADER_ALIASES.items():
        for i, n in enumerate(names):
            if i not in cmap.values() and n in aliases:
                cmap[key] = i
                break
    if not {"action", "scene"} <= cmap.keys():
        cmap = {k: i for i, k in enumerate(LEGACY_ORDER)}
    return cmap


def read_rows(table):
    """回傳 [{row_id, cells(原始 rich_text), 各欄位文字...}]，跳過表頭與「總秒數」列。
    分鏡欄留空的列視為延續上一個分鏡。"""
    rows = table.get("_children", [])
    if not rows:
        return [], {}
    cmap = _column_map(rows[0].get("table_row", {}).get("cells", []))
    out, last_scene = [], None
    for row in rows[1:]:
        cells = row.get("table_row", {}).get("cells", [])
        get = lambda k: _rt_plain(cells[cmap[k]]).strip() if k in cmap and cmap[k] < len(cells) else ""
        scene = get("scene")
        if scene.startswith("總秒數"):
            continue
        if not any(get(k) for k in ("action", "line", "seconds")):
            continue
        if not scene and out and not any(get(k) for k in ("shot", "action", "seconds")):
            out[-1]["line"] = (out[-1]["line"] + "\n" + get("line")).strip()  # 只有對白的列 = 上一句的延續
            continue
        scene = scene or last_scene
        if not scene:
            continue
        last_scene = scene
        out.append({"row_id": row.get("id"), "cells": cells, **{k: get(k) for k in HEADER_ALIASES}, "scene": scene})
    return out, cmap


def _scene_id(s):
    m = re.match(r"\d+", s)
    return int(m.group()) if m else s


def build_scenes(rows, detail_scenes=None):
    """表格列 → scenes。detail_scenes 是下方完整版解析結果（可為空），用來補表格沒有的資訊。"""
    detail = {d["id"]: d for d in (detail_scenes or [])}
    scenes, by_id = [], {}
    for r in rows:
        sid = _scene_id(r["scene"])
        layout_text = "" if AUTO_MARK in r["layout"] else r["layout"]  # (自動) 的格子每次重新判斷
        if sid not in by_id:
            d = detail.get(sid, {})
            sc = {"id": sid, "layoutObjects": scene_props.expand(layout_text) if layout_text else d.get("layoutObjects", []),
                  "music": r["music"] or d.get("music", ""), "sfx": r["sfx"] or d.get("sfx", ""),
                  "note": d.get("note", ""), "shots": [], "_first_row_id": r["row_id"]}
            if d.get("image_url"):
                sc["image_url"] = d["image_url"]
            by_id[sid] = sc
            scenes.append(sc)
        elif layout_text:  # 同一分鏡後面鏡頭寫的道具也收進來
            sc = by_id[sid]
            sc["layoutObjects"] += [o for o in scene_props.expand(layout_text) if o not in sc["layoutObjects"]]
        sc = by_id[sid]
        if r["sfx"] and r["sfx"] not in sc["sfx"]:  # 同一分鏡後面鏡頭的音效也要收進來
            sc["sfx"] = "；".join(x for x in [sc["sfx"], r["sfx"]] if x)
        d_shots = detail.get(sid, {}).get("shots", [])
        d_shot = d_shots[len(sc["shots"])] if len(sc["shots"]) < len(d_shots) else {}

        cell = r["position"]
        explicit = cell and AUTO_MARK not in cell
        ang, pos = angle_matcher.parse_cell(cell) if explicit else (None, None)
        if r["angle"]:
            ang = angle_matcher.detect_angle(r["angle"]) or r["angle"]
        shot = {
            "action": r["action"], "line": r["line"], "seconds": r["seconds"],
            "angle": ang or d_shot.get("angle", ""), "position": pos or d_shot.get("position", ""),
            "note": "；".join(x for x in [r["note"], d_shot.get("note", "")] if x),
            "_row_id": r["row_id"], "_explicit": bool(explicit),
        }
        if d_shot.get("image_url"):
            shot["image_url"] = d_shot["image_url"]
        sc["shots"].append(shot)
    return scenes


def enrich(scenes, styles, games=None):
    """補齊每個鏡頭的角度/鏡位，並預先配好參考素材（images.py 會直接用 _asset_row，不用再配一次）。"""
    style = angle_matcher.style_of(styles)
    for i, sc in enumerate(scenes):
        if not sc.get("layoutObjects"):
            # 場景/道具沒寫：片尾分鏡帶片尾代號；第一個分鏡依風格帶預設（寫回表格標 (自動)）；其他沿用前一個
            actions = " ".join(sh.get("action", "") for sh in sc["shots"])
            auto = scene_props.detect_ending(actions) or (scene_props.DEFAULTS.get(style, "") if i == 0 else "")
            if auto:
                sc["layoutObjects"] = scene_props.expand(auto)
                sc["_layout_auto"] = auto
            elif i > 0:
                sc["layoutObjects"] = [{"label": "場景/道具", "desc": scene_props.SAME_AS_PREV}]
        for sh in sc["shots"]:
            text = f"{sh.get('action', '')} {sh.get('line', '')}"
            if not sh.get("image_url"):
                row, note = match_asset(text, styles, games)
                sh["_asset_row"], sh["_asset_note"] = row, note
            if sh.get("angle") and sh.get("position"):
                continue
            ang, pos, src = angle_matcher.infer_shot(sh.get("action", ""), (sh.get("_asset_row") or {}).get("鏡位"), style)
            sh["angle"] = sh.get("angle") or ang
            sh["position"] = sh.get("position") or pos
            sh["_inferred"] = src
    return scenes


def _writable_rt(rich_text):
    """GET 回來的 rich_text 轉成 PATCH 收得了的格式（保留粗體/顏色等樣式）。"""
    out = []
    for rt in rich_text or []:
        if rt.get("type") == "text":
            node = {"type": "text", "text": {"content": rt["text"]["content"], "link": rt["text"].get("link")}}
        else:
            node = {"type": "text", "text": {"content": rt.get("plain_text", "")}}
        if rt.get("annotations"):
            node["annotations"] = rt["annotations"]
        out.append(node)
    return out


def write_back(table, cmap, scenes, patch_block):
    """把自動判斷的結果寫回表格（灰字、標「(自動)」）：
    - 「鏡位」欄：角度・鏡位
    - 「場景/道具」欄：第一個分鏡的風格預設、片尾分鏡的片尾代號
    人工填過的格子不動。patch_block(block_id, payload) 由呼叫端提供（方便離線測試）。回傳改了幾格。"""
    wanted = {}  # row_id -> {col: value}
    for sc in scenes:
        if sc.get("_layout_auto") and "layout" in cmap and sc.get("_first_row_id"):
            wanted.setdefault(sc["_first_row_id"], {})[cmap["layout"]] = f"{sc['_layout_auto']} {AUTO_MARK}"
        for sh in sc["shots"]:
            if "position" in cmap and not sh.get("_explicit") and sh.get("_row_id"):
                wanted.setdefault(sh["_row_id"], {})[cmap["position"]] = f"{sh['angle']}・{sh['position']} {AUTO_MARK}"
    n = 0
    for row in table.get("_children", []):
        changes = wanted.get(row.get("id"))
        if not changes:
            continue
        old = row["table_row"]["cells"]
        changes = {c: v for c, v in changes.items() if c < len(old) and _rt_plain(old[c]).strip() != v}
        if not changes:
            continue
        cells = [_writable_rt(c) for c in old]
        for c, v in changes.items():
            cells[c] = [{"type": "text", "text": {"content": v}, "annotations": {"color": "gray"}}]
        patch_block(row["id"], {"table_row": {"cells": cells}})
        n += len(changes)
    return n
