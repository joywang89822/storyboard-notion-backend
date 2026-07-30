# -*- coding: utf-8 -*-
"""從「參考素材資料庫」自動比對挑圖，取代人工一張張找截圖。

比對規則照 reference_assets/_使用說明.md：
- 用關鍵字對照表把腳本裡的口語寫法轉成標準 subject tag，precise 比對，不做模糊字串比對
- 動作描述裡如果講明是誰（主角/對手/左玩家/右玩家），比對時要連「視角」一起篩
- style 不符時視同沒有對應素材（品牌片尾類例外，見 STYLE_EXEMPT_ASSET_TYPES）
- 找到多筆符合時不會自己猜，全部列出來、挑第一筆用，但在該鏡頭的 note 標記「有多筆候選」
- 完全沒有符合的素材時，明確標記「資料庫沒有對應素材」，不會用相近的湊數
"""
import csv
import os

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference_assets")
INDEX_CSV = os.path.join(BASE_DIR, "參考素材索引.csv")
KEYWORD_CSV = os.path.join(BASE_DIR, "關鍵字對照表.csv")

VIEWPOINTS = ["主角", "對手", "左玩家", "右玩家"]
STYLE_EXEMPT_ASSET_TYPES = {"片尾"}  # 品牌片尾類（中撲jingle/印撲icon）不比對 style
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def _load_keyword_map():
    mapping = []  # [(synonym, standard_tag), ...]，比對時用長字串優先，避免短詞誤判蓋掉長詞
    with open(KEYWORD_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            synonyms_field = row.get("同義詞（腳本/口語常見寫法）", "") or ""
            tag = (row.get("標準tag（填進索引表 subject 欄的字）", "") or "").strip()
            if not tag:
                continue
            for syn in synonyms_field.split("、"):
                syn = syn.strip()
                if syn:
                    mapping.append((syn, tag))
    mapping.sort(key=lambda kv: -len(kv[0]))
    return mapping


def _load_index():
    with open(INDEX_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


_KEYWORD_MAP = _load_keyword_map()
_INDEX = _load_index()


def find_subjects(text):
    """在文字裡找出提到的標準 subject tag（可能不只一個）。英文同義詞（如 ALL IN）不分大小寫。"""
    lowered = text.lower()
    found = []
    for syn, tag in _KEYWORD_MAP:
        haystack = lowered if syn.isascii() else text
        needle = syn.lower() if syn.isascii() else syn
        if needle in haystack and tag not in found:
            found.append(tag)
    return found


def detect_viewpoint(text):
    for vp in VIEWPOINTS:
        if vp in text:
            return vp
    return None


def match_asset(text, styles):
    """styles: 這次腳本的影像風格清單（來自 meta.影像特殊需求，例如 ["3D"]），空清單代表不限風格。

    回傳 (asset_row_or_None, note_or_None)。
    """
    subjects = find_subjects(text)
    if not subjects:
        return None, None  # 腳本裡沒提到資料庫認得的關鍵字，不算錯誤，就是單純沒東西可比對

    viewpoint = detect_viewpoint(text)
    candidates = []
    for subject in subjects:
        rows = [r for r in _INDEX if r.get("subject") == subject]
        if viewpoint:
            rows = [r for r in rows if r.get("視角") in (viewpoint, "不指定", "")]
        if styles:
            rows = [
                r for r in rows
                if r.get("asset_type") in STYLE_EXEMPT_ASSET_TYPES or (r.get("style") or "") in styles
            ]
        candidates.extend(rows)

    if not candidates:
        return None, f"資料庫目前沒有「{'、'.join(subjects)}」的參考素材"

    # 去重（同一列可能因多個 subject 命中被加進來兩次）
    seen = set()
    unique = []
    for r in candidates:
        key = r.get("file_path")
        if key not in seen:
            seen.add(key)
            unique.append(r)

    picked = unique[0]
    note = None
    if len(unique) > 1:
        names = "、".join(r.get("file_name", "") for r in unique)
        note = f"資料庫有 {len(unique)} 筆候選（{names}），自動選第一筆，建議確認是否要換"
    return picked, note


def resolve_image_path(row):
    if not row:
        return None
    ext = os.path.splitext(row.get("file_path", ""))[1].lower()
    if ext not in IMAGE_EXTS:
        return None  # 影片素材（mp4）沒辦法直接當 PPTX 縮圖，跳過
    path = os.path.join(BASE_DIR, row["file_path"])
    return path if os.path.exists(path) else None
