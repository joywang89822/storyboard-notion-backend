# -*- coding: utf-8 -*-
"""文字腳本表格「場景/道具」欄：寫代號就好，產 PPT 時展開成完整說明＋參考路徑。

代號表在 scene_props.csv（從對稿區過去的分鏡腳本整理出來的常用牌桌/撲克牌/背景/版面），
要新增常用道具直接加一列，不用改程式。

寫法：用「、」或換行分開，例如「3D藍桌、寫實牌、籌碼堆」。
- 代號後面可以接「：補充」，例如「3D藍桌：改紅色絨布」→ 說明後面會加上補充
- 認不得的字照原樣放進 PPT（「牌桌：自訂說明」這種舊寫法也照用）
"""
import csv
import os
import re

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_props.csv")
SAME_AS_PREV = "同前一cut"
DEFAULTS = {  # 第一個分鏡沒寫時，依影像風格先帶的預設
    "2D": "遊戲牌桌",
    "3D": "3D藍桌、寫實牌、籌碼堆",
    "真人": "",
}


def _load():
    rows, lookup = [], {}
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = (r.get("代號") or "").strip()
            if not code:
                continue
            rows.append(r)
            for name in [code] + (r.get("同義詞") or "").split("、"):
                name = name.strip()
                if name:
                    lookup.setdefault(name.lower(), r)
    return rows, lookup


_ROWS, _LOOKUP = _load()


def split_tokens(text):
    return [t.strip() for t in re.split(r"[、\n,，]", text or "") if t.strip()]


def expand(text):
    """「3D藍桌、寫實牌：撲克牌要大」→ [{"label", "desc"}, ...]（PPT 排版物件表格的列）"""
    out = []
    for tok in split_tokens(text):
        m = re.match(r"([^：:]*)([：:])(.*)", tok, re.S)
        head, sep, extra = m.groups() if m else (tok, "", "")
        row = _LOOKUP.get(head.strip().lower())
        if row:
            desc = row["說明"] + (f"；{extra.strip()}" if extra.strip() else "")
            if row.get("參考路徑"):
                desc += f"\n參考：{row['參考路徑']}"
            out.append({"label": row["類別"], "desc": desc})
        elif sep:
            out.append({"label": head.strip(), "desc": extra.strip()})
        else:
            out.append({"label": "場景/道具", "desc": tok})
    return out


def detect_ending(text):
    """動作描述裡有片尾（中撲jingle 等）時回傳那個代號，讓片尾分鏡不會被標成「同前一cut」。"""
    lowered = (text or "").lower()
    for r in _ROWS:
        if r["類別"] != "片尾":
            continue
        for name in [r["代號"]] + (r.get("同義詞") or "").split("、"):
            name = name.strip().lower()
            if len(name) >= 2 and name in lowered:
                return r["代號"]
    return None


def codes_by_category():
    """給說明文件/範本用：{類別: [(代號, 適用風格, 說明), ...]}"""
    out = {}
    for r in _ROWS:
        out.setdefault(r["類別"], []).append((r["代號"], r.get("適用風格", ""), r["說明"]))
    return out
