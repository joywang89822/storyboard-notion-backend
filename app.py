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


def _get_param(name):
    """相容兩種來源：陽春版 Notion 按鈕只能帶查詢參數/自訂標頭，沒有 Body 可用；
    如果之後方案升級有 Body，也一樣吃得到（手動測試也常用 Body）。"""
    body = request.get_json(force=True, silent=True) or {}
    return request.args.get(name) or request.headers.get(f"X-{name}") or body.get(name)


def _authorized():
    return _get_param("secret") == WEBHOOK_SECRET


@app.route("/generate-pptx", methods=["POST"])
def generate_pptx():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    page_id = _get_param("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    try:
        data = parse_page(page_id, NOTION_TOKEN, title=_get_param("title"))
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
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    page_id = _get_param("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    try:
        data = parse_page(page_id, NOTION_TOKEN, title=_get_param("title"))
        n = refresh_summary_table(page_id, NOTION_TOKEN, data["scenes"])
        return jsonify({"ok": True, "rows": n})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/debug/assets", methods=["GET"])
def debug_assets():
    """診斷用：確認部署到 Render 上的伺服器，實際看不看得到參考素材資料庫。"""
    import asset_matcher as am
    sample = am._INDEX[0] if am._INDEX else None
    sample_img_exists = None
    if sample:
        sample_img_exists = bool(am.resolve_image_path(sample))
    match_row, match_note = am.match_asset("中撲jingle", ["3D"])
    return jsonify({
        "keyword_entries": len(am._KEYWORD_MAP),
        "index_rows": len(am._INDEX),
        "base_dir": am.BASE_DIR,
        "base_dir_exists": os.path.isdir(am.BASE_DIR),
        "sample_row": sample,
        "sample_image_exists_on_disk": sample_img_exists,
        "jingle_test_match": (match_row or {}).get("file_name"),
        "jingle_test_note": match_note,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
