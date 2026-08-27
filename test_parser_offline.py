# -*- coding: utf-8 -*-
"""不打 Notion API，純用手刻的 mock block tree驗證 notion_parser.py 的解析邏輯。"""
import json
from notion_parser import parse_meta, parse_scenes, compute_asset_name, compute_total_count


def todo(text, checked):
    return {"type": "to_do", "to_do": {"rich_text": [{"plain_text": text}], "checked": checked}, "_children": []}


def toggle(text, children):
    return {"type": "toggle", "toggle": {"rich_text": [{"plain_text": text}]}, "_children": children}


def para(text, children=None):
    return {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}, "_children": children or []}


def bullet(text, children=None):
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"plain_text": text}]}, "_children": children or []}


def h2(text):
    return {"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": text}]}, "_children": []}


meta_blocks = [
    toggle("遊戲", [todo("中文德撲", True), todo("印尼德撲", False), todo("印尼合併", False), todo("Wow slot", False)]),
    toggle("投放媒體", [todo("FB", False), todo("Google", True), todo("TikTok", True), todo("其他：", False)]),
    toggle("單支秒數上限", [todo("6s", False), todo("15s", False), todo("30s", True)]),
    toggle("是否做長短秒", [todo("長秒", True), todo("短秒", True)]),
    toggle("素材類型", [todo("全新", True), todo("部分沿用舊素材", False), todo("舊素材微調", False), todo("relanguage", False), todo("resize", False)]),
    toggle("影像特殊需求", [todo("3D", True), todo("2D", False), todo("真人", False), todo("其他：", False)]),
    toggle("音效特殊需求", [todo("人聲配音", False), todo("AI語音", False), todo("先配樂再做畫面", False), todo("需創作音樂", False)]),
    toggle("素材尺寸需求", [
        toggle("優先對稿尺寸（可複選，沒有就不用勾）", [todo("1920×1080", True), todo("1080×1920", False)]),
        toggle("Banner（JPG）", [todo("1920×1080", False)]),
        toggle("Video（mp4）", [todo("1920×1080", True), todo("1080×1920", True), todo("1080×1350", False), todo("1080×1080", True)]),
        toggle("原始尺寸對照表（參考用，不用勾）", []),
    ]),
    para("畫面風格：高級感，整體為藍色調"),
    para("配樂風格：powerful /reggae"),
    para("廣告TA：25-55歲男性"),
    para("廣告目的：複製成效好的3D素材"),
    para("廣告鉤子：爽贏"),
]

scene_blocks = [
    h2("分鏡 1"),
    bullet("場景/道具（跟前一鏡相同可直接寫「同前一cut」）：", [
        bullet("牌桌: 德州撲克牌桌、藍色絨布"),
        bullet("撲克牌: 寫實風格，公牌 10 J K Q"),
    ]),
    para("音樂："),
    para("音效："),
    para("鏡頭 1："),
    toggle("角度/運鏡", [todo("平視", True), todo("俯視", False)]),
    toggle("鏡位", [todo("全景", False), todo("近景", False), todo("中景", False)]),
    para("動作描述：主角第一視角瞇牌、手牌為KK"),
    para("對白/字卡文案："),
    para("秒數：1s"),
    para("鏡頭 2："),
    toggle("角度/運鏡", [todo("平視", False), todo("特寫推進", True)]),
    toggle("鏡位", [todo("全景", False), todo("近景", False), todo("中景", False)]),
    para("動作描述：KKK邊框發光"),
    para("對白/字卡文案："),
    para("秒數：1s"),
]

meta = parse_meta(meta_blocks)
meta["素材名稱"] = compute_asset_name(meta, "鐵支翻盤篇", "20260729")
total, note = compute_total_count(meta)
meta["總支數"] = str(total)
meta["總支數備註"] = note

scenes = parse_scenes(scene_blocks)

print(json.dumps({"meta": meta, "scenes": scenes}, ensure_ascii=False, indent=2))

assert meta["投放媒體"] == ["Google", "TikTok"], meta["投放媒體"]
assert meta["素材尺寸"]["Video"] == ["1080×1080", "1080×1920", "1920×1080"], meta["素材尺寸"]
assert meta["優先對稿尺寸"] == ["1920×1080"], meta["優先對稿尺寸"]
assert meta["素材名稱"] == "20260729_中文德撲_video廣宣_鐵支翻盤篇", meta["素材名稱"]
assert total == 1 * 2 * 3, total
assert len(scenes) == 1
assert scenes[0]["id"] == 1
assert len(scenes[0]["shots"]) == 2
assert scenes[0]["shots"][0]["angle"] == "平視"
assert scenes[0]["shots"][0]["action"] == "主角第一視角瞇牌、手牌為KK"
assert scenes[0]["shots"][0]["seconds"] == "1s"
assert scenes[0]["shots"][1]["action"] == "KKK邊框發光"
assert scenes[0]["layoutObjects"] == [
    {"label": "牌桌", "desc": "德州撲克牌桌、藍色絨布"},
    {"label": "撲克牌", "desc": "寫實風格，公牌 10 J K Q"},
]
print("\nALL ASSERTIONS PASSED (舊版 toggle 排版)")


# ---- 新版排版：「素材基本資訊」整個包成 toggle heading，欄位變成 columns 並排 ----
# 這是實際線上「篇」頁面改版後的真實結構：不是同一層 sibling，而是巢狀在 heading 底下，
# 靠 _flatten_meta_blocks 展開後才能沿用一樣的欄位搜尋邏輯。
from notion_parser import _flatten_meta_blocks  # noqa: E402


def h1(text, children=None):
    return {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": text}]}, "_children": children or []}


def column(children):
    return {"type": "column", "column": {}, "_children": children}


def column_list(label, option_columns):
    return {"type": "column_list", "column_list": {}, "_children": [column([para(label)])] + option_columns}


def option_column(text, checked):
    return column([todo(text, checked)])


def table_row_new(cells):
    return {"type": "table_row", "table_row": {"cells": [[{"plain_text": c}] for c in cells]}, "_children": []}


def table_new(rows):
    return {"type": "table", "table": {}, "_children": rows}


new_meta_blocks = [h1("素材基本資訊", [
    column_list("遊戲", [option_column("中文德撲", True), option_column("印尼德撲", False)]),
    column_list("投放媒體", [option_column("FB", False), option_column("Google", True), option_column("TikTok", True), option_column("其他：", False)]),
    column_list("單支秒數上限", [option_column("6s", False), option_column("15s", False), option_column("30s", True), option_column("45s", False)]),
    column_list("是否做長短秒", [option_column("長秒", True), option_column("短秒", True)]),
    column_list("素材類型", [option_column("全新", True)]),
    column_list("影像特殊需求", [option_column("3D", True), option_column("2D", False)]),
    column_list("音效特殊需求", [option_column("人聲配音", False)]),
    bullet("畫面風格： 高級感，整體為藍色調"),
    bullet("配樂風格： powerful /reggae"),
    bullet("廣告TA： 18-55歲男性"),  # 新版這裡沒有空格，驗證舊版「廣告 TA」跟新版「廣告TA」都要吃得到
    bullet("廣告目的： 複製網上流行影片"),
    bullet("廣告鉤子： 搞笑情境"),
    {  # 「素材尺寸需求」新版是 toggle heading（heading_2 帶 is_toggleable），不是 toggle 區塊
        "type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "素材尺寸需求"}]}, "_children": [
            column_list("優先對稿尺寸", [option_column("1920×1080", True), option_column("1080×1920", False)]),
            column_list("Banner（JPG）", [option_column("1920×1080", False)]),
            column_list("Video（mp4）", [option_column("1920×1080", True), option_column("1080×1920", True),
                                        option_column("1080×1350", False), option_column("1080×1080", True)]),
        ],
    },
])]

new_meta = parse_meta(_flatten_meta_blocks(new_meta_blocks))
assert new_meta["遊戲"] == ["中文德撲"], new_meta["遊戲"]
assert new_meta["投放媒體"] == ["Google", "TikTok"], new_meta["投放媒體"]
assert new_meta["單支秒數上限"] == ["30s"], new_meta["單支秒數上限"]
assert new_meta["畫面風格"] == "高級感，整體為藍色調", new_meta["畫面風格"]
assert new_meta["廣告TA"] == "18-55歲男性", new_meta["廣告TA"]
assert new_meta["素材尺寸"]["Video"] == ["1080×1080", "1080×1920", "1920×1080"], new_meta["素材尺寸"]
assert new_meta["優先對稿尺寸"] == ["1920×1080"], new_meta["優先對稿尺寸"]

new_scene_blocks = [
    h2("分鏡 1"),
    bullet("場景/道具：", [bullet("牌桌: 同前一cut")]),
    para("音樂："),
    para("音效："),
    para("鏡頭 1："),
    column_list("角度/運鏡", [option_column("平視", True), option_column("俯視", False), option_column("其他：", False)]),
    column_list("鏡位", [option_column("全景", False), option_column("近景", True), option_column("中景", False)]),
    table_new([table_row_new(["動作描述", "對白/字卡文案", "秒數"]), table_row_new(["主角瞇牌看到AA", "三條A", "1.5s"])]),
]
new_scenes = parse_scenes(new_scene_blocks)
assert len(new_scenes) == 1
assert new_scenes[0]["shots"][0]["angle"] == "平視", new_scenes[0]["shots"][0]
assert new_scenes[0]["shots"][0]["position"] == "近景", new_scenes[0]["shots"][0]
assert new_scenes[0]["shots"][0]["action"] == "主角瞇牌看到AA", new_scenes[0]["shots"][0]
assert new_scenes[0]["shots"][0]["line"] == "三條A", new_scenes[0]["shots"][0]
assert new_scenes[0]["shots"][0]["seconds"] == "1.5s", new_scenes[0]["shots"][0]

print("ALL ASSERTIONS PASSED (新版 columns+表格排版)")
