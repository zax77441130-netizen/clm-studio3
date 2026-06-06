from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

class ContactLink(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    url: str = Field(min_length=1, max_length=500)

class LocalizedSite(BaseModel):
    studio_name: str
    english_name: str
    tagline: str
    hero_title: str
    hero_subtitle: str
    about_title: str
    about_content: str
    contact_title: str
    contact_note: str

class Branding(BaseModel):
    logo_path: str
    hero_image_path: str

class SiteWrapper(BaseModel):
    zh: LocalizedSite
    en: LocalizedSite
    branding: Branding

class ServiceItem(BaseModel):
    title: str
    description: str

class ServiceWrapper(BaseModel):
    zh: List[ServiceItem]
    en: List[ServiceItem]

class PortfolioLocale(BaseModel):
    title: str
    summary: str
    detail: str
    tech_stack: List[str]

class PortfolioItem(BaseModel):
    id: str
    category: str
    cover_image: str
    open_in_new_page: bool = True
    external_url: Optional[str] = ""
    zh: PortfolioLocale
    en: PortfolioLocale

class SitePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    site: SiteWrapper
    services: ServiceWrapper
    portfolio: List[PortfolioItem]
    contacts: List[ContactLink]
