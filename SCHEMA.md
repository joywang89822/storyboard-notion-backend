# pptx_builder.py 的 JSON 輸入格式

```jsonc
{
  "meta": {
    "素材名稱": "20260720_中文德撲_video廣宣_鐵支翻盤篇",
    "投放媒體": ["Google", "TikTok"],
    "總支數": "6",
    "總支數備註": "1遊戲 × 長短秒2版本 × 3尺寸(1920x1080、1080x1920、1080x1080)",
    "單支秒數上限": ["30s"],
    "是否做長短秒": ["長秒", "短秒"],
    "素材類型": ["全新"],
    "影像特殊需求": ["3D"],
    "音效特殊需求": [],
    "畫面風格": "高級感，整體為藍色調，第一人稱POV視角",
    "配樂風格": "powerful / reggae",
    "廣告TA": "25-55歲男性...",
    "廣告目的": "複製成效好的3D素材",
    "廣告鉤子": "爽贏",
    "素材尺寸": { "Video": ["1920×1080", "1080×1920", "1080×1080"] },
    "優先對稿尺寸": ["1920×1080"]
  },
  "scenes": [
    {
      "id": 1,
      "seconds": "2s",              // 可留空，會自動加總底下 shots 的秒數
      "layoutObjects": [
        { "label": "牌桌", "desc": "德州撲克牌桌、藍色絨布" },
        { "label": "撲克牌", "desc": "寫實風格，公牌 10 J K Q，及一張牌背面" }
      ],
      "music": "",
      "sfx": "",
      "note": "",                    // 分鏡層級備註，會以紅字顯示在該分鏡頁面底部
      "shots": [
        {
          "angle": "平視",           // 對應 Notion「角度/運鏡」打勾的選項
          "position": "",           // 對應 Notion「鏡位」（全景/近景/中景）打勾的選項
          "action": "主角第一視角瞇牌，露出手牌 KK",
          "line": "",                // 對白/字卡文案
          "seconds": "1s",
          "image": null,             // 選填，相對於 base_dir 的圖片路徑；沒有就顯示灰底佔位框
          "note": ""                 // 鏡頭層級備註
        }
      ]
    }
  ]
}
```

## 跟 Notion 打勾選項的對照

`meta` 裡這幾個欄位，值只能是 Notion 範本裡對應 toggle 的固定選項（見 `pptx_builder.py` 裡的 `FIELD_OPTIONS`）：
`投放媒體`、`單支秒數上限`、`是否做長短秒`、`素材類型`、`影像特殊需求`、`音效特殊需求`。

`meta.素材尺寸` 的 key 是「素材類型」（Banner / Video / Gif / Screenshot / 主題圖片 / Liveops / 主題影片 / Icon），
value 是該類型下被打勾的尺寸字串陣列，尺寸字串需跟 `pptx_builder.py` 的 `SIZE_TAXONOMY` 完全一致（含全形括號）。

## CLI 用法

```
python pptx_builder.py <script.json> <output.pptx> [--db-dir DIR] [--spec-img PATH]
```

- `--db-dir`：`shots[].image` 相對路徑的基準資料夾，預設是 json 檔所在資料夾
- `--spec-img`：最後一頁「素材規範」的示意圖（例如 `素材規範頁.png`），留空就不放圖，只顯示文字說明
