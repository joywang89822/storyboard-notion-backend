# -*- coding: utf-8 -*-
"""Notion 按鈕觸發的後端服務。兩個動作，全部不需要 Claude／任何 LLM：

  POST /generate-pptx    讀取頁面內容 -> 產生 PPTX -> 上傳回同一頁面
  POST /refresh-summary  讀取頁面內容 -> 重整理最上面的「主管審閱摘要」表格

部署方式、Notion Automation 按鈕怎麼設定，見 SETUP.md。
"""
import os
import sys
import tempfile
import threading
import traceback

from flask import Flask, request, jsonify

from notion_parser import parse_page
from pptx_builder import build_pptx
from summary import refresh_summary_table
from file_upload import upload_file_to_page
from images import materialize_images
from detail_writer import expand_to_detail

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


_LAST_THREAD = None  # 只給測試用，讓測試可以 join 等背景工作跑完再檢查結果


def _run_in_background(fn, *args):
    """Notion 按鈕的 Webhook 動作等不了太久（免費方案 Render 剛好休眠時，喚醒+處理
    很容易超過 Notion 那邊的逾時），所以先立刻回 202，實際工作丟到背景執行緒，
    做完直接呼叫 Notion API 把結果寫回頁面，不需要透過原本那次請求的回應。"""
    global _LAST_THREAD

    def wrapper():
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 — 背景執行緒裡的例外不會有人接，印到 log 才看得到
            traceback.print_exc(file=sys.stderr)
    t = threading.Thread(target=wrapper, daemon=True)
    _LAST_THREAD = t
    t.start()
    return t


def _do_generate(page_id, title):
    data = parse_page(page_id, NOTION_TOKEN, title=title)
    with tempfile.TemporaryDirectory() as tmp:
        materialize_images(data, tmp)
        out_name = f"{data['meta']['素材名稱']}_分鏡腳本.pptx"
        out_path = os.path.join(tmp, out_name)
        build_pptx(data, out_path, base_dir=tmp)
        upload_file_to_page(page_id, NOTION_TOKEN, out_path, out_name)


def _do_summary(page_id, title):
    data = parse_page(page_id, NOTION_TOKEN, title=title)
    refresh_summary_table(page_id, NOTION_TOKEN, data["scenes"])


def _do_expand(page_id, title):
    expand_to_detail(page_id, NOTION_TOKEN)


@app.route("/generate-pptx", methods=["POST"])
def generate_pptx():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    page_id = _get_param("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    _run_in_background(_do_generate, page_id, _get_param("title"))
    return jsonify({"ok": True, "status": "processing"}), 202


@app.route("/refresh-summary", methods=["POST"])
def refresh_summary():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    page_id = _get_param("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    _run_in_background(_do_summary, page_id, _get_param("title"))
    return jsonify({"ok": True, "status": "processing"}), 202


@app.route("/expand-detail", methods=["POST"])
def expand_detail():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    page_id = _get_param("page_id")
    if not page_id:
        return jsonify({"error": "missing page_id"}), 400

    _run_in_background(_do_expand, page_id, _get_param("title"))
    return jsonify({"ok": True, "status": "processing"}), 202


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
    normal_row, normal_note = am.match_asset("主角第一視角瞇牌、手牌為KK", ["3D"])
    kkk_row, kkk_note = am.match_asset("KKK邊框發光", ["3D"])
    return jsonify({
        "keyword_entries": len(am._KEYWORD_MAP),
        "index_rows": len(am._INDEX),
        "base_dir": am.BASE_DIR,
        "base_dir_exists": os.path.isdir(am.BASE_DIR),
        "sample_row": sample,
        "sample_image_exists_on_disk": sample_img_exists,
        "jingle_test_match": (match_row or {}).get("file_name"),
        "jingle_test_note": match_note,
        "normal_test_match": (normal_row or {}).get("file_name"),
        "normal_test_note": normal_note,
        "normal_test_image_exists": bool(am.resolve_image_path(normal_row)) if normal_row else None,
        "kkk_test_match": (kkk_row or {}).get("file_name"),
        "kkk_test_note": kkk_note,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
