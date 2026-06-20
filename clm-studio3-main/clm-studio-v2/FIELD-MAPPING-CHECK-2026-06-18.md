# 欄位映射檢查報告

## 本次完成項目

### A. 英文正式前台內容後台 UI
已補齊以下英文正式內容後台欄位：

- Home
- About
- Services
- Portfolio
- Contact

目前後台已可直接編輯英文正式前台內容，而不只是英文模板或英文 SEO。

### B. Services 中文自動翻譯英文
已新增後台按鈕：

- `中文服務自動翻成英文`

目前邏輯：

- 以中文服務標題 / 描述為來源
- 呼叫後端 `/api/admin/translate-service`
- 自動寫回英文 services 區塊
- 不需要手動再新增一份英文服務

注意：

- 目前是規則式翻譯，不是雲端機器翻譯
- 對常見網站 / AI / 系統 / SEO / 顧問 / 自動化詞彙夠用
- 若要更自然商務英文，可後續再接正式翻譯服務或人工微調

---

## 欄位映射檢查結果

### 後台可改
已確認：

- 英文首頁正式內容欄位存在
- 英文關於頁正式內容欄位存在
- 英文服務頁正式內容欄位存在
- 英文作品集頁正式內容欄位存在
- 英文聯絡頁正式內容欄位存在
- Services 中文轉英文按鈕存在
- 後台英文模板欄位存在
- schema / fallback 欄位存在

### JSON 有存
已確認：

- `content.en` 存在
- `seo.templates.en` 存在
- `schema` 存在
- `fallbacks` 存在

### 前台有吃
已確認：

- 首頁有讀 `content[lang].home`
- About 頁有讀 `content[lang].about`
- Services 頁有讀 `content[lang].services`
- Portfolio 頁有讀 `content[lang].portfolio`
- Contact 頁有讀 `content[lang].contact`
- 作品詳頁有吃 SEO fallback
- shared.js 有吃 schema / fallback

### 上線後會反映
目前結論：

- 只要前台仍讀 `/api/site`，且正式網域的 `seo.site_url` 有正確填入
- 後台修改後寫入 `data/site.json`
- 前台重新載入頁面時就會反映

也就是說，架構上目前是：

後台欄位 → API 存入 JSON → 前台讀 JSON → 頁面更新

不是寫死在前端 HTML。

---

## 目前可較高把握確認的事項

### 已接通
- SEO 正式內容
- SEO 模板內容
- 中文前台正式內容
- 英文前台正式內容
- 服務資料
- 作品資料
- 媒體資料
- schema 設定
- fallback 設定

### 仍建議上線前再做一次實機驗證
雖然欄位映射已對過，但若要 100% 上線保險，仍建議在正式部署環境再檢查：

- `seo.site_url` 是否已換成正式網域
- OG 圖網址是否可被外部抓取
- Sitemap / robots.txt 是否輸出正式網域
- 瀏覽器快取是否影響立即看到更新
- 若部署有多 instance，是否有共用同一份 `data/site.json`

---

## 本次新增 / 修改重點檔案

- `backend/app/routes.py`
- `frontend/admin.html`

---

## 結論

這次已完成：

1. Services 中文輸入後可自動生成英文版本
2. 英文正式前台內容後台 UI 已補齊
3. 欄位映射檢查已完成一輪
4. 目前主要內容已不是只存在前端，而是可從後台改動並透過 JSON 餵給前台

若要再往上補到更穩，我下一步會建議：

- 實際啟 backend + frontend 跑一次手動 smoke test
- 用正式 `site_url` 測 sitemap / robots / canonical / og
- 如果需要，把服務翻譯改成更自然的翻譯器而不是規則式替換
