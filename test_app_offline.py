# -*- coding: utf-8 -*-
"""不打 Notion/檔案上傳，純測 Flask app 的路由/認證邏輯有沒有接對。"""
import os
from unittest.mock import patch

os.environ["NOTION_TOKEN"] = "dummy"
os.environ["WEBHOOK_SECRET"] = "s3cr3t"

import app as app_module  # noqa: E402

client = app_module.app.test_client()

# 1. 沒帶正確 secret -> 401
r = client.post("/generate-pptx", json={"page_id": "abc"})
assert r.status_code == 401, r.get_json()

# 2. 缺 page_id -> 400
r = client.post("/generate-pptx", json={"secret": "s3cr3t"})
assert r.status_code == 400, r.get_json()

# 3. 正常流程（mock 掉會打網路的三個函式）
fake_data = {"meta": {"素材名稱": "20260729_中文德撲_video廣宣_測試篇"}, "scenes": []}
with patch("app.parse_page", return_value=fake_data) as mp, \
     patch("app.build_pptx") as mb, \
     patch("app.upload_file_to_page") as mu:
    r = client.post("/generate-pptx", json={"secret": "s3cr3t", "page_id": "abc", "title": "測試篇"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["asset_name"] == "20260729_中文德撲_video廣宣_測試篇"
    assert mp.called and mb.called and mu.called

with patch("app.parse_page", return_value={"meta": {}, "scenes": []}), \
     patch("app.refresh_summary_table", return_value=5) as mr:
    r = client.post("/refresh-summary", json={"secret": "s3cr3t", "page_id": "abc"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["rows"] == 5
    assert mr.called

# 4. 陽春版 Notion 按鈕的用法：page_id 放查詢參數、secret 放自訂標頭，完全不帶 Body
with patch("app.parse_page", return_value=fake_data) as mp, \
     patch("app.build_pptx") as mb, \
     patch("app.upload_file_to_page") as mu:
    r = client.post(
        "/generate-pptx?page_id=abc",
        headers={"X-secret": "s3cr3t"},
    )
    assert r.status_code == 200, r.get_json()
    assert mp.call_args.kwargs.get("title") is None  # 沒帶 title 時交給 parse_page 自己去抓

print("ALL APP ROUTE TESTS PASSED")
