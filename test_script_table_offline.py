# -*- coding: utf-8 -*-
"""不打 Notion API：用真實頁面（試水溫篇、投資決策篇、大JJ篇）的文字腳本表格，
驗證「只寫一次就出 PPT」流程的表格解析、角度/鏡位推測、選圖、寫回格式。"""
import script_table as st
from asset_matcher import match_asset, find_subjects, cards_in


def cell(text):
    return [{"type": "text", "text": {"content": text, "link": None}, "plain_text": text,
             "annotations": {"bold": False, "color": "default"}}] if text else []


def table(rows, header=("分鏡", "鏡頭", "秒數", "鏡位", "動作", "對白/文案")):
    kids = [{"id": "hdr", "type": "table_row", "table_row": {"cells": [cell(h) for h in header]}}]
    for i, r in enumerate(rows):
        kids.append({"id": f"r{i}", "type": "table_row", "table_row": {"cells": [cell(c) for c in r]}})
    return {"id": "tbl", "type": "table", "_children": kids}


# 試水溫篇（2D）：鏡位欄是同事人工填的 → 當標準答案
SHUISHIWEN = [
    ("1", "1", "1.5s", "近景", "公牌68A\n特寫主角手牌AA+公牌\nAAA外框發光", "三條A 我要靠這把翻身啦"),
    ("1", "2", "1.5s", "特寫", "拉bar條，下注50000", "先來試個水溫"),
    ("2", "1", "0.5s", "特寫", "左玩家跟注", ""),
    ("2", "2", "0.5s", "特寫", "右玩家跟注", "都跟注?"),
    ("3", "1", "1s", "中景", "轉牌10", "不管了 跟他拚了"),
    ("3", "2", "1.5s", "特寫", "拉bar條All in", "All in"),
    ("4", "1", "0.5s", "特寫", "左玩家all in", "秒跟 太有自信了吧"),
    ("4", "2", "0.5", "特寫", "右玩家棄牌", ""),
    ("5", "1", "1s", "全景", "雙方全開牌\n左玩家79", "挖嘞 三條A還能撞順子"),
    ("6", "1", "2s", "近景", "左玩家手牌+ 6810 外框發光\n左玩家頭像嘲諷笑emoji", ""),
    ("6", "2", "3s", "全景", "開河牌 8\n閃電擊中左玩家頭像 頭像列兩半", "A葫蘆 太爽啦"),
    ("7", "1", "1s", "全景", "爆金幣", ""),
    ("8", "1", "3s", "平視・全景", "中撲jingle", ""),
    ("總秒數", "", "17.5s", "", "", ""),
]
# 投資決策篇（3D）
TOUZI = [
    ("1", "1", "1s", "特寫", "主角瞇牌27 公牌68KA", ""),
    ("1", "2", "3s", "中景", "主角推籌碼，籌碼倒下瞬間畫面定格+黑白畫面", "股票想止損又沒勇氣嗎?"),
    ("2", "1", "3s", "特寫", "主角手牌27\n(勝率條圖從80%>5%)", "德州撲克是計算期望值的遊戲"),
    ("2", "2", "2s", "中景", "主角棄牌，將手牌往前丟出", "遵守紀律不被當韭菜割"),
    ("3", "1", "2s", "特寫", "主角瞇牌看到AA(同分鏡1)，推籌碼All in\n(勝率條圖從0%>85%)", "等到手牌期望值變高"),
    ("3", "2", "2s", "中景/俯視", "對手all in後雙方翻開牌", ""),
    ("4", "1", "2.5s", "中景", "主角葫蘆AAAKK贏過對手高牌，爆金幣籌碼灑落", "練習理性決策，成為投資大師。"),
    ("5", "1", "3s", "平視・全景", "中撲jingle", ""),
]


def blank_position(rows):
    return [(a, b, c, "", e, f) for a, b, c, _, e, f in rows]


# 1. 人工填的鏡位一定照用，不覆蓋、不寫回
rows, cmap = st.read_rows(table(SHUISHIWEN))
assert len(rows) == 13, len(rows)  # 總秒數列被跳過
scenes = st.enrich(st.build_scenes(rows), ["2D"])
assert [len(s["shots"]) for s in scenes] == [2, 2, 2, 2, 1, 2, 1, 1]
assert scenes[0]["shots"][0]["position"] == "近景" and scenes[0]["shots"][0]["_explicit"]
assert scenes[7]["shots"][0]["angle"] == "平視" and scenes[7]["shots"][0]["position"] == "全景"
patched = []
assert st.write_back(table(SHUISHIWEN), cmap, scenes, lambda bid, p: patched.append(bid)) == 0

# 2. 鏡位欄空白 → 自動推測，跟人工答案比對準確度（只印出來，不強制全對）
report = []
for name, data, style in [("試水溫篇", SHUISHIWEN, "2D"), ("投資決策篇", TOUZI, "3D")]:
    truth = [r[3] for r in data if r[0] != "總秒數"]
    t = table(blank_position(data))
    rows, cmap = st.read_rows(t)
    scenes = st.enrich(st.build_scenes(rows), [style])
    shots = [sh for s in scenes for sh in s["shots"]]
    hit = 0
    for sh, ans in zip(shots, truth):
        ok = sh["position"] in ans
        hit += ok
        report.append(f"  {'✓' if ok else '✗'} {name} | 人工:{ans:<6} 自動:{sh['angle']}・{sh['position']:<3}({sh['_inferred']}) | {sh['action'][:22]!r}")
    report.append(f"  → {name} 鏡位命中 {hit}/{len(shots)}")
    # 3. 寫回：每個推測的鏡頭都寫一格，格式「角度・鏡位 (自動)」，其他欄位原樣保留
    calls = []
    n = st.write_back(t, cmap, scenes, lambda bid, p: calls.append((bid, p)))
    assert n == len(shots), (n, len(shots))
    bid, p = calls[0]
    cells = p["table_row"]["cells"]
    assert cells[3][0]["text"]["content"].endswith(st.AUTO_MARK), cells[3]
    assert cells[4][0]["text"]["content"] == data[0][4]  # 動作欄沒被動到
    assert "plain_text" not in cells[4][0]               # 已轉成 PATCH 格式
    # 4. 第二次跑：(自動) 的格子會重新推測，結果一樣就不重寫
    for row in t["_children"]:
        for b, pp in calls:
            if row["id"] == b:
                row["table_row"]["cells"] = [[{**x, "plain_text": x["text"]["content"]} for x in c] for c in pp["table_row"]["cells"]]
    rows2, _ = st.read_rows(t)
    assert all(not r["position"] or st.AUTO_MARK in r["position"] for r in rows2)
    scenes2 = st.enrich(st.build_scenes(rows2), [style])
    assert st.write_back(t, cmap, scenes2, lambda *a: None) == 0
print("\n".join(report))

# 5. 只有對白的延續列併進上一句（大JJ篇的寫法）；「POV 女友視角」這種認不得的人工填寫不寫回
dajj = table([
    ("1", "1", "5s", "POV 女友視角", "女生上車 開車門", "男: 你知道我有多大嗎"),
    ("", "", "3s", "", "", "女: 我是知道沒有很大啦"),
    ("", "", "", "", "", "女: 你都玩這麼大的喔"),
    ("5", "1", "3s", "", "中撲jingle", ""),
])
rows, cmap = st.read_rows(dajj)
assert len(rows) == 3, rows
assert rows[1]["line"] == "女: 我是知道沒有很大啦\n女: 你都玩這麼大的喔", rows[1]["line"]
scenes = st.enrich(st.build_scenes(rows), ["真人"])
assert [len(s["shots"]) for s in scenes] == [2, 1]
calls = []
st.write_back(dajj, cmap, scenes, lambda bid, p: calls.append(bid))
assert "r0" not in calls and "r3" in calls, calls

# 6. 表頭可以多加欄位、換順序
extra = table([("1", "俯視", "全景", "雙方開牌", "", "2s", "牌桌、籌碼")],
              header=("分鏡", "角度", "鏡位", "動作描述", "對白", "秒數", "場景/道具"))
rows, cmap = st.read_rows(extra)
sc = st.build_scenes(rows)[0]
assert sc["shots"][0]["angle"] == "俯視" and sc["shots"][0]["position"] == "全景" and sc["shots"][0]["seconds"] == "2s"
assert [o["desc"] for o in sc["layoutObjects"]] == ["牌桌", "籌碼"]

# 6b. 表格最後加窄的「音效」欄：同分鏡各鏡頭的音效都收進該分鏡
sfx = table([("4", "1", "2s", "", "河牌慢動作彈起 落下翻開K", "", "心跳聲"),
             ("4", "2", "2s", "", "鐵支文案從天而降", "鐵支翻盤啦", "低音鼓"),
             ("5", "1", "3s", "", "中撲jingle", "", "")],
            header=("分鏡", "鏡頭", "秒數", "鏡位", "動作", "對白/文案", "音效"))
rows, cmap = st.read_rows(sfx)
scs = st.build_scenes(rows)
assert scs[0]["sfx"] == "心跳聲；低音鼓" and scs[1]["sfx"] == "", [s["sfx"] for s in scs]
assert cmap["position"] == 3  # 加欄不影響鏡位寫回位置

# 7. 下方完整版有的場景/道具、貼圖會併進來
detail = [{"id": 1, "layoutObjects": [{"label": "遊戲UI", "desc": "同舊素材"}], "music": "reggae", "sfx": "", "note": "",
           "shots": [{"angle": "", "position": "", "image_url": "https://x/1.png", "note": "手動備註"}]}]
rows, _ = st.read_rows(table(TOUZI[:2]))
sc = st.build_scenes(rows, detail)[0]
assert sc["music"] == "reggae" and sc["layoutObjects"][0]["label"] == "遊戲UI"
assert sc["shots"][0]["image_url"] == "https://x/1.png" and sc["shots"][0]["note"] == "手動備註"

# 8. 選圖：牌面要對得上
subs = find_subjects("主角瞇牌看到AA，推籌碼All in"); assert subs[0] == "瞇牌動作" and "All-in動作" in subs, subs
assert "AA" in cards_in("主角瞇牌看到AA，推籌碼All in") and "AAAKK" in cards_in("主角葫蘆AAAKK贏過")
row, note = match_asset("主角瞇牌看到AA，推籌碼All in", ["3D"])
print("瞇牌AA(3D) →", row["file_name"], row["牌面"], row["鏡位"], "|", note)
assert row["subject"] == "瞇牌動作" and row["牌面"] == "AA", row
row, note = match_asset("主角瞇牌KK", ["3D"])
print("瞇牌KK(3D) →", row["file_name"], row["牌面"], "|", note)
assert row["牌面"] == "KK", row
row, _ = match_asset("中撲jingle", ["2D"])
assert row["subject"] == "中撲jingle"
print("ALL SCRIPT TABLE TESTS PASSED")
