# -*- coding: utf-8 -*-
"""把 notion_parser 解析出來的 image_url（同事直接貼在 Notion 頁面裡的圖片）下載到本機，
換成 pptx_builder 看得懂的本機路徑（shots[].image / scenes[].image）。"""
import os
import mimetypes

import requests

from asset_matcher import match_asset, resolve_image_path

_EXT_FALLBACK = ".jpg"


def _download(url, dest_dir, name_hint):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    ext = mimetypes.guess_extension((r.headers.get("Content-Type") or "").split(";")[0].strip()) or _EXT_FALLBACK
    if ext == ".jpe":
        ext = ".jpg"
    path = os.path.join(dest_dir, f"{name_hint}{ext}")
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def _auto_match(text, styles):
    row, note = match_asset(text, styles)
    return resolve_image_path(row), note


def materialize_images(data, dest_dir):
    """就地修改 data：
    1. 同事直接貼在 Notion 頁面裡的圖片（image_url）優先，下載下來設定 "image" 欄位
    2. 沒有貼圖的鏡頭/分鏡，改用「參考素材資料庫」照 subject/視角/style 自動比對挑圖
       （比對規則見 asset_matcher.py），比對結果有多筆候選或完全沒有時，會在該鏡頭的
       note 欄位標記提醒，跟原本人工比對時的做法一致，不會自己亂猜
    """
    styles = data.get("meta", {}).get("影像特殊需求") or []

    for s in data.get("scenes", []):
        if s.get("image_url"):
            try:
                s["image"] = _download(s["image_url"], dest_dir, f"scene_{s.get('id')}")
            except requests.RequestException:
                pass  # 下載失敗就當作沒有圖片，維持灰底佔位框，不讓整個產出失敗

        for i, sh in enumerate(s.get("shots", []), start=1):
            if sh.get("image_url"):
                try:
                    sh["image"] = _download(sh["image_url"], dest_dir, f"scene_{s.get('id')}_shot_{i}")
                except requests.RequestException:
                    pass
                continue

            text = f"{sh.get('action', '')} {sh.get('line', '')}"
            path, note = _auto_match(text, styles)
            if path:
                sh["image"] = path
            if note:
                sh["note"] = (sh.get("note") + "；" + note) if sh.get("note") else note
    return data
