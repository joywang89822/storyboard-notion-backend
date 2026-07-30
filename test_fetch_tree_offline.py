# -*- coding: utf-8 -*-
"""模擬跟真實頁面差不多形狀（寬度、巢狀層數）的區塊樹，驗證 fetch_tree 不會卡死、
而且平行抓取確實比序列快。每個模擬呼叫故意加一點延遲，模擬網路往返時間。"""
import time
from unittest.mock import patch
import notion_parser as np

LATENCY = 0.05  # 模擬一次 API 呼叫的網路延遲（秒）

# 模擬結構：跟「範本」頁面差不多——meta 有 8 個 toggle，其中一個（idx 7）底下還有
# 10 個巢狀 toggle，每個底下又有幾個 to_do leaf。
TREE = {
    "root": [f"meta_toggle_{i}" for i in range(8)] + [f"scene_shot_toggle_{i}" for i in range(20)],
    **{f"meta_toggle_{i}": [f"todo_{i}_{j}" for j in range(4)] for i in range(7)},
    "meta_toggle_7": [f"nested_toggle_{i}" for i in range(10)],
    **{f"nested_toggle_{i}": [f"todo_n_{i}_{j}" for j in range(4)] for i in range(10)},
    **{f"scene_shot_toggle_{i}": [f"todo_s_{i}_{j}" for j in range(3)] for i in range(20)},
}


def fake_get_children(block_id, token):
    time.sleep(LATENCY)
    ids = TREE.get(block_id, [])
    return [
        {"id": cid, "type": "to_do" if cid.startswith("todo") else "toggle",
         "has_children": cid in TREE,
         "to_do": {"rich_text": [{"plain_text": cid}], "checked": False},
         "toggle": {"rich_text": [{"plain_text": cid}]}}
        for cid in ids
    ]


with patch("notion_parser._get_children", side_effect=fake_get_children):
    start = time.time()
    tree = np.fetch_tree("root", "dummy-token")
    elapsed = time.time() - start

n_calls = 1 + 28 + 10  # root + 28 depth-1 nodes-with-children + 10 depth-2 nested toggles
serial_estimate = n_calls * LATENCY
print(f"elapsed={elapsed:.2f}s, serial_estimate={serial_estimate:.2f}s, nodes={len(tree)}")
assert elapsed < serial_estimate, "平行抓取應該要比序列快，不然优化沒生效"
assert elapsed < 5, f"花太久了，看起來可能卡住：{elapsed:.2f}s"
assert len(tree) == 28
print("PASSED")
