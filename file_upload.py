# -*- coding: utf-8 -*-
"""把本機檔案上傳到 Notion，並掛成頁面上的一個檔案區塊（同事可以直接點下載）。"""
import requests
from notion_parser import API, _headers, _get_children

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _find_anchor_block_id(page_id, token):
    """找「🎬 主管審閱摘要」表格的區塊 id，讓新上傳的檔案可以插在它後面（頁面最上面那一段），
    而不是掉到整頁最下面。找不到（例如頁面沒有摘要區塊）就回傳 None，退回附加在最後面。"""
    try:
        children = _get_children(page_id, token)
    except requests.RequestException:
        return None
    for b in children:
        if b.get("type") == "table":
            return b["id"]
    return None


def upload_file_to_page(page_id, token, file_path, filename):
    anchor_id = _find_anchor_block_id(page_id, token)

    r = requests.post(
        f"{API}/file_uploads",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"filename": filename, "content_type": PPTX_MIME},
        timeout=30,
    )
    r.raise_for_status()
    upload = r.json()

    with open(file_path, "rb") as f:
        r2 = requests.post(
            upload["upload_url"],
            headers=_headers(token),
            files={"file": (filename, f, PPTX_MIME)},
            timeout=180,
        )
    r2.raise_for_status()

    payload = {"children": [
        {"type": "file", "file": {"type": "file_upload", "file_upload": {"id": upload["id"]}}}
    ]}
    if anchor_id:
        payload["after"] = anchor_id

    r3 = requests.patch(
        f"{API}/blocks/{page_id}/children",
        headers={**_headers(token), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r3.raise_for_status()
    return upload["id"]
