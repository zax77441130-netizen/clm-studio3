# Railway Volume 設定說明

目前這個專案會把可變動資料寫到：

- `data/site.json`
- `data/uploads/`

如果直接部署到 Railway、但**沒有掛 Volume**，這些內容通常只會存在於容器的暫存檔案系統中。重新部署、重建、或換機後，資料可能消失。

---

## 這版已支援的持久化方式

後端現在支援用環境變數指定資料目錄：

- `DATA_DIR`

如果沒有設定，預設仍使用專案內的 `./data`。

---

## 建議的 Railway 設定

### 1. 建立 Railway Volume

在 Railway 服務設定中新增一個 Volume。

### 2. 掛載路徑

建議掛到：

- `/app/data`

### 3. 設定環境變數

新增：

- `DATA_DIR=/app/data`

### 4. 保留既有必要環境變數

至少還需要：

- `ADMIN_TOKEN=你的管理密碼`
- `ENVIRONMENT=production`

---

## 掛好之後的實際效果

後端會改成把資料寫到：

- `/app/data/site.json`
- `/app/data/uploads/`

這樣後台修改內容、上傳圖片或影片後，即使 Railway 重新部署，資料仍會保留在 Volume 中。

---

## 上線前確認清單

1. Railway Volume 已建立
2. Volume 已掛到 `/app/data`
3. `DATA_DIR=/app/data` 已設定
4. `ADMIN_TOKEN` 已設定
5. 重新部署後檢查：
   - 後台修改一段文字
   - 上傳一張圖片
   - 重新部署
   - 確認文字與圖片還在

---

## 如果你想用別的掛載路徑

也可以，例如：

- `/app-data`

那就把環境變數改成：

- `DATA_DIR=/app-data`

重點是：

- Railway Volume 掛載路徑
- `DATA_DIR`

這兩個要一致。

---

## 資料保護與首次初始化

- 應用程式啟動與 GET 請求不會建立或改寫 `site.json`。
- 缺檔、JSON 損壞或結構錯誤時，API 會明確失敗，不會用預設範本覆蓋。
- 僅限確認為全新 Volume 時，從 Railway Shell 明確執行：

  ```bash
  cd /app
  python -m backend.app.storage init
  ```

- 如果 `site.json` 已存在，初始化指令會拒絕覆蓋。
- 每次後台儲存前會在 `/app/data/.site-backups/` 建立含 UTC 時間與 SHA-256 的版本，預設保留 30 份。
- 完整還原前會在 `/app/data/.restore-backups/` 備份現況，預設保留 5 份；這些目錄沒有掛成靜態資源。

## 站外備份（不自動上傳）

登入管理後台後，使用「下載完整備份」取得包含 `site.json` 與 `uploads/` 的 ZIP，定期存放到組織已核准的加密雲端硬碟或離線儲存。系統不會自行啟用付費服務，也不會把資料傳送到第三方。

建議至少保留每日 7 份、每週 4 份，並定期在隔離環境測試還原。完整備份可能包含客戶內容，請限制存取權限並啟用儲存端加密。
