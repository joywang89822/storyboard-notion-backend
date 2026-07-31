# -*- coding: utf-8 -*-
"""驗證 detail_writer.py 的「上方文字表格 -> 下方分鏡內容」展開邏輯，不打 Notion API：
monkeypatch 掉 fetch_tree 跟所有會發 HTTP 的函式，改成記錄呼叫內容，事後檢查。
"""
import detail_writer as dw

_id_seq = [0]


def new_id(prefix):
    _id_seq[0] += 1
    return f"{prefix}{_id_seq[0]}"


def para(text, id_=None, extra_rt=None):
    rt = extra_rt or [{"plain_text": text}]
    return {"id": id_ or new_id("p"), "type": "paragraph", "paragraph": {"rich_text": rt}, "_children": []}


def bullet(text, id_=None):
    return {"id": id_ or new_id("b"), "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"plain_text": text}]}, "_children": []}


def h1(text, id_=None):
    return {"id": id_ or new_id("h1"), "type": "heading_1", "heading_1": {"rich_text": [{"plain_text": text}]}, "_children": []}


def h2(text, id_=None):
    return {"id": id_ or new_id("h2"), "type": "heading_2", "heading_2": {"rich_text": [{"plain_text": text}]}, "_children": []}


def todo(text, checked, id_=None):
    return {"id": id_ or new_id("t"), "type": "to_do", "to_do": {"rich_text": [{"plain_text": text}], "checked": checked}, "_children": []}


def toggle(text, children, id_=None):
    return {"id": id_ or new_id("tg"), "type": "toggle", "toggle": {"rich_text": [{"plain_text": text}]}, "_children": children}


def divider(id_=None):
    return {"id": id_ or new_id("d"), "type": "divider", "divider": {}, "_children": []}


def table_row(cells, id_=None):
    return {"id": id_ or new_id("r"), "type": "table_row",
            "table_row": {"cells": [[{"plain_text": c}] for c in cells]}, "_children": []}


def table(rows, id_=None):
    return {"id": id_ or new_id("tbl"), "type": "table", "table": {}, "_children": rows}


def full_shot(shot_no, angle_checked, position_options, action_text, line_text="", seconds_text="1s", ids=None):
    ids = ids or {}
    # 範本裡「動作描述/對白/字卡文案/秒數」實際上是 bulleted_list_item（項目符號），不是 paragraph；
    # 這裡故意跟真實頁面一樣用 bullet()，這樣才測得出 detail_writer 送錯 block type 的問題
    marker = para(f"鏡頭 {shot_no}：", id_=ids.get("marker"))
    angle_children = [todo(opt, opt == angle_checked, id_=ids.get(f"a_{opt}")) for opt in dw.angle_matcher.ANGLE_OPTIONS]
    angle_children.append(todo("其他：", False))
    angle_tg = toggle("角度/運鏡", angle_children, id_=ids.get("angle_tg"))
    pos_children = [todo(opt, False, id_=ids.get(f"p_{opt}")) for opt in position_options]
    pos_tg = toggle("鏡位", pos_children, id_=ids.get("pos_tg"))
    action = bullet(f"動作描述：{action_text}", id_=ids.get("action"))
    line = bullet(f"對白/字卡文案：{line_text}", id_=ids.get("line"))
    seconds = bullet(f"秒數：{seconds_text}", id_=ids.get("seconds"))
    return [marker, angle_tg, pos_tg, action, line, seconds]


# ---- 組一顆假頁面 ----
# 上方文字表格：分鏡1鏡頭1（既有，動作改了）、分鏡1鏡頭2（既有場景的新鏡頭）、分鏡2（全新分鏡）
summary_table = table([
    table_row(["分鏡", "鏡頭", "秒數", "鏡位", "動作", "對白/文案"]),
    table_row(["1", "1", "1s", "", "主角俯視看牌", ""]),
    table_row(["1", "2", "2s", "", "特寫拍攝金幣", "三條"]),
    table_row(["2", "1", "3s", "全景", "中撲jingle", ""]),
    table_row(["總秒數", "", "99s", "", "", ""], id_="total_row"),  # 故意放錯的舊值，驗證會被重算覆蓋
])

# 下方「分鏡內容」：分鏡1鏡頭1既有（動作是舊文字，鏡位 toggle 只有 3 個選項，沒有「特寫」）
scene1_shot1 = full_shot("1", "平視", ["全景", "近景", "中景"], "舊的動作文字")
scene1 = [h2("分鏡 1")] + [bullet("場景/道具：")] + [para("音樂："), para("音效：")] + scene1_shot1

# 分鏡3：上方表格沒有提到，應該整段被刪除
scene3_shot1 = full_shot("1", "仰視", ["全景", "近景", "中景"], "會被刪除的舊分鏡")
scene3 = [h2("分鏡 3")] + [bullet("場景/道具：")] + [para("音樂："), para("音效：")] + scene3_shot1 + [divider()]

trailing_button = {"id": "btn1", "type": "unsupported", "unsupported": {}, "_children": []}

page_tree = [summary_table, h1("分鏡內容")] + scene1 + scene3 + [trailing_button]

# ---- monkeypatch 掉所有會真的打 API 的函式 ----
calls = {"patch": [], "append": [], "delete": []}


def fake_fetch_tree(page_id, token):
    return page_tree


def fake_patch_block(block_id, payload, token):
    calls["patch"].append((block_id, payload))


def fake_append_children(parent_id, children, token, after=None):
    calls["append"].append((parent_id, after, children))
    results = []
    for c in children:
        c = dict(c)
        c["id"] = new_id("new")
        results.append(c)
    return results


def fake_delete_block(block_id, token):
    calls["delete"].append(block_id)


dw.fetch_tree = fake_fetch_tree
dw._patch_block = fake_patch_block
dw._append_children = fake_append_children
dw._delete_block = fake_delete_block

dw.expand_to_detail("fake_page_id", "fake_token")

# ---- 檢查結果 ----

# 1) 分鏡1鏡頭1 是既有鏡頭：動作文字要被覆蓋更新，而且要送對 block type（bulleted_list_item，
#    不是 paragraph）—曾經送錯過 key，被 Notion 判 400
action_patches = [p for bid, p in calls["patch"] if bid == scene1_shot1[3]["id"]]
assert len(action_patches) == 1
assert "bulleted_list_item" in action_patches[0], action_patches[0]
assert action_patches[0]["bulleted_list_item"]["rich_text"][-1]["text"]["content"] == "主角俯視看牌", action_patches[0]

# 2) 角度/運鏡勾選要更新成「俯視」：「平視」被取消勾選、「俯視」被勾選
angle_todo_ids = {c["type"] if False else None: None}  # noop，避免 lint 抱怨未用變數
angle_children = scene1_shot1[1]["_children"]
by_label = {c["to_do"]["rich_text"][0]["plain_text"]: c["id"] for c in angle_children}
patched_ids = {bid: p for bid, p in calls["patch"]}
assert patched_ids[by_label["平視"]]["to_do"]["checked"] is False
assert patched_ids[by_label["俯視"]]["to_do"]["checked"] is True

# 3) 鏡位 toggle 原本沒有「特寫」選項，應該要被自動新增（透過 append_children 加進該 toggle）
pos_tg_id = scene1_shot1[2]["id"]
appended_into_pos_tg = [c for parent, after, children in calls["append"] if parent == pos_tg_id for c in children]
assert any(c["to_do"]["rich_text"][0]["text"]["content"] == "特寫" for c in appended_into_pos_tg), appended_into_pos_tg

# 4) 分鏡1鏡頭2 是新鏡頭：應該被 append 到分鏡1底下（parent 是 page_id，不是某個 toggle）
new_shot_appends = [
    (parent, after, children) for parent, after, children in calls["append"]
    if parent == "fake_page_id" and any(
        b.get("type") == "paragraph" and "鏡頭 2" in b["paragraph"]["rich_text"][0]["text"]["content"]
        for b in children
    )
]
assert len(new_shot_appends) == 1, calls["append"]

# 4a) 新鏡頭的動作/對白/秒數也要建成 bulleted_list_item，跟範本現有格式一致
for _, _, children in new_shot_appends:
    label_blocks = [b for b in children if b.get("type") == "bulleted_list_item"]
    assert len(label_blocks) == 3, children  # 動作描述、對白/字卡文案、秒數

# 4b) Notion API 規定巢狀 children 要跟 "toggle"/"type" 同一層，不能塞在 "toggle" 裡面 —
#     這裡曾經寫錯過（塞進 toggle 物件內），會被 Notion 判成 400 Bad Request
for _, _, children in new_shot_appends:
    for b in children:
        if b.get("type") == "toggle":
            assert "children" in b, "toggle 區塊沒有帶 children，勾選框不會被建立"
            assert "children" not in b["toggle"], "children 不能塞在 toggle 物件裡面，要跟 type/toggle 同一層"

# 5) 分鏡2 是全新分鏡：應該被 append 到 page 底下，且用「中撲jingle」當動作文字
new_scene_appends = [
    (parent, after, children) for parent, after, children in calls["append"]
    if parent == "fake_page_id" and any(
        b.get("type") == "heading_2" and b["heading_2"]["rich_text"][0]["text"]["content"] == "分鏡 2"
        for b in children
    )
]
assert len(new_scene_appends) == 1, calls["append"]

# 6) 分鏡3 在上方表格已經不存在：整段（含鏡頭6個區塊+divider+heading等）應該被刪除，
#    但緊接在它後面、我們認不得的按鈕區塊絕對不能被刪掉
scene3_ids = {b["id"] for b in scene3}
assert scene3_ids.issubset(set(calls["delete"])), (scene3_ids, calls["delete"])
assert "btn1" not in calls["delete"]

# 7) 總秒數要順便被重算：1s+2s+3s=6s，蓋掉表格裡原本錯的 99s
total_patches = [p for bid, p in calls["patch"] if bid == "total_row"]
assert len(total_patches) == 1, calls["patch"]
assert total_patches[0]["table_row"]["cells"][2][0]["text"]["content"] == "6s", total_patches[0]

print("ALL ASSERTIONS PASSED")
