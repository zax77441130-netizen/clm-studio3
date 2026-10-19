import argparse
import fcntl
import hashlib
import json
import logging
import os
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from .config import DATA_DIR, SITE_FILE, UPLOADS_DIR


logger = logging.getLogger(__name__)
LOCK_FILE = DATA_DIR / '.site.lock'
BACKUP_DIR = DATA_DIR / '.site-backups'
RESTORE_BACKUP_DIR = DATA_DIR / '.restore-backups'
BACKUP_RETENTION = 30
RESTORE_BACKUP_RETENTION = 5
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 5 * 1024 * 1024 * 1024


class StorageError(RuntimeError):
    """Base exception for safe persistent-storage failures."""


class DataMissingError(StorageError):
    pass


class DataCorruptError(StorageError):
    pass


class DataValidationError(StorageError):
    pass


class VersionConflictError(StorageError):
    pass


class PostReplaceSyncError(StorageError):
    """The rename completed, but syncing its parent directory failed."""


class RestoreRollbackError(StorageError):
    """A restore failed and its media rollback could not be completed."""


DEFAULT_DATA = {
  "site": {
    "zh": {
      "studio_name": "創模工作室",
      "english_name": "Create Large Model (CLM)",
      "tagline": "Create Beyond Limits.",
      "hero_title": "讓 AI、網站、系統與商業策略真正落地",
      "hero_subtitle": "創模工作室專注於 AI 串接、客製化 AI、網站與系統開發、自動化整合、RAG、AI Agent、資安檢查、SEO 與商業研究，協助品牌與企業把想法做成可實際營運、可持續維護、可逐步成長的成果。",
      "about_title": "關於創模工作室",
      "about_content": "創模工作室（Create Large Model）致力於把品牌、網站、AI 與營運流程整合成真正可使用的數位資產。\n\n我們不把網站、AI、後台與內容拆成彼此孤立的功能，而是回到實際營運情境，從需求理解、資訊架構、頁面內容、技術落地到後續維護，一起規劃。\n\n我們重視的不只是上線，而是交付之後是否真的能被團隊接手、持續更新，並在正式上線到網域後依然保有後台可調整的彈性。",
      "contact_title": "聯絡我們",
      "contact_note": "如果你正在規劃企業官網、品牌網站、AI 導入、RAG、AI Agent、後台系統、流程自動化或 SEO 優化，可以先和我們聊需求、目標、時程與可行方向。正式內容與設定之後也都能在後台持續調整。"
    },
    "en": {
      "studio_name": "CLM Studio",
      "english_name": "Create Large Model (CLM)",
      "tagline": "Create Beyond Limits.",
      "hero_title": "Turn AI, websites, systems, and strategy into real business outcomes",
      "hero_subtitle": "CLM Studio helps brands and companies turn ideas into maintainable business assets through AI integration, custom AI systems, websites, automation, RAG, AI agents, security reviews, SEO, and research.",
      "about_title": "About CLM Studio",
      "about_content": "Create Large Model (CLM) focuses on turning brand communication, websites, AI capabilities, and operating workflows into practical digital assets.\n\nWe do not treat websites, AI, admin tools, and content as isolated pieces. We plan them in real operating context, from requirements and information architecture to content structure, technical delivery, and long-term maintenance.\n\nOur goal is not just launch. It is to deliver work that teams can continue to manage, update, and expand after the site goes live on a real domain.",
      "contact_title": "Contact",
      "contact_note": "If you are planning a corporate website, brand site, AI integration, RAG, AI agents, admin systems, workflow automation, or SEO improvements, start by telling us your goals, timing, and current constraints. Content and settings can still be adjusted later from the admin side."
    },
    "branding": {
      "logo_path": "/uploads/clm-logo-source.png",
      "hero_image_path": "/uploads/clm-hero-source.png"
    }
  },
  "services": {
    "zh": [
      {"title": "AI 串接與智慧客服", "description": "整合客服、表單、CRM、知識庫與內部系統，讓 AI 成為真正可被團隊使用的營運能力。"},
      {"title": "客製化 AI / RAG / Agent", "description": "打造企業專屬 AI、知識問答系統、AI Agent 與內部工具，讓知識、流程與回應能力更具體。"},
      {"title": "網站與系統開發", "description": "提供品牌官網、前後端分離網站、後台系統、API 與商業平台建置，兼顧內容管理與後續維護。"},
      {"title": "自動化整合", "description": "串接跨服務流程，減少人工重複操作，讓資訊流與工作流更順暢。"},
      {"title": "資安檢查", "description": "針對網站、系統、資料流與權限結構進行安全檢視，提供低風險、可執行的改善建議。"},
      {"title": "商業研究 / SEO / 技術顧問", "description": "從市場研究、SEO 規劃到技術方向整理，協助你把決策建立在更清楚的資訊上。"}
    ],
    "en": [
      {"title": "AI Integration & Smart Support", "description": "Connect AI with support, forms, CRM, knowledge bases, and internal systems so teams can use it in real operations."},
      {"title": "Custom AI / RAG / Agents", "description": "Build tailored AI assistants, knowledge systems, RAG tools, and AI agents for practical internal use."},
      {"title": "Web & System Development", "description": "Deliver websites, admin systems, APIs, and business platforms with maintainable content and backend workflows."},
      {"title": "Automation & Workflow Integration", "description": "Connect services and reduce repetitive manual work through clearer operational workflows."},
      {"title": "Security Review", "description": "Assess websites, systems, data flows, and access structures with practical, lower-risk remediation advice."},
      {"title": "Research / SEO / Technical Consulting", "description": "Support market research, SEO planning, and technical direction with clearer decision support."}
    ]
  },
  "portfolio": [
    {
      "id": "project-template",
      "category": "Website / AI / System",
      "cover_image": "/uploads/601a6779a02d4de2ad42c6bf3988af93.jpg",
      "open_in_new_page": True,
      "external_url": "",
      "featured": True,
      "zh": {
        "title": "作品名稱示範｜客戶品牌 / 專案類型 / 核心成果",
        "summary": "用 1 到 2 句快速說明這個專案幫誰解決什麼問題，做了哪些重點，最後帶來什麼成果或價值。",
        "detail": "【專案背景】\n先交代品牌或客戶面對的情境、目標或問題。\n\n【本次執行重點】\n說明本案處理了哪些內容，例如網站改版、AI 串接、流程整合、後台建置、內容架構整理。\n\n【成果與價值】\n描述這個專案完成後，對品牌、使用者或團隊帶來什麼幫助，例如資訊更清楚、流程更順、轉換更好、維護更方便。\n\n【補充說明】\n如果有合作方式、技術特色、內容策略或交付範圍，也可放在這裡。",
        "tech_stack": ["例如：Next.js", "例如：FastAPI", "例如：SEO", "例如：RAG"],
        "seo_title": "作品名稱示範｜案例類型＋核心服務＋品牌名",
        "seo_description": "用 1 句整理這個作品頁想被搜尋理解的重點，通常可由作品摘要濃縮而來，約 60 到 100 字。"
      },
      "en": {
        "title": "Project Title Template | Client / Project Type / Key Outcome",
        "summary": "Use one or two sentences to explain who this project helped, what was delivered, and what value it created.",
        "detail": "[Project Background]\nExplain the client context, goals, or problem first.\n\n[What Was Delivered]\nDescribe the main work, such as website redesign, AI integration, workflow improvement, backend setup, or content structure planning.\n\n[Outcome and Value]\nExplain what improved after delivery, such as clearer information, smoother operations, better conversion, or easier maintenance.\n\n[Additional Notes]\nAdd delivery scope, collaboration model, technical highlights, or strategy notes if helpful.",
        "tech_stack": ["Example: Next.js", "Example: FastAPI", "Example: SEO", "Example: RAG"],
        "seo_title": "Project Title Template | Case Type + Core Service + Brand Name",
        "seo_description": "Summarize the key search-facing message of this case page in one sentence, usually condensed from the project summary."
      },
      "media": [
        {"kind": "image", "url": "/uploads/84dce9393ccd440ba18428b1cf24d7e0.jpg", "title": "首頁視覺示範｜媒體 title 格式", "caption": "說明這張圖在案例裡代表什麼，例如首頁首屏設計、品牌視覺方向或使用者入口。", "alt": "案例首頁視覺示意，呈現品牌主視覺與主要內容入口", "embed_code": ""},
        {"kind": "video", "url": "/uploads/8df969df98d1466fa5302001bf932cf6.mp4", "title": "操作流程示範｜媒體 title 格式", "caption": "說明這支影片展示的是哪一段流程、功能或互動，例如後台操作、頁面切換或功能演示。", "alt": "展示案例後台操作流程與頁面切換的示範影片", "embed_code": ""}
      ]
    }
  ],
  "contacts": [
    {"label": "LINE", "url": "https://line.me/R/ti/p/@your-line-id"},
    {"label": "Facebook", "url": "https://facebook.com/your-page"},
    {"label": "Instagram", "url": "https://instagram.com/your-page"},
    {"label": "Email", "url": "mailto:hello@example.com"},
    {"label": "GitHub", "url": "https://github.com/"}
  ],
  "seo": {
    "site_url": "",
    "site_name": "CLM Studio",
    "default_title": "創模工作室 CLM Studio",
    "title_template": "%s | CLM Studio",
    "default_description": "CLM Studio 提供 AI 導入、網站建置、後台系統、流程自動化與 SEO 優化服務。",
    "default_keywords": ["CLM Studio", "創模工作室", "AI 導入", "網站設計", "SEO", "流程自動化", "AI Agent"],
    "robots": "index, follow, max-image-preview:large",
    "twitter_card": "summary_large_image",
    "zh": {
      "home_title": "首頁 SEO Title 示範｜品牌名＋核心服務＋主要價值",
      "home_description": "首頁 SEO Description 示範：用 1 句說清楚品牌主要做什麼、服務誰、提供什麼價值，避免空泛形容詞。",
      "about_title": "關於頁 SEO Title 示範｜品牌介紹＋理念或專業方向",
      "about_description": "關於頁 SEO Description 示範：簡述品牌背景、工作方式與能提供的核心價值，讓搜尋者快速理解品牌定位。",
      "services_title": "服務頁 SEO Title 示範｜服務類型＋解決方案＋品牌名",
      "services_description": "服務頁 SEO Description 示範：聚焦服務內容、適合對象與可解決的問題，避免只列關鍵字。",
      "portfolio_title": "作品集頁 SEO Title 示範｜案例展示＋服務領域＋品牌名",
      "portfolio_description": "作品集頁 SEO Description 示範：說明這頁收錄哪些類型案例、可看到哪些成果與技術重點。",
      "contact_title": "聯絡頁 SEO Title 示範｜聯絡品牌＋合作需求＋品牌名",
      "contact_description": "聯絡頁 SEO Description 示範：說明適合聯絡的需求類型、合作方向與可透過哪些方式聯繫。",
      "default_og_image": "/assets/og-image.jpg"
    },
    "en": {
      "home_title": "Home SEO Title Template | Brand + Core Service + Main Value",
      "home_description": "Home SEO description template: explain what the brand does, who it serves, and the value it delivers in one clear sentence.",
      "about_title": "About SEO Title Template | Brand Story + Positioning",
      "about_description": "About SEO description template: summarize the brand background, working approach, and practical value clearly.",
      "services_title": "Services SEO Title Template | Service Type + Solution + Brand",
      "services_description": "Services SEO description template: focus on service scope, target audience, and the problems solved.",
      "portfolio_title": "Portfolio SEO Title Template | Case Studies + Service Area + Brand",
      "portfolio_description": "Portfolio SEO description template: explain what kinds of cases appear here and what visitors can learn from them.",
      "contact_title": "Contact SEO Title Template | Contact + Collaboration Need + Brand",
      "contact_description": "Contact SEO description template: explain what kinds of projects are suitable to inquire about and how to get in touch.",
      "default_og_image": "/assets/og-image.jpg"
    },
    "templates": {
      "zh": {
        "home_title": "格式：品牌名＋核心服務＋主要價值\n示範：創模工作室｜AI 導入、網站建置與系統整合",
        "home_description": "格式：品牌主要做什麼＋服務對象＋能帶來的結果\n示範：創模工作室協助品牌與企業整合 AI、網站與後台系統，打造可持續維護的數位成果。",
        "about_title": "格式：關於品牌／工作室＋定位\n示範：關於創模工作室｜品牌、網站、AI 與系統整合",
        "about_description": "格式：品牌背景＋工作方式＋核心價值\n示範：了解創模工作室如何從需求分析、資訊架構到技術落地，協助團隊打造可長期使用的數位資產。",
        "services_title": "格式：服務頁主題＋主要服務項目\n示範：服務內容｜AI 串接、網站開發、後台系統、SEO",
        "services_description": "格式：列出服務範圍＋可解決的問題\n示範：查看創模工作室的 AI 串接、客製化 AI、網站與系統開發、自動化整合與 SEO 顧問服務。",
        "portfolio_title": "格式：作品集／案例展示＋品牌名\n示範：作品集｜創模工作室案例與專案展示",
        "portfolio_description": "格式：案例類型＋可看到的成果內容\n示範：瀏覽創模工作室的 AI、網站、系統整合與自動化案例，了解專案成果、技術堆疊與交付方式。",
        "contact_title": "格式：聯絡品牌＋合作需求\n示範：聯絡我們｜創模工作室 CLM Studio",
        "contact_description": "格式：適合洽詢的需求＋聯絡目的\n示範：聯絡創模工作室，洽詢 AI 導入、網站建置、流程自動化與 SEO 專案合作。",
        "project_title": "格式：客戶／品牌名＋專案類型＋成果關鍵詞\n示範：某品牌官網改版｜網站重構與 SEO 優化案例",
        "project_summary": "格式：誰＋遇到什麼情境＋做了什麼＋得到什麼結果\n示範：協助品牌重整網站架構與內容，讓服務資訊更清楚、詢問流程更順。",
        "project_detail": "格式：專案背景 → 執行重點 → 成果與價值 → 補充說明\n示範：先交代需求與問題，再描述實際處理內容，最後說明成果與後續可維護性。",
        "project_tech_stack": "格式：用逗號分隔技術或方法\n示範：Next.js, FastAPI, SEO, RAG, CMS",
        "project_seo_title": "格式：作品名稱＋服務類型＋品牌名\n示範：某品牌官網改版｜網站重構、SEO 優化｜創模工作室",
        "project_seo_description": "格式：濃縮作品摘要的搜尋版說法\n示範：本案例展示如何透過網站重構、內容優化與 SEO 規劃，提升品牌資訊清晰度與詢問效率。",
        "media_alt": "規則：描述畫面主體、功能或用途，不要只寫『圖片』、『作品圖』。\n示範：案例首頁視覺，呈現品牌主視覺與主要服務入口。",
        "media_title": "規則：寫媒體名稱或段落名稱，方便後台辨識。\n示範：首頁視覺示範、後台操作流程、手機版服務頁。",
        "media_caption": "規則：說明這張圖／這支影片在案例裡代表什麼。\n示範：這張圖展示首頁首屏設計與主要轉換按鈕配置。",
        "image_format": "圖片建議：alt 寫畫面主體與用途；title 寫媒體名稱；caption 寫這張圖在案例中的意義。",
        "video_format": "影片建議：alt 可描述影片展示內容；title 寫影片段落名稱；caption 寫這支影片展示的流程或功能。",
        "embed_format": "Embed 建議：title 寫嵌入內容名稱；caption 寫嵌入內容用途；若可填 alt，描述其展示主題。"
      },
      "en": {
        "home_title": "Format: Brand + Core Service + Main Value\nExample: CLM Studio | AI Integration, Web Development, and System Delivery",
        "home_description": "Format: What the brand does + who it serves + the result it delivers\nExample: CLM Studio helps brands and companies connect AI, websites, and backend systems into maintainable digital assets.",
        "about_title": "Format: About the Brand / Studio + Positioning\nExample: About CLM Studio | Brand, Web, AI, and Systems",
        "about_description": "Format: Brand background + working approach + core value\nExample: Learn how CLM Studio plans requirements, information architecture, and technical delivery for long-term digital operations.",
        "services_title": "Format: Service Page Topic + Main Service Areas\nExample: Services | AI Integration, Web Development, Admin Systems, SEO",
        "services_description": "Format: Service scope + the problems solved\nExample: Explore CLM Studio services across AI integration, custom AI, web development, automation, and SEO consulting.",
        "portfolio_title": "Format: Portfolio / Case Studies + Brand\nExample: Portfolio | CLM Studio Case Studies",
        "portfolio_description": "Format: Case types + what visitors can learn here\nExample: Browse AI, web, and system delivery case studies with project outcomes and technical highlights.",
        "contact_title": "Format: Contact + Brand + Collaboration Need\nExample: Contact | CLM Studio",
        "contact_description": "Format: Suitable inquiry types + contact purpose\nExample: Contact CLM Studio about AI integration, websites, workflow automation, or SEO projects.",
        "project_title": "Format: Client / Brand + Project Type + Outcome Keyword\nExample: Brand Website Redesign | Web Restructure and SEO Case Study",
        "project_summary": "Format: Who + what situation + what was delivered + what improved\nExample: Helped the brand restructure its website and content so service information became clearer and inquiry flow improved.",
        "project_detail": "Format: Background → Delivery Focus → Outcome and Value → Additional Notes\nExample: Explain the need first, then what was built, then what improved after launch.",
        "project_tech_stack": "Format: Comma-separated technologies or methods\nExample: Next.js, FastAPI, SEO, RAG, CMS",
        "project_seo_title": "Format: Project Name + Service Type + Brand\nExample: Brand Website Redesign | Web Restructure and SEO Optimization | CLM Studio",
        "project_seo_description": "Format: Search-facing version of the project summary\nExample: This case study shows how website restructuring, content planning, and SEO improved clarity and inquiry efficiency.",
        "media_alt": "Rule: Describe the visible subject and purpose. Do not just write 'image' or 'project photo'.\nExample: Homepage visual showing the main brand image and core service entry points.",
        "media_title": "Rule: Use a clear media name for backend editing.\nExample: Homepage Visual, Admin Flow Demo, Mobile Services Layout.",
        "media_caption": "Rule: Explain what this image or video represents inside the case study.\nExample: This image shows the first-screen homepage layout and primary call-to-action placement.",
        "image_format": "Image guidance: alt describes the subject and purpose; title names the media; caption explains why the image matters in the case study.",
        "video_format": "Video guidance: alt can describe the video content; title names the clip; caption explains the flow or feature being demonstrated.",
        "embed_format": "Embed guidance: title names the embedded content; caption explains its purpose; if alt is available, describe the displayed topic."
      }
    }
  },
  "content": {
    "zh": {
      "home": {
        "section_tag": "Services",
        "headline": "從品牌網站到 AI 導入，內容分頁完整承接",
        "description": "首頁保持清楚俐落，服務、作品與聯絡資訊則在各自頁面完整展開，讓訪客更容易理解你提供的內容與合作方式。",
        "highlights": [
          {"title": "品牌網站與服務說明", "description": "先把品牌定位、服務內容與頁面導流整理清楚。"},
          {"title": "AI 與系統整合", "description": "讓 AI、後台與營運流程真正接得起來，而不是只停留在展示。"},
          {"title": "可持續維護的後台", "description": "正式上線後仍可持續在後台修改內容、SEO 與作品資料。"}
        ],
        "services_cta_title": "從品牌網站到 AI 導入，內容分頁完整承接",
        "services_cta_description": "首頁先快速建立理解，服務、作品與聯絡資訊再分頁展開，兼顧清楚度、導流與後續 SEO。",
        "consultation_title": "可先免費諮詢，再決定合作方向",
        "consultation_description": "如果你還不確定該從網站、AI、後台或流程整合開始，可以先聊需求、優先順序與執行方向。"
      },
      "about": {
        "work_title": "創模工作室的工作方式",
        "work_description": "我們不把網站、AI、系統整合拆成彼此孤立的功能，而是回到實際營運脈絡，從需求理解、資訊架構、頁面內容、技術落地到後續維護一起規劃。",
        "points": [
          {"title": "先理解需求", "description": "先看目標、限制與優先順序，再決定該怎麼做。"},
          {"title": "重視整合落地", "description": "網站、資料、AI、後台與流程要能實際接起來。"},
          {"title": "保留後續維護彈性", "description": "交付後不是結束，而是要能持續更新與擴充。"}
        ],
        "cards": [
          {"title": "品牌策略", "description": "整理品牌訊息、服務主軸與網站溝通結構。"},
          {"title": "數位產品思維", "description": "不只做頁面，也思考使用流程、管理方式與延伸性。"},
          {"title": "交付與維護", "description": "讓成果不是短期展示，而是可被團隊接手的資產。"}
        ]
      },
      "services": {
        "intro": "每項服務獨立說明，避免把所有資訊都塞在首頁，讓訪客更容易理解創模工作室真正提供的能力與範圍。",
        "cta_title": "如果你不確定該從哪個服務開始",
        "cta_description": "可以先從需求釐清開始，再判斷是網站、AI、自動化還是系統整合更適合。"
      },
      "portfolio": {
        "intro": "作品集不只放幾張圖，而是讓訪客看懂專案背景、執行重點、成果與技術脈絡。"
      },
      "contact": {
        "cards": [
          {"title": "適合什麼需求", "description": "企業網站、品牌網站、AI 導入、RAG、AI Agent、後台系統或流程自動化，都可以先聊。"},
          {"title": "先談需求再談做法", "description": "先釐清需求、時程與優先順序，再決定最適合的執行方式。"},
          {"title": "合作方式保留彈性", "description": "可從單一頁面、單一功能、顧問討論或完整專案開始。"}
        ],
        "project_title": "開始一個專案",
        "project_description": "如果你正在規劃網站、AI、資料流程、自動化或數位轉型需求，可以透過下列方式與我們聯絡。",
        "project_helper": "第一次聯繫不需要把所有內容都準備好，只要先說明你想做什麼、目前卡在哪裡、希望達成什麼結果即可。",
        "consultation_title": "免費諮詢",
        "consultation_description": "若你還不確定該從哪裡開始，可以先透過免費諮詢釐清方向、需求與優先順序。",
        "consultation_helper": "你可以先從網站、AI、後台或流程整合的問題切入，我們會協助你整理成可執行方向。"
      }
    },
    "en": {
      "home": {
        "section_tag": "Selected Focus",
        "headline": "Built for delivery, not just display",
        "description": "CLM Studio helps teams align brand expression, web experience, AI capabilities, and admin operations so digital work becomes usable long after launch.",
        "highlights": [
          {"title": "Corporate websites and brand experience", "description": "Built around brand clarity, content rhythm, and conversion paths."},
          {"title": "AI connected to operations", "description": "Tools should live inside real workflows, not remain demos."},
          {"title": "Maintainable by non-technical teams", "description": "Admin and content management are planned together to keep maintenance practical."}
        ],
        "services_cta_title": "From brand websites to AI delivery, dedicated pages carry the detail",
        "services_cta_description": "The homepage stays restrained while services, work, and contact details expand clearly on their own pages.",
        "consultation_title": "Start with a free consultation",
        "consultation_description": "If you are not yet sure whether to start with web, AI, admin, or workflow integration, begin with a free consultation to clarify needs, goals, and priorities."
      },
      "about": {
        "work_title": "How CLM Studio Works",
        "work_description": "We do not treat websites, AI, and system integration as isolated features. We place them back into real business context and plan the full path from requirements and information architecture to workflows, implementation, and long-term maintenance.",
        "points": [
          {"title": "Business understanding", "description": "Understand needs, constraints, and goals before deciding what to build."},
          {"title": "Technical integration", "description": "Web, data, AI, admin tools, and workflows should actually connect."},
          {"title": "Long-term maintainability", "description": "The result should be a maintainable asset, not a short-lived showcase."}
        ],
        "cards": [
          {"title": "Brand Strategy", "description": "Structure brand messaging, content hierarchy, and visual rhythm into a durable website foundation."},
          {"title": "Digital Product Thinking", "description": "Go beyond launch by considering workflows, management needs, and future extension."},
          {"title": "Delivery & Maintenance", "description": "Deliver outcomes teams can actually inherit, continue, and iterate on."}
        ]
      },
      "services": {
        "intro": "Each service is explained on its own terms so visitors can understand CLM Studio capabilities without forcing everything into the homepage.",
        "cta_title": "Not sure where to start?",
        "cta_description": "Start with needs clarification first, then decide whether web, AI, automation, or system integration is the right fit."
      },
      "portfolio": {
        "intro": "Large projects should not be compressed into a few summary lines, so the portfolio and detail pages carry fuller content, technical notes, and presentation."
      },
      "contact": {
        "cards": [
          {"title": "What We Can Help With", "description": "If you are planning a corporate website, brand site, AI integration, RAG, AI agents, admin systems, or workflow automation, this is a good place to start."},
          {"title": "Clarify Before Building", "description": "CLM Studio focuses on clarifying needs, priorities, and practical scope before pushing you into unnecessary build work."},
          {"title": "Flexible Collaboration", "description": "You can start from a consultation, a single page, one feature, or a full website and system delivery project."}
        ],
        "project_title": "Start a Project",
        "project_description": "If you are planning an AI, web, data workflow, digital transformation, or automation project, use the channels below to reach CLM Studio.",
        "project_helper": "You can contact us directly or begin with a free consultation to clarify needs, timing, and budget range.",
        "consultation_title": "Free Consultation",
        "consultation_description": "If you are not yet sure whether to start with web, AI, admin, or workflow integration, use a free consultation to clarify direction, needs, and priorities first.",
        "consultation_helper": "You do not need everything prepared before the first conversation. Just tell us what you want to build, what is blocking you now, or what outcome you are aiming for."
      }
    }
  },
  "schema": {
    "organization_type": "Organization",
    "enable_breadcrumb": True,
    "enable_video_object": True,
    "enable_faq": False
  },
  "fallbacks": {
    "cover_image_from_first_media": True,
    "summary_message_zh": "這個作品目前還沒填摘要，可到後台補上作品摘要。",
    "summary_message_en": "This project does not have a summary yet. Add one in the admin panel.",
    "detail_message_zh": "這個作品目前還沒填詳細介紹，請到後台補上作品詳細內容。",
    "detail_message_en": "This project does not have a detailed description yet. Add it in the admin panel.",
    "seo_title_from_project_title": True,
    "seo_description_from_summary": True,
    "og_image_default": "/assets/og-image.jpg"
  }
}


def deep_merge(base, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def normalize_portfolio_item(item, index):
    item = deepcopy(item or {})
    item.setdefault('id', f'project-{index + 1}')
    item.setdefault('category', 'General')
    item.setdefault('cover_image', '')
    item.setdefault('external_url', '')
    item.setdefault('open_in_new_page', True)
    item.setdefault('featured', True)
    for lang, fallback_title in [('zh', f'新作品 {index + 1}'), ('en', f'New Project {index + 1}')]:
        locale = item.setdefault(lang, {})
        locale.setdefault('title', fallback_title)
        locale.setdefault('summary', '')
        locale.setdefault('detail', '')
        locale.setdefault('tech_stack', [])
        locale.setdefault('seo_title', '')
        locale.setdefault('seo_description', '')
    media = item.get('media')
    if not isinstance(media, list):
        media = []
    normalized_media = []
    for media_item in media:
        media_item = deepcopy(media_item or {})
        media_item.setdefault('kind', 'image')
        media_item.setdefault('url', '')
        media_item.setdefault('title', '')
        media_item.setdefault('caption', '')
        media_item.setdefault('alt', '')
        media_item.setdefault('embed_code', '')
        normalized_media.append(media_item)
    if not normalized_media and item.get('cover_image'):
        normalized_media.append({
            'kind': 'image',
            'url': item.get('cover_image', ''),
            'title': item['zh'].get('title', ''),
            'caption': '',
            'alt': item['zh'].get('title', ''),
            'embed_code': ''
        })
    item['media'] = normalized_media
    return item


def normalize_data(data):
    raw = deepcopy(data or {})
    if 'schema_' in raw and 'schema' not in raw:
        raw['schema'] = raw.pop('schema_')
    elif 'schema_' in raw and isinstance(raw.get('schema'), dict):
        merged_schema = deepcopy(raw.get('schema_', {}))
        merged_schema.update(raw.get('schema', {}))
        raw['schema'] = merged_schema
        raw.pop('schema_', None)

    merged = deep_merge(deepcopy(DEFAULT_DATA), raw)
    portfolio = merged.get('portfolio') or []
    merged['portfolio'] = [normalize_portfolio_item(item, idx) for idx, item in enumerate(portfolio)]
    if 'schema_' in merged:
        merged.pop('schema_', None)
    return merged


def validate_data(data):
    if not isinstance(data, dict):
        raise DataValidationError('site.json root must be a JSON object')
    required_types = {
        'site': dict,
        'services': dict,
        'portfolio': list,
        'contacts': list,
    }
    for key, expected_type in required_types.items():
        if key not in data:
            raise DataValidationError(f'site.json is missing required field: {key}')
        if not isinstance(data[key], expected_type):
            raise DataValidationError(f'site.json field {key} must be {expected_type.__name__}')
    for key in ('zh', 'en', 'branding'):
        if not isinstance(data['site'].get(key), dict):
            raise DataValidationError(f'site.json field site.{key} must be object')
    for key in ('zh', 'en'):
        if not isinstance(data['services'].get(key), list):
            raise DataValidationError(f'site.json field services.{key} must be array')
    return data


def _read_raw_validated(path=None):
    path = SITE_FILE if path is None else Path(path)
    if not path.exists():
        raise DataMissingError(f'data file does not exist: {path}')
    try:
        raw = path.read_bytes()
    except OSError as exc:
        logger.exception('Unable to read site data from %s', path)
        raise StorageError(f'unable to read data file: {path}') from exc
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error('Invalid JSON in %s: %s', path, exc)
        raise DataCorruptError(f'data file contains invalid JSON: {path}') from exc
    validate_data(data)
    return raw, data


def data_version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def _exclusive_lock():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open('a+b') as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            _recover_restore_locked()
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def with_storage_lock(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _exclusive_lock():
            return function(*args, **kwargs)
    return wrapped


def _fsync_directory(path: Path):
    directory_fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _fsync_tree_directories(root: Path):
    directories = [item for item in root.rglob('*') if item.is_dir()]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(directory)
    _fsync_directory(root)


def _prune(directory: Path, pattern: str, retain: int):
    files = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    removed = False
    try:
        for old_file in files[retain:]:
            old_file.unlink()
            removed = True
    finally:
        if removed:
            _fsync_directory(directory)


def _remove_file_and_sync(path: Path):
    if path.exists():
        path.unlink()
        _fsync_directory(path.parent)


def _backup_site_locked(raw: bytes) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    digest = data_version(raw)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    target = BACKUP_DIR / f'site-{timestamp}-{digest}.json'
    try:
        with target.open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(BACKUP_DIR)
        _prune(BACKUP_DIR, 'site-*.json', BACKUP_RETENTION)
    except Exception as exc:
        logger.exception('Site backup failed; write aborted')
        try:
            _remove_file_and_sync(target)
        except OSError:
            pass
        raise StorageError('backup failed; data was not changed') from exc
    return target


def _atomic_replace_site_locked(serialized: bytes):
    temp_path = None
    replaced = False
    try:
        fd, name = tempfile.mkstemp(prefix='.site-', suffix='.tmp', dir=DATA_DIR)
        temp_path = Path(name)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, SITE_FILE)
        replaced = True
        temp_path = None
        _fsync_directory(DATA_DIR)
    except Exception as exc:
        logger.exception('Atomic site data replacement failed')
        if replaced:
            raise PostReplaceSyncError(
                'site data was replaced, but syncing the data directory failed; durability is uncertain'
            ) from exc
        raise StorageError('atomic replacement failed; previous data was preserved') from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _looks_like_question_marks(value):
    text = str(value or '').strip()
    if not text:
        return False
    allowed = {'?', '？'}
    return set(text).issubset(allowed)


def repair_known_corruption(data):
    try:
        zh_services = data.get('services', {}).get('zh', []) or []
        default_zh_services = DEFAULT_DATA.get('services', {}).get('zh', []) or []
        for index, item in enumerate(zh_services):
            if not isinstance(item, dict):
                continue
            fallback = default_zh_services[index] if index < len(default_zh_services) else {}
            if _looks_like_question_marks(item.get('title')):
                item['title'] = fallback.get('title') or f'服務項目 {index + 1}'
            if _looks_like_question_marks(item.get('description')):
                item['description'] = fallback.get('description') or ''
    except Exception:
        pass
    try:
        value = data.get('fallbacks', {}).get('summary_message_zh')
        if value in {'SMOKE FALLBACK', '???????????????????????'} or _looks_like_question_marks(value):
            data['fallbacks']['summary_message_zh'] = '這個作品目前還沒填摘要，可到後台補上作品摘要。'
    except Exception:
        pass
    return data


def ensure_data():
    """Validate storage without mutating it. Kept for compatibility."""
    with _exclusive_lock():
        _read_raw_validated()


def read_data():
    with _exclusive_lock():
        _, current = _read_raw_validated()
    return repair_known_corruption(normalize_data(current))


def read_data_with_version():
    with _exclusive_lock():
        raw, current = _read_raw_validated()
    return repair_known_corruption(normalize_data(current)), data_version(raw)


def write_data(data, expected_version: str):
    if not expected_version:
        raise VersionConflictError('data version is required')
    validate_data(data)
    normalized = repair_known_corruption(normalize_data(data))
    validate_data(normalized)
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2).encode('utf-8')
    with _exclusive_lock():
        current_raw, _ = _read_raw_validated()
        if data_version(current_raw) != expected_version:
            raise VersionConflictError('site data changed since it was loaded')
        _backup_site_locked(current_raw)
        _atomic_replace_site_locked(serialized)
    return data_version(serialized)


def initialize_data():
    serialized = json.dumps(normalize_data(DEFAULT_DATA), ensure_ascii=False, indent=2).encode('utf-8')
    with _exclusive_lock():
        if SITE_FILE.exists():
            raise StorageError(f'refusing to overwrite existing data file: {SITE_FILE}')
        _atomic_replace_site_locked(serialized)
    return data_version(serialized)


def _safe_archive_member(info: zipfile.ZipInfo) -> PurePosixPath:
    if '\\' in info.filename:
        raise DataValidationError(f'unsafe archive path: {info.filename}')
    path = PurePosixPath(info.filename)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise DataValidationError(f'unsafe archive path: {info.filename}')
    if path.parts[0] not in {'site.json', 'uploads'}:
        raise DataValidationError(f'unexpected archive entry: {info.filename}')
    if path.as_posix() == 'uploads' and not info.is_dir():
        raise DataValidationError('uploads must be a directory')
    if path.as_posix() == 'site.json' and info.is_dir():
        raise DataValidationError('site.json must be a file')
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise DataValidationError(f'archive symlink is not allowed: {info.filename}')
    if path.parts[0] == 'site.json' and len(path.parts) != 1:
        raise DataValidationError(f'invalid site.json path: {info.filename}')
    return PurePosixPath(*path.parts)


def _validated_archive_members(infos: list[zipfile.ZipInfo]):
    validated = []
    entries = {}
    for info in infos:
        normalized = _safe_archive_member(info)
        key = normalized.as_posix()
        kind = 'directory' if info.is_dir() else 'file'
        if key in entries:
            raise DataValidationError(f'backup contains duplicate normalized path: {key}')
        for parent in normalized.parents:
            parent_key = parent.as_posix()
            if parent_key == '.':
                break
            if entries.get(parent_key) == 'file':
                raise DataValidationError(f'backup path conflicts with file: {parent_key}')
        if kind == 'file' and any(existing.startswith(f'{key}/') for existing in entries):
            raise DataValidationError(f'backup file conflicts with directory: {key}')
        entries[key] = kind
        validated.append((info, normalized))
    return validated


def _extract_validated_archive(archive: zipfile.ZipFile, members, destination: Path):
    for info, normalized in members:
        target = destination.joinpath(*normalized.parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, 'r') as source, target.open('xb') as output:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())


def _validate_media_paths(value, media_root=None):
    if isinstance(value, dict):
        for nested in value.values():
            _validate_media_paths(nested, media_root)
    elif isinstance(value, list):
        for nested in value:
            _validate_media_paths(nested, media_root)
    elif isinstance(value, str) and value.startswith('/uploads/'):
        relative = unquote(urlsplit(value).path.removeprefix('/uploads/'))
        path = PurePosixPath(relative)
        if not relative or path.is_absolute() or '..' in path.parts or '\\' in relative:
            raise DataValidationError(f'unsafe media path in site.json: {value}')
        if media_root is not None and not (Path(media_root) / relative).is_file():
            raise DataValidationError(f'backup is missing referenced media: {value}')


def create_full_backup(destination: Path):
    with _exclusive_lock():
        _read_raw_validated()
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.write(SITE_FILE, 'site.json')
            if UPLOADS_DIR.exists():
                for item in sorted(UPLOADS_DIR.rglob('*')):
                    if item.is_symlink():
                        raise StorageError(f'refusing to back up symlink: {item}')
                    if item.is_file():
                        archive.write(item, PurePosixPath('uploads', item.relative_to(UPLOADS_DIR).as_posix()))
    return destination


def _backup_current_state_locked():
    RESTORE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    target = RESTORE_BACKUP_DIR / f'before-restore-{timestamp}.zip'
    try:
        with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.write(SITE_FILE, 'site.json')
            for item in sorted(UPLOADS_DIR.rglob('*')):
                if item.is_symlink():
                    raise StorageError(f'refusing to back up symlink: {item}')
                if item.is_file():
                    archive.write(item, PurePosixPath('uploads', item.relative_to(UPLOADS_DIR).as_posix()))
        with target.open('rb') as handle:
            os.fsync(handle.fileno())
        _fsync_directory(RESTORE_BACKUP_DIR)
        _prune(RESTORE_BACKUP_DIR, 'before-restore-*.zip', RESTORE_BACKUP_RETENTION)
    except Exception as exc:
        try:
            _remove_file_and_sync(target)
        except OSError:
            pass
        raise StorageError('pre-restore backup failed; restore was not started') from exc


def _durable_file(path: Path, content: bytes):
    with path.open('xb') as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _write_restore_state(journal: Path, state: dict):
    temp = journal / 'state.tmp'
    with temp.open('wb') as handle:
        handle.write(json.dumps(state).encode('utf-8'))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, journal / 'state.json')
    _fsync_directory(journal)


def _recover_restore_locked():
    """Rollback uncommitted restores before any storage operation; retryable after a crash."""
    journal = DATA_DIR / '.restore-journal'
    if not journal.exists():
        return
    state_file = journal / 'state.json'
    if not state_file.exists():
        # No switch can start before state.json is durable. Also handles interrupted cleanup.
        _read_raw_validated()
        shutil.rmtree(journal)
        _fsync_directory(DATA_DIR)
        return
    try:
        state = json.loads(state_file.read_bytes())
        old_name = state['old_uploads']
        if not isinstance(old_name, str) or not old_name.startswith('.uploads-old-') or Path(old_name).name != old_name:
            raise ValueError('invalid old-media name')
        if state['state'] not in {'prepared', 'committed'} or not isinstance(state['had_uploads'], bool):
            raise ValueError('invalid journal state')
        old_uploads = DATA_DIR / old_name
        if state['state'] == 'prepared':
            original_raw, _ = _read_raw_validated(journal / 'original-site.json')
            if data_version(original_raw) != state['original_sha256']:
                raise ValueError('original snapshot checksum mismatch')
            if old_uploads.exists():
                if UPLOADS_DIR.exists():
                    shutil.rmtree(UPLOADS_DIR)
                    _fsync_directory(DATA_DIR)
                os.replace(old_uploads, UPLOADS_DIR)
                _fsync_directory(DATA_DIR)
            elif state['had_uploads'] and not UPLOADS_DIR.is_dir():
                raise ValueError('original media is unavailable')
            elif not state['had_uploads'] and UPLOADS_DIR.exists():
                shutil.rmtree(UPLOADS_DIR)
                _fsync_directory(DATA_DIR)
            _atomic_replace_site_locked(original_raw)
        elif old_uploads.exists():
            shutil.rmtree(old_uploads)
            _fsync_directory(DATA_DIR)
        shutil.rmtree(journal)
        _fsync_directory(DATA_DIR)
    except Exception as exc:
        logger.exception('Restore journal recovery failed; refusing further storage operations')
        raise RestoreRollbackError('restore journal recovery failed; data was not reset; manual inspection required') from exc


def recover_pending_restore():
    with _exclusive_lock():
        pass


def restore_full_backup(source: Path):
    staging = Path(tempfile.mkdtemp(prefix='.restore-', dir=DATA_DIR))
    try:
        with zipfile.ZipFile(source, 'r') as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise DataValidationError('backup contains too many entries')
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise DataValidationError('backup uncompressed size exceeds safety limit')
            members = _validated_archive_members(infos)
            if not any(path.as_posix() == 'site.json' for _, path in members):
                raise DataValidationError('backup does not contain site.json')
            _extract_validated_archive(archive, members, staging)
            _fsync_tree_directories(staging)
        restored_raw, restored_data = _read_raw_validated(staging / 'site.json')
        restored_uploads = staging / 'uploads'
        _validate_media_paths(restored_data, restored_uploads)
        with _exclusive_lock():
            current_raw, _ = _read_raw_validated()
            _backup_site_locked(current_raw)
            _backup_current_state_locked()
            old_uploads = DATA_DIR / f'.uploads-old-{os.getpid()}-{os.urandom(4).hex()}'
            journal = DATA_DIR / '.restore-journal'
            journal.mkdir()
            _fsync_directory(DATA_DIR)
            _durable_file(journal / 'original-site.json', current_raw)
            state = {'state': 'prepared', 'old_uploads': old_uploads.name,
                     'had_uploads': UPLOADS_DIR.exists(),
                     'original_sha256': data_version(current_raw)}
            _write_restore_state(journal, state)
            try:
                if UPLOADS_DIR.exists():
                    os.replace(UPLOADS_DIR, old_uploads)
                    _fsync_directory(DATA_DIR)
                if restored_uploads.exists():
                    os.replace(restored_uploads, UPLOADS_DIR)
                else:
                    UPLOADS_DIR.mkdir()
                _fsync_directory(DATA_DIR)
                _atomic_replace_site_locked(restored_raw)
                state['state'] = 'committed'
                _write_restore_state(journal, state)
            except Exception as restore_error:
                try:
                    _recover_restore_locked()
                except Exception as rollback_error:
                    raise RestoreRollbackError(
                        'restore recovery is pending; original data and journal are preserved; '
                        'stop editing and retry after resolving the storage error'
                    ) from rollback_error
                raise restore_error
            _recover_restore_locked()
        return data_version(restored_raw)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _main():
    parser = argparse.ArgumentParser(description='CLM Studio data storage administration')
    parser.add_argument('command', choices=['init'], help='explicit storage operation')
    args = parser.parse_args()
    if args.command == 'init':
        version = initialize_data()
        print(f'Initialized {SITE_FILE} (version {version})')


if __name__ == '__main__':
    _main()
