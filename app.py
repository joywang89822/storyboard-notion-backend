# -*- coding: utf-8 -*-
"""Notion 按鈕觸發的後端服務。兩個動作，全部不需要 Claude／任何 LLM：

  POST /generate-pptx    讀取頁面內容 -> 產生 PPTX -> 上傳回同一頁面
  POST /refresh-summary  讀取頁面內容 -> 重整理最上面的「主管審閱摘要」表格

部署方式、Notion Automation 按鈕怎麼設定，見 SETUP.md。
"""
import os
import tempfile

from flask import Flask, request, jsonify

from notion_parser import parse_page
from pptx_builder import build_pptx
from summary import refresh_summary_table
from file_upload import upload_file_to_page
from images import materialize_images

app = Flask(__name__)

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


def _authorized(body):
    return body.get("secret") == WEBHOOK_SECRET


@app.route("/generate-pptx", methods=["POST"])
def generate_pptx():
    body = request.get_json(force=True, silent=True) or {}
    if not _authorized(body):
        return jsonify({"error": "unauthorized"}), 401
    page_id = body.get("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    try:
        data = parse_page(page_id, NOTION_TOKEN, title=body.get("title", ""))
        with tempfile.TemporaryDirectory() as tmp:
            materialize_images(data, tmp)
            out_name = f"{data['meta']['素材名稱']}_分鏡腳本.pptx"
            out_path = os.path.join(tmp, out_name)
            build_pptx(data, out_path, base_dir=tmp)
            upload_file_to_page(page_id, NOTION_TOKEN, out_path, out_name)
        return jsonify({"ok": True, "asset_name": data["meta"]["素材名稱"]})
    except Exception as e:  # noqa: BLE001 — 回錯誤訊息給 Notion 側好排查
        return jsonify({"error": str(e)}), 500


@app.route("/refresh-summary", methods=["POST"])
def refresh_summary():
    body = request.get_json(force=True, silent=True) or {}
    if not _authorized(body):
        return jsonify({"error": "unauthorized"}), 401
    page_id = body.get("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    try:
        data = parse_page(page_id, NOTION_TOKEN, title=body.get("title", ""))
        n = refresh_summary_table(page_id, NOTION_TOKEN, data["scenes"])
        return jsonify({"ok": True, "rows": n})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
