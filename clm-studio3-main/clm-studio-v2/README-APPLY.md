# 本次更新套用說明

基準：本次提供的 clm-studio3-main (2).zip（含 35 項 Python 測試與 7 項 Node 狀態檢查的版本）。

payload/project 是程式覆蓋包，不是整個官網備份。應將其對應到 Git 實際追蹤的專案目錄；不可再新增一層 clm-studio3-main。以 git ls-files 確認 backend/app/storage.py 所屬的應用程式目錄，再將 payload/project/clm-studio-v2 的內容對應至該處；.gitignore 對應至應用程式目錄的上一層，與既有規則合併。

本次修正文檔中過時的資料路徑為 /app/data，補齊執行期備份與還原交易的 Git 忽略規則。backend、frontend、tests 延用已核對的資料保護修正版，不額外改寫功能。詳見壓縮檔根目錄 BOT-INSTRUCTIONS.txt。

不包含 data、上傳媒體、.env、部署設定或大型測試成果檔；這些既有檔案需保留。Git 忽略規則不會自動解除已追蹤檔案，本次不刪除或取消追蹤既有測試資料。

測試：隔離 DATA_DIR 下 35 項 Python 測試、7 項 Node 狀態檢查通過；Node 使用模擬 DOM/fetch，非瀏覽器端到端驗證。未在 Railway 部署，未驗證實體斷電。正式部署前先取得站外完整備份，正式環境不得執行 init。
