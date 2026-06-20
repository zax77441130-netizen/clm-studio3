# SEO 使用說明

這個網站的 SEO 已改成「以正式網域 + 後台資料」為主，不再綁死本機網址。

## 先做什麼

進入後台後，先填：

1. 正式網站網址 `site_url`
   - 例如：`https://yourdomain.com`
2. 網站名稱 `site_name`
3. 預設標題 `default_title`
4. 預設描述 `default_description`
5. 預設 OG 圖片

## 後台每個欄位是做什麼的

### 全站 SEO
- `site_url`
  - 正式網站網域
  - 會影響 canonical、og:url、sitemap.xml、robots.txt、structured data
- `site_name`
  - 網站名稱
- `default_title`
  - 沒有單頁 SEO 標題時的後備標題
- `title_template`
  - 例如 `%s | CLM Studio`
- `default_description`
  - 沒有單頁描述時的後備描述
- `default_keywords`
  - 全站共用關鍵字
- `default_og_image`
  - 社群分享預設圖

### 每頁 SEO
可分別設定：
- 首頁
- 關於頁
- 服務頁
- 作品集頁
- 聯絡頁

每頁至少建議填：
- Title
- Description

### 作品 SEO
每個作品可填：
- 作品 SEO Title
- 作品 SEO Description

如果沒填，系統會退回用作品標題 / 摘要。

## 註冊網域後還有沒有用？

有，但前提是：

**你要去後台把 `site_url` 改成正式網域。**

例如原本：
- `https://example.com`

改成：
- `https://yourdomain.com`

改完再按儲存，之後：
- canonical 會更新
- og:url 會更新
- sitemap.xml 會更新
- robots.txt 裡的 sitemap 會更新
- JSON-LD 裡的網址也會更新

## 新增作品圖片不顯示時先檢查

1. 有沒有先按「上傳並套用」
2. 有沒有再按「套用目前作品」
3. 最後有沒有按「一鍵儲存全部內容」
4. `cover_image` 是否為空
5. 作品媒體是否至少有一筆圖片或影片

## 建議操作流程

### 新增作品
1. 按 `新增作品`
2. 填作品標題、摘要、詳細內容
3. 上傳封面圖
4. 按 `套用目前作品`
5. 到作品內頁媒體區新增圖片 / 影片 / embed
6. 每新增一筆媒體按一次 `套用目前媒體`
7. 最後按 `一鍵儲存全部內容`

### 改 SEO
1. 先填 `site_url`
2. 再填各頁 Title / Description
3. 如果作品很重要，再填作品自己的 SEO
4. 儲存後重新整理頁面檢查

## 已完成的 SEO 功能
- canonical
- meta description
- keywords
- Open Graph
- Twitter Card
- robots.txt
- sitemap.xml
- Organization / WebSite / AboutPage / ContactPage / CollectionPage / CreativeWork JSON-LD
