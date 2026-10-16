# -*- coding: utf-8 -*-
"""從「參考素材資料庫」自動比對挑圖，取代人工一張張找截圖。

比對規則照 reference_assets/_使用說明.md：
- 用關鍵字對照表把腳本裡的口語寫法轉成標準 subject tag，precise 比對，不做模糊字串比對
- 動作描述裡如果講明是誰（主角/對手/左玩家/右玩家），比對時要連「視角」一起篩
- style 不符時視同沒有對應素材（品牌片尾類例外，見 STYLE_EXEMPT_ASSET_TYPES）
- 完全沒有符合的素材時，明確標記「資料庫沒有對應素材」，不會用相近的湊數

2026-10-15 起：同一個 subject 有多張候選時，不再挑第一筆，而是照下面加分排序挑最像的：
- 牌面一致（動作描述寫「瞇牌AA」→ 優先牌面=AA 的圖；牌面明顯不同的扣分）
- 視角剛好一致（不是「不指定」）
- tags 跟動作描述重疊的字數
- 人工確認過的（tag_source=人工）略優先
只有前兩名分數一樣時才在 note 提醒「有多筆同分候選」。
"""
import csv
import os
import re

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference_assets")
INDEX_CSV = os.path.join(BASE_DIR, "參考素材索引.csv")
KEYWORD_CSV = os.path.join(BASE_DIR, "關鍵字對照表.csv")

VIEWPOINTS = ["主角", "對手", "左玩家", "右玩家"]
STYLE_EXEMPT_ASSET_TYPES = {"片尾"}  # 品牌片尾類（中撲jingle/印撲icon）不比對 style
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
CARD_RE = re.compile(r"(?<![A-Za-z0-9])((?:10|[AKQJT2-9]){2,5})(?![A-Za-z0-9])")


def _load_keyword_map():
    mapping = []  # [(synonym, standard_tag), ...]，長字串優先比對，避免短詞誤判蓋掉長詞
    with open(KEYWORD_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            synonyms_field = row.get("同義詞（腳本/口語常見寫法）", "") or ""
            tag = (row.get("標準tag（填進索引表 subject 欄的字）", "") or "").strip()
            if not tag:
                continue
            for syn in [tag] + synonyms_field.split("、"):
                syn = syn.strip()
                if syn:
                    mapping.append((syn, tag))
    mapping.sort(key=lambda kv: -len(kv[0]))
    return mapping


def _load_index():
    with open(INDEX_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # 圖檔不在（例如沒同步到）的列直接排除，免得選到了卻放不進 PPT
    return [r for r in rows if os.path.exists(os.path.join(BASE_DIR, r.get("file_path", "")))]


_KEYWORD_MAP = _load_keyword_map()
_INDEX = _load_index()


def find_subjects(text):
    """在文字裡找出提到的標準 subject tag，依「在文字裡最先出現的位置」排序（動作描述通常先寫主要動作）。
    英文同義詞（如 ALL IN）不分大小寫。"""
    lowered = text.lower()
    first_pos = {}
    taken = []  # 已被長詞佔掉的區間，避免「三條」在「三條特效」裡又被短詞重複算
    for syn, tag in _KEYWORD_MAP:
        haystack = lowered if syn.isascii() else text
        needle = syn.lower() if syn.isascii() else syn
        start = haystack.find(needle)
        while start != -1:
            end = start + len(needle)
            if not any(s <= start and end <= e for s, e in taken):
                taken.append((start, end))
                if tag not in first_pos or start < first_pos[tag]:
                    first_pos[tag] = start
            start = haystack.find(needle, end)
    return [t for t, _ in sorted(first_pos.items(), key=lambda kv: kv[1])]


def detect_viewpoint(text):
    for vp in VIEWPOINTS:
        if vp in text:
            return vp
    return None


def norm_cards(s):
    s = (s or "").upper().replace("10", "T")
    return "".join(sorted(re.sub(r"[^AKQJT2-9]", "", s)))


def cards_in(text):
    return {norm_cards(m) for m in CARD_RE.findall(text or "")}


def _score(row, text, viewpoint, cards, subject_rank, styles=()):
    score = -subject_rank * 3  # 越早出現的 subject 越主要
    if styles and row.get("style") in styles:
        score += 2  # 片尾類不受風格限制，但同風格的還是優先
    asset_cards = norm_cards(row.get("牌面"))
    if cards and asset_cards:
        score += 6 if asset_cards in cards else -4
    if viewpoint and row.get("視角") == viewpoint:
        score += 2
    tags = [t for t in (row.get("tags") or "").split("、") if len(t) >= 2]
    score += min(3, sum(1 for t in tags if t in text))
    if row.get("tag_source") == "人工":
        score += 1
    return score


def match_asset(text, styles, games=None):
    """styles: 這次腳本的影像風格清單（來自 meta.影像特殊需求，例如 ["3D"]），空清單代表不限風格。
    games: 這次腳本的遊戲（meta.遊戲，例如 ["中文德撲"]）；有同遊戲的候選時只從同遊戲挑，
    避免中撲腳本配到印撲 LUXY POKER 的圖。

    回傳 (asset_row_or_None, note_or_None)。
    """
    subjects = find_subjects(text)
    if not subjects:
        return None, None  # 腳本裡沒提到資料庫認得的關鍵字，不算錯誤，就是單純沒東西可比對

    viewpoint = detect_viewpoint(text)
    cards = cards_in(text)
    scored = []
    seen = set()
    for rank, subject in enumerate(subjects):
        for r in _INDEX:
            if r.get("subject") != subject or r.get("file_path") in seen:
                continue
            if viewpoint and r.get("視角") not in (viewpoint, "不指定", ""):
                continue
            if styles and r.get("asset_type") not in STYLE_EXEMPT_ASSET_TYPES and (r.get("style") or "") not in styles:
                continue
            seen.add(r.get("file_path"))
            scored.append((_score(r, text, viewpoint, cards, rank, styles), r))

    if not scored:
        return None, f"資料庫目前沒有「{'、'.join(subjects)}」的參考素材"
    same_game = [sr for sr in scored if games and sr[1].get("game") in games]
    if same_game:
        scored = same_game

    scored.sort(key=lambda sr: -sr[0])
    picked = scored[0][1]
    note = None
    ties = [r for s, r in scored if s == scored[0][0]]
    if len(ties) > 1:
        names = "、".join(r.get("file_name", "") for r in ties[:5])
        note = f"資料庫有 {len(ties)} 筆同分候選（{names}{'…' if len(ties) > 5 else ''}），自動選第一筆，建議確認"
    return picked, note


def resolve_image_path(row):
    if not row:
        return None
    ext = os.path.splitext(row.get("file_path", ""))[1].lower()
    if ext not in IMAGE_EXTS:
        return None  # 影片素材（mp4）沒辦法直接當 PPTX 縮圖，跳過
    path = os.path.join(BASE_DIR, row["file_path"])
    return path if os.path.exists(path) else None
