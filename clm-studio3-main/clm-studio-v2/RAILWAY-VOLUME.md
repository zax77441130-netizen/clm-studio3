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

- `/data`

### 3. 設定環境變數

新增：

- `DATA_DIR=/data`

### 4. 保留既有必要環境變數

至少還需要：

- `ADMIN_TOKEN=你的管理密碼`
- `ENVIRONMENT=production`

---

## 掛好之後的實際效果

後端會改成把資料寫到：

- `/data/site.json`
- `/data/uploads/`

這樣後台修改內容、上傳圖片或影片後，即使 Railway 重新部署，資料仍會保留在 Volume 中。

---

## 上線前確認清單

1. Railway Volume 已建立
2. Volume 已掛到 `/data`
3. `DATA_DIR=/data` 已設定
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
