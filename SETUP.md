# 手動設定清單

以下步驟牽涉到你自己的帳號密鑰，我沒辦法代勞，需要你自己操作。跟著順序做，全部做完這個
自動化就能用了。同事完全不用做任何設定，他們只需要在 Notion 頁面按按鈕。

## 1. 申請 Notion 內部整合（讓後端程式能讀寫你的 Notion 頁面）

1. 前往 https://www.notion.so/my-integrations → 「+ New integration」
2. 名稱隨意（例如「分鏡腳本自動化」），關聯到你的 workspace
3. Capabilities 至少要勾：Read content、Update content、Insert content
4. 建立後複製 **Internal Integration Secret**（`secret_...` 開頭），這個等一下要填進 Render 的
   `NOTION_TOKEN` 環境變數 —— **不要貼在 Notion 頁面裡或存進程式碼**
5. 回到「腳本」資料夾（你的分鏡腳本都在裡面的那個 Notion 頁面），右上角 `•••` →
   `Connections` → 把剛剛建立的整合加進去。子頁面會一起繼承權限，不用每份都設定一次

## 2. 把 `notion_backend` 這個資料夾放到 GitHub（Render 部署要接 Git repo）

1. 在 GitHub 開一個新的 **private** repository（例如 `storyboard-notion-backend`）
2. 把 `creative related/notion_backend/` 整個資料夾內容 push 上去（`test_*.py` 這幾個測試檔可以不用上傳，但留著也沒差）
3. 記得**不要**把任何 token／secret 寫進程式碼或 commit 進去，這兩個服務用的密鑰全部是在
   Render 後台設定成環境變數（見下一步），不會出現在程式碼裡

## 3. 在 Render 部署

1. 到 https://render.com 註冊（免費方案不用信用卡）
2. New → Web Service → 選擇剛剛那個 GitHub repo
3. Render 會自動偵測 `render.yaml`；如果沒有自動套用，手動設定：
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plan: Free
4. 在 Environment 分頁加兩個環境變數：
   - `NOTION_TOKEN`：步驟 1 拿到的 `secret_...`
   - `WEBHOOK_SECRET`：自己隨便打一串亂數字串（例如用密碼產生器生一組），這是防止別人
     亂打你的服務網址的簡單保護，記下來，等一下步驟 4 要用
5. 部署完成後，Render 會給你一個網址，例如 `https://storyboard-notion-backend.onrender.com`，
   記下來

## 4. 在 Notion 範本頁面加「按鈕」

實際測下來，Notion「Send webhook」這個按鈕動作的簡化版介面**沒有 Body 欄位，URL 也不支援
`{{變數}}`**，所以 `page_id` 只能寫死在網址的 query string 裡，每次複製「範本」開新專案時要
手動改一次。

在「範本」頁面（之後每次複製這頁開新專案，按鈕會一起帶過去，但網址裡的 page_id 要手動換成
新頁面的）：

1. 頁面任意位置新增一個 **Button** 區塊（輸入 `/button`）
2. 按鈕命名「產出 PPTX」，動作選 **Send webhook**
   - URL 填：`https://你的render網址.onrender.com/generate-pptx?secret=步驟3設定的WEBHOOK_SECRET&page_id=這個頁面的ID`
3. 再新增第二個 Button「更新摘要」：
   - URL 填：`https://你的render網址.onrender.com/refresh-summary?secret=...&page_id=...`
4. 再新增第三個 Button「展開分鏡內容」（反向流程：上方文字表格 → 下方完整版，見下方說明）：
   - URL 填：`https://你的render網址.onrender.com/expand-detail?secret=...&page_id=...`

同事之後開新專案，複製「範本」頁面，這三顆按鈕會一起帶過去，但**網址裡的 page_id 要記得
改成新頁面自己的**，不然會改到別份頁面的內容。頁面 ID 可以從瀏覽器網址列複製（`notion.so/`
後面那串英數字，去掉短橫線也可以）。

## 5. 測試

1. 找一份已經填好內容的分鏡頁面（例如「鐵支翻盤篇」），按「更新摘要」按鈕，等幾秒
   （Render 免費方案如果剛好在休眠，第一次可能要等 30-60 秒喚醒），
   確認最上面的摘要表格內容有跟著頁面內容更新
2. 按「產出 PPTX」按鈕，等一下後，頁面下方應該會多一個檔案附件，點開確認排版正常
3. 如果失敗，可以到 Render 後台的 Logs 分頁看後端印出的錯誤訊息

## 6.「展開分鏡內容」（反向流程）

正常流程是先填下方「分鏡內容」完整版，再用「更新摘要」產生上方「文字腳本」簡短版給主管看。
「展開分鏡內容」是反過來：直接在上方表格打純文字（鏡位/秒數可以不填），按這顆按鈕，後端會
用關鍵字比對（`angle_matcher.py` + `angle_keywords.csv`，同事要調整判斷用的口語寫法直接改
那份 CSV）自動判斷要勾選下方「角度/運鏡」「鏡位」的哪個選項，動作/對白/秒數也會照表格內容
填入，讓你確認、手動微調。

- 只影響「動作描述」「對白/字卡文案」「秒數」跟兩組勾選框；「場景/道具」「音樂」「音效」
  這幾欄表格裡本來就沒有，不會被清空或動到
- 上方表格新增/刪掉的「分鏡」「鏡頭」，下方會跟著新增/刪除；表格裡還在的「鏡頭」是整段
  覆蓋重建（不管原本有沒有手動勾過/填過）
- 「鏡位」勾選框新增了「特寫」這個選項（跟「角度/運鏡」的「特寫推進」是不同東西：後者是
  鏡頭運動、前者是靜態的取景範圍），舊頁面第一次跑「展開分鏡內容」時會自動幫每個鏡頭補上
  這個選項

## 已知限制 / 之後可能要注意的地方

- **解析器綁定現在的頁面結構**：`notion_parser.py` 是照「範本」頁面現在的區塊排法寫的
  （标题文字、toggle 名稱、「標籤：內容」的寫法）。如果之後改了範本的欄位名稱或排版方式，
  這支程式要跟著更新，不然會解析不到或解析錯誤
- **圖片**：`shots[].image` 目前沒有自動從 Notion 帶圖片下來，同事如果有參考圖，需要另外
  提供圖片路徑（可以之後視需要再擴充，讓後端自動抓 Notion 頁面裡貼的圖片）
- **免費方案休眠**：Render 免費服務閒置 15 分鐘會休眠，同事第一次按按鈕可能要多等半分鐘
