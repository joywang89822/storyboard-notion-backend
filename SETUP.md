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

在「範本」頁面（之後每次複製這頁開新專案，按鈕會一起帶過去）：

1. 頁面任意位置新增一個 **Button** 區塊（輸入 `/button`）
2. 按鈕命名「產出 PPTX」，動作選 **Send webhook**
   - URL 填：`https://你的render網址.onrender.com/generate-pptx`
   - Body（JSON）填：
     ```json
     {
       "secret": "步驟3設定的WEBHOOK_SECRET",
       "page_id": "{{Page ID}}",
       "title": "{{Page > Title}}"
     }
     ```
     （`{{...}}` 用 Notion 按鈕設定介面裡「插入變數」選，不是直接打字）
3. 再新增第二個 Button「更新摘要」，動作一樣是 Send webhook：
   - URL 填：`https://你的render網址.onrender.com/refresh-summary`
   - Body 跟上面一樣（`secret` / `page_id` / `title`）

同事之後開新專案，複製「範本」頁面，這兩顆按鈕就會一起在，不用重設。

## 5. 測試

1. 找一份已經填好內容的分鏡頁面（例如「鐵支翻盤篇」），按「更新摘要」按鈕，等幾秒
   （Render 免費方案如果剛好在休眠，第一次可能要等 30-60 秒喚醒），
   確認最上面的摘要表格內容有跟著頁面內容更新
2. 按「產出 PPTX」按鈕，等一下後，頁面下方應該會多一個檔案附件，點開確認排版正常
3. 如果失敗，可以到 Render 後台的 Logs 分頁看後端印出的錯誤訊息

## 已知限制 / 之後可能要注意的地方

- **解析器綁定現在的頁面結構**：`notion_parser.py` 是照「範本」頁面現在的區塊排法寫的
  （标题文字、toggle 名稱、「標籤：內容」的寫法）。如果之後改了範本的欄位名稱或排版方式，
  這支程式要跟著更新，不然會解析不到或解析錯誤
- **圖片**：`shots[].image` 目前沒有自動從 Notion 帶圖片下來，同事如果有參考圖，需要另外
  提供圖片路徑（可以之後視需要再擴充，讓後端自動抓 Notion 頁面裡貼的圖片）
- **免費方案休眠**：Render 免費服務閒置 15 分鐘會休眠，同事第一次按按鈕可能要多等半分鐘
