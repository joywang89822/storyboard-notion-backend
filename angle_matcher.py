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


def _load_hints():
    """「(推測)」類的列：動作描述沒寫明角度/鏡位時，從畫面內容推測。
    回傳 [(角度或鏡位, 適用風格 or "", 選項, [關鍵字...]), ...]。
    同一個鏡頭會依同事的習慣而不同（2D 遊戲畫面的跟注/All in 是特寫 UI，3D 的推籌碼是中景），
    所以規則可以限定「適用風格」，空白 = 不分風格的通用規則。"""
    hints = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            category = (row.get("分類（角度/鏡位）") or "").strip()
            if not category.endswith("(推測)"):
                continue
            target = (row.get("標準選項") or "").strip()
            words = [s.strip() for s in (row.get("同義詞（腳本/口語常見寫法）") or "").split("、") if s.strip()]
            if target and words:
                hints.append((category.replace("(推測)", ""), (row.get("適用風格") or "").strip(), target, words))
    return hints


_HINTS = _load_hints()

DEFAULT_ANGLE = "平視"
DEFAULT_POSITION = "中景"
STYLE_KEYS = ["2D", "3D", "真人"]


def _hint(text, kind, style):
    """先看這個風格專屬的規則，沒中再看通用規則；同一組規則裡取動作描述中「最先出現」的詞。"""
    lowered = text.lower()
    for scope in ([style] if style else []) + [""]:
        best = None
        for k, st, target, words in _HINTS:
            if k != kind or st != scope:
                continue
            for w in words:
                pos = lowered.find(w.lower()) if w.isascii() else text.find(w)
                if pos != -1 and (best is None or pos < best[0]):
                    best = (pos, target)
        if best:
            return best[1]
    return None


def style_of(styles):
    """meta.影像特殊需求（例如 ["3D"]、["真人", "2D"]）→ 推測規則要用的風格。真人+2D 合成以真人為主。"""
    styles = styles or []
    for k in ["真人", "3D", "2D"]:
        if k in styles:
            return k
    return ""


def infer_shot(text, asset_position=None, style=""):
    """沒有人工指定時，推測一個鏡頭的 (角度, 鏡位, 依據)。永遠回傳值，不會留空。

    順序：動作描述裡明寫的詞（俯視/特寫…）> 內容推測（依風格，例如 2D 跟注→特寫、3D 推籌碼→中景）
         > 配到的參考素材標註的鏡位 > 預設（平視、中景）
    """
    text = text or ""
    angle = detect_angle(text)
    position = detect_position(text)
    source = "明寫" if (angle or position) else ""
    if angle == "特寫推進" and not position:
        position = "特寫"
    if not position:
        position = _hint(text, "鏡位", style)
        if position:
            source = source or "內容推測"
    if not angle:
        angle = _hint(text, "角度", style)
    if not position and asset_position in POSITION_OPTIONS:
        position, source = asset_position, source or "參考素材"
    return angle or DEFAULT_ANGLE, position or DEFAULT_POSITION, source or "預設"


def parse_cell(text):
    """表格「鏡位」欄的人工填寫（例如「中景/俯視」「平視・全景」）→ (角度, 鏡位)，沒寫到的回傳 None。"""
    if not text:
        return None, None
    return detect_angle(text), detect_position(text)


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
