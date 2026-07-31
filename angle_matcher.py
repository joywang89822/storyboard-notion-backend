# -*- coding: utf-8 -*-
"""從「動作描述」（或使用者自己填的「鏡位」欄文字）判斷要勾選的「角度/運鏡」「鏡位」選項。

關鍵字表放在 angle_keywords.csv（格式跟 reference_assets/關鍵字對照表.csv 一樣），同事要新增/
調整判斷用的口語寫法，直接改那份 CSV 就好，不用改程式。

消歧規則：「特寫」單獨出現時判斷成鏡位的「特寫」；如果同時出現「推進」（例如「特寫推進」），
則視為角度/運鏡的「特寫推進」，這時不會同時勾選鏡位的「特寫」，避免兩邊都勾、意思重複。
"""
import csv
import os

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "angle_keywords.csv")

ANGLE_OPTIONS = ["平視", "俯視", "仰視", "特寫推進"]
POSITION_OPTIONS = ["全景", "近景", "中景", "特寫"]


def _load():
    angle_map = []     # [(關鍵字, 標準選項), ...]，長字串優先比對，避免短詞誤判蓋掉長詞
    position_map = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            category = (row.get("分類（角度/鏡位）") or "").strip()
            target = (row.get("標準選項") or "").strip()
            synonyms = row.get("同義詞（腳本/口語常見寫法）", "") or ""
            if not target:
                continue
            bucket = {"角度": angle_map, "鏡位": position_map}.get(category)
            if bucket is None:
                continue
            for syn in synonyms.split("、"):
                syn = syn.strip()
                if syn:
                    bucket.append((syn, target))
    angle_map.sort(key=lambda kv: -len(kv[0]))
    position_map.sort(key=lambda kv: -len(kv[0]))
    return angle_map, position_map


_ANGLE_MAP, _POSITION_MAP = _load()


def _find(text, keyword_map):
    lowered = text.lower()
    for syn, target in keyword_map:
        haystack = lowered if syn.isascii() else text
        needle = syn.lower() if syn.isascii() else syn
        if needle in haystack:
            return target
    return None


def detect_angle(text):
    """回傳 ANGLE_OPTIONS 其中一個，或 None（沒偵測到關鍵字，留給使用者手動勾）。"""
    if not text:
        return None
    return _find(text, _ANGLE_MAP)


def detect_position(text):
    """回傳 POSITION_OPTIONS 其中一個，或 None。"""
    if not text:
        return None
    has_push = "推進" in text
    filtered = [(syn, target) for syn, target in _POSITION_MAP if not (target == "特寫" and syn == "特寫" and has_push)]
    return _find(text, filtered)
