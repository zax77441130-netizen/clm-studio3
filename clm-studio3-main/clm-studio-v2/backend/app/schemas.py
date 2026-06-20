from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class OpenModel(BaseModel):
    model_config = ConfigDict(extra='allow')


class ContactLink(OpenModel):
    label: str = Field(min_length=1, max_length=50)
    url: str = Field(min_length=1, max_length=500)


class LocalizedSite(OpenModel):
    studio_name: str
    english_name: str
    tagline: str
    hero_title: str
    hero_subtitle: str
    about_title: str
    about_content: str
    contact_title: str
    contact_note: str


class Branding(OpenModel):
    logo_path: str
    hero_image_path: str


class SeoLocale(OpenModel):
    home_title: str = ''
    home_description: str = ''
    about_title: str = ''
    about_description: str = ''
    services_title: str = ''
    services_description: str = ''
    portfolio_title: str = ''
    portfolio_description: str = ''
    contact_title: str = ''
    contact_description: str = ''
    default_og_image: str = ''


class SeoTemplatesLocale(OpenModel):
    home_title: str = ''
    home_description: str = ''
    about_title: str = ''
    about_description: str = ''
    services_title: str = ''
    services_description: str = ''
    portfolio_title: str = ''
    portfolio_description: str = ''
    contact_title: str = ''
    contact_description: str = ''
    project_title: str = ''
    project_summary: str = ''
    project_detail: str = ''
    project_tech_stack: str = ''
    project_seo_title: str = ''
    project_seo_description: str = ''
    media_alt: str = ''
    media_title: str = ''
    media_caption: str = ''
    image_format: str = ''
    video_format: str = ''
    embed_format: str = ''


class SeoTemplates(OpenModel):
    zh: SeoTemplatesLocale = Field(default_factory=SeoTemplatesLocale)
    en: SeoTemplatesLocale = Field(default_factory=SeoTemplatesLocale)


class SeoConfig(OpenModel):
    site_url: str = ''
    site_name: str = ''
    default_title: str = ''
    title_template: str = '%s | CLM Studio'
    default_description: str = ''
    default_keywords: List[str] = []
    robots: str = 'index, follow, max-image-preview:large'
    twitter_card: str = 'summary_large_image'
    zh: SeoLocale = Field(default_factory=SeoLocale)
    en: SeoLocale = Field(default_factory=SeoLocale)
    templates: SeoTemplates = Field(default_factory=SeoTemplates)


class SiteWrapper(OpenModel):
    zh: LocalizedSite
    en: LocalizedSite
    branding: Branding


class ServiceItem(OpenModel):
    title: str
    description: str


class ServiceWrapper(OpenModel):
    zh: List[ServiceItem]
    en: List[ServiceItem]


class PortfolioLocale(OpenModel):
    title: str
    summary: str
    detail: str
    tech_stack: List[str]
    seo_title: str = ''
    seo_description: str = ''


class PortfolioMediaItem(OpenModel):
    kind: Literal['image', 'video', 'embed'] = 'image'
    url: str
    title: str = ''
    caption: str = ''
    alt: str = ''
    embed_code: str = ''


class PortfolioItem(OpenModel):
    id: str
    category: str
    cover_image: str
    open_in_new_page: bool = True
    external_url: Optional[str] = ''
    featured: bool = False
    zh: PortfolioLocale
    en: PortfolioLocale
    media: List[PortfolioMediaItem] = []


class SitePayload(OpenModel):
    model_config = ConfigDict(extra='allow', populate_by_name=True, protected_namespaces=())
    site: SiteWrapper
    services: ServiceWrapper
    portfolio: List[PortfolioItem]
    contacts: List[ContactLink]
    seo: SeoConfig = Field(default_factory=SeoConfig)
    content: Dict[str, Any] = Field(default_factory=dict)
    schema_: Dict[str, Any] = Field(default_factory=dict, alias='schema', serialization_alias='schema')
    fallbacks: Dict[str, Any] = Field(default_factory=dict)
