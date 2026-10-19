# Railway 持久資料與備份

本專案目前正式環境的應用程式工作目錄為 `/app`。Railway Volume 掛載點與服務環境變數應一致：

```text
Volume mount path: /app/data
DATA_DIR=/app/data
```

網站內容為 `/app/data/site.json`，媒體為 `/app/data/uploads/`。請沿用現有 Volume，勿另建空白磁碟取代。未設定 DATA_DIR 時程式預設指向應用程式根目錄的 data；正式環境仍應明確設定上述變數。

## 既有正式環境

1. 部署前先匯出目前 Volume 的完整內容到站外，確認備份可解壓且有 site.json 與 uploads。不要以 Git 倉庫中的測試內容代替備份。
2. 保留現有服務 Root Directory 與 Start Command；壓縮檔外層同名目錄不代表實際 Git 路徑。應從 git ls-files 與 Railway 現有設定核對，不可因解壓層級而改路徑。
3. 套用程式時只更新程式與文件，勿覆蓋 data、.env、交易紀錄或備份。既有正式環境不得執行初始化。
4. 一般 GET、讀取及正常啟動不會把範本寫入 site.json。資料缺失、損壞或結構錯誤會失敗，需調查或還原正確備份。
5. 部署後確認重複 GET 不改變 site.json 雜湊及修改時間，再驗證後台儲存、版本衝突、重啟與媒體存取。

## 備份與受控還原

每次儲存前保留文字版本備份 30 份；完整還原前保留完整備份 5 份。管理員可下載含 site.json、uploads 的完整 ZIP。重要編輯前與定期排程均應把完整備份保存到站外，Volume 與同磁碟備份無法防範整個磁碟遺失。

還原使用跨程序鎖、交易紀錄與啟動恢復。不要手動刪除 `.restore-journal`、`.uploads-old-*` 或 `.site.lock`。完整還原應安排維護時段，切換媒體目錄時靜態媒體請求可能短暫失敗。程序 SIGKILL 恢復已有隔離測試；實體斷電與 Railway 正式環境尚未驗證，不保證所有磁碟故障皆可恢復。

## 僅全新空白 Volume

只有確認磁碟為全新且確實要建立初始內容時，才可明確初始化。以下為兩行命令：

```bash
cd /app
python -m backend.app.storage init
```

初始化拒絕覆蓋已存在的 site.json。缺檔不代表磁碟全新，必須先排查掛載與 DATA_DIR。
