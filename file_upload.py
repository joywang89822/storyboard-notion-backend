# -*- coding: utf-8 -*-
"""把本機檔案上傳到 Notion，並掛成頁面上的一個檔案區塊（同事可以直接點下載）。"""
import requests
from notion_parser import API, _headers

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def upload_file_to_page(page_id, token, file_path, filename):
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

    r3 = requests.patch(
        f"{API}/blocks/{page_id}/children",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"children": [
            {"type": "file", "file": {"type": "file_upload", "file_upload": {"id": upload["id"]}}}
        ]},
        timeout=30,
    )
    r3.raise_for_status()
    return upload["id"]
