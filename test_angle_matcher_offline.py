# -*- coding: utf-8 -*-
"""驗證 angle_matcher.py 的關鍵字判斷邏輯，不打 Notion API。"""
import angle_matcher as am

assert am.detect_angle("主角俯視看牌") == "俯視"
assert am.detect_angle("鏡頭慢慢拉近特寫金幣") == "特寫推進"
assert am.detect_angle("正常對話，沒有鏡頭資訊") is None

assert am.detect_position("近景拍攝對手") == "近景"
assert am.detect_position("特寫拍攝金幣") == "特寫"
assert am.detect_position("特寫推進拍攝金幣") is None  # 「推進」出現時，鏡位的「特寫」讓給角度的「特寫推進」
assert am.detect_position("全景鏡頭") == "全景"
assert am.detect_position("完全沒提到鏡位") is None

print("ALL ASSERTIONS PASSED")
