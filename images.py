# -*- coding: utf-8 -*-
"""把 notion_parser 解析出來的 image_url（同事直接貼在 Notion 頁面裡的圖片）下載到本機，
換成 pptx_builder 看得懂的本機路徑（shots[].image / scenes[].image）。"""
import os
import mimetypes

import requests

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


def materialize_images(data, dest_dir):
    """就地修改 data：把每個有 image_url 的 scene/shot，下載圖片並設定 "image" 欄位。"""
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
    return data
