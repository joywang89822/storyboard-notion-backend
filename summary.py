# -*- coding: utf-8 -*-
"""重整理「🎬 主管審閱摘要」表格，並寫回 Notion 頁面。

設計上刻意不去動頁面上塊的順序（避免 Notion API 沒有「插入到最前面」這種操作的麻煩），
只找到頁面上第一個 table 區塊（也就是我們一開始塞進去的那張摘要表格），
保留表頭那一列，把底下的資料列整批刪掉重建。
"""
import os
import requests
from notion_parser import _headers, API, NOTION_VERSION, fetch_tree, _text  # noqa: F401


def _find_first_table(tree):
    for b in tree:
        if b.get("type") == "table":
            return b
    return None


def _cell(text):
    return [{"type": "text", "text": {"content": str(text)}}]


def build_rows(scenes):
    """回傳 [[分鏡, 鏡頭, 秒數, 鏡位, 動作, 對白/文案], ...]"""
    rows = []
    for s in scenes:
        for i, sh in enumerate(s["shots"], start=1):
            pos = "・".join(x for x in [sh.get("angle", ""), sh.get("position", "")] if x)
            rows.append([s["id"], i, sh.get("seconds", ""), pos, sh.get("action", ""), sh.get("line", "")])
    return rows


def refresh_summary_table(page_id, token, scenes):
    tree = fetch_tree(page_id, token)
    table = _find_first_table(tree)
    if table is None:
        raise RuntimeError("頁面上找不到摘要表格，可能被手動刪掉或改了格式，需要人工重新加回「🎬 主管審閱摘要」區塊")

    rows = table["_children"]
    if not rows:
        raise RuntimeError("摘要表格沒有表頭列，無法安全重建")

    header = rows[0]
    for row in rows[1:]:
        r = requests.delete(f"{API}/blocks/{row['id']}", headers=_headers(token), timeout=30)
        r.raise_for_status()

    data_rows = build_rows(scenes)
    new_children = [
        {"type": "table_row", "table_row": {"cells": [_cell(c) for c in row]}}
        for row in data_rows
    ]
    if new_children:
        r = requests.patch(
            f"{API}/blocks/{table['id']}/children",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"children": new_children},
            timeout=30,
        )
        r.raise_for_status()
    return len(data_rows)
