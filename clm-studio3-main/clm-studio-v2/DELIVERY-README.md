# CLM Studio 交付說明

## 目前版本定位

這一版已從本機 demo 改造成可在正式網域部署、可由非技術人員維護的後台版本。

## 正式上線必填環境變數

至少要設定：

- `ADMIN_TOKEN=你的後台管理密碼`
- `ENVIRONMENT=production`
- `DATA_DIR=/data`

## Railway 持久化設定

如果部署在 Railway，請**一定要建立 Volume**，並掛載到：

- `/data`

然後把環境變數設成：

- `DATA_DIR=/data`

這樣後端才會把可變動資料寫到持久化儲存，而不是寫在容器暫存層。

實際會保存：

- `site.json`
- `uploads/`

也就是：

- `/data/site.json`
- `/data/uploads/`

如果沒有掛 Railway Volume，重新部署後，後台修改內容和上傳檔案可能消失。

## 上線前一定要做的事

1. 打開後台 `/admin`
2. 到 SEO 區塊填入正式網站網址 `site_url`
   - 例如：`https://yourdomain.com`
3. 填入網站名稱、預設標題、預設描述
4. 上傳 SEO / 分享圖
5. 儲存全部內容
6. 打開 `/seo-check` 檢查：
   - Canonical 是否為正式網域
   - OG URL 是否為正式網域
   - OG Image 是否正常
   - robots.txt 是否有 sitemap
   - sitemap.xml 是否列出正確網址

## 作品集操作流程

### 新增作品
1. 到後台的「作品集管理」
2. 按 `新增作品`
3. 填標題、摘要、詳細介紹
4. 上傳封面圖
5. 按 `套用目前作品`
6. 到「作品內頁媒體」區新增圖片 / 影片 / embed
7. 每新增一筆媒體都按 `套用目前媒體`
8. 最後按 `一鍵儲存全部內容`

### 新增作品時的重要提醒
- 如果沒按最後的 `一鍵儲存全部內容`，重新整理後可能看不到更新
- 如果作品沒有封面，系統會嘗試用第一個媒體當封面
- 如果摘要或詳細介紹沒填，前台會顯示提示文字

## 支援的上傳格式

### 圖片
- jpg / jpeg
- png
- webp
- gif
- heic / heif（會自動轉成網頁可用格式）

### 影片
- mp4
- webm
- mov（伺服器有 ffmpeg 時可轉 mp4，沒有時會要求先自行轉檔）

## SEO 已完成項目
- canonical
- meta description
- keywords
- Open Graph
- Twitter Card
- robots.txt
- sitemap.xml
- Organization / WebSite / AboutPage / ContactPage / CollectionPage / CreativeWork JSON-LD
- 作品頁獨立 SEO
- 後端直出各主要前台頁面的 meta

## 已知目前設計邏輯
- 作品頁如果沒有摘要，會顯示「尚未填摘要」提示
- 作品頁如果沒有詳細介紹，會顯示「尚未填詳細介紹」提示
- 每個媒體可有自己的標題與說明
- 媒體標題會顯示在每個媒體區塊中
- embed 只允許白名單 iframe，不會把一般文字當 HTML 插入
- contacts URL 只允許：
  - `https://`
  - `http://`
  - `mailto:`
  - `tel:`

## 建議交付後的第一輪檢查

1. 測一筆新作品
2. 測一張 HEIC 圖片
3. 測一支影片
4. 測一個 embed
5. 測正式網域 `site_url`
6. 測 `/seo-check`
7. 測 Google / Discord 分享預覽
8. 重新部署一次，確認 Railway Volume 內資料仍存在

## 重要提醒
目前專案資料夾不是 git repo。
如果要做正式維護，建議立刻：
1. `git init`
2. 建立第一版 commit
3. 再接部署流程
