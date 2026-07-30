# -*- coding: utf-8 -*-
"""把本機檔案上傳到 Notion，並掛成頁面上的一個檔案區塊（同事可以直接點下載）。"""
import requests
from notion_parser import API, _headers, _get_children

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _scan_page(page_id, token):
    try:
        return _get_children(page_id, token)
    except requests.RequestException:
        return []


def _find_anchor_block_id(children):
    """找「🎬 主管審閱摘要」表格的區塊 id，讓新上傳的檔案可以插在它後面（頁面最上面那一段），
    而不是掉到整頁最下面。找不到（例如頁面沒有摘要區塊）就回傳 None，退回附加在最後面。"""
    for b in children:
        if b.get("type") == "table":
            return b["id"]
    return None


def _delete_old_pptx_files(children, token):
    """每次重新產生都會留下一個新檔案，不清掉舊的話頁面上會越疊越多份、容易點錯到舊版本，
    所以先把之前上傳的 PPTX 檔案區塊刪掉，只保留最新這一份。"""
    for b in children:
        if b.get("type") != "file":
            continue
        name = (b.get("file", {}).get("name") or "").lower()
        if name.endswith(".pptx"):
            try:
                requests.delete(f"{API}/blocks/{b['id']}", headers=_headers(token), timeout=30)
            except requests.RequestException:
                pass  # 刪舊檔失敗不影響這次上傳新檔，最多是舊檔還留著


def upload_file_to_page(page_id, token, file_path, filename):
    children = _scan_page(page_id, token)
    anchor_id = _find_anchor_block_id(children)
    _delete_old_pptx_files(children, token)

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
