from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import bs4
import requests
import urllib3

urllib3.disable_warnings()

ROOT = Path(__file__).parent
OUT = ROOT / "graph" / "data" / "sources" / "africa_batch_2026_06.jsonl"
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url: str, *, verify: bool = True) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=10, verify=verify)
    r.raise_for_status()
    return r


def clean(text: str | None) -> str:
    raw = text or ""
    if "<" not in raw and ">" not in raw:
        return re.sub(r"\s+", " ", raw).strip()
    return re.sub(r"\s+", " ", bs4.BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)).strip()


def ensure_url(value: str | None) -> str:
    text = clean(value)
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    return "https://" + text.lstrip("/")


def broad_sector(text: str) -> str:
    t = clean(text).lower()
    if any(k in t for k in ("bank", "banque", "financial", "insurance", "assurance", "invest", "leasing", "holding", "capital", "finance", "microfinance", "broker")):
        return "Financials"
    if any(k in t for k in ("telecom", "technology", "software", "ict", "digital", "internet", "communication", "media")):
        return "Information Technology" if any(k in t for k in ("technology", "software", "ict", "digital", "internet")) else "Communication Services"
    if any(k in t for k in ("health", "medical", "hospital", "pharma", "santé", "pharm")):
        return "Health Care"
    if any(k in t for k in ("oil", "gas", "petrol", "energy", "petrole")):
        return "Energy"
    if any(k in t for k in ("electric", "power", "water", "utility", "utilities")):
        return "Utilities"
    if any(k in t for k in ("real estate", "reit", "immobilier", "placement immobilier")):
        return "Real Estate"
    if any(k in t for k in ("food", "beverage", "brew", "consumer goods", "agric", "agro", "palm", "cocoa", "tea", "staple", "distribution", "tobacco")):
        return "Consumer Staples"
    if any(k in t for k in ("automobile", "accessories", "retail", "commercial", "service", "services", "hotel", "travel", "consumer")):
        return "Consumer Discretionary"
    if any(k in t for k in ("cement", "construction", "building", "materials", "chem", "mining", "paper", "matériaux", "mine", "steel", "glass")):
        return "Materials"
    if any(k in t for k in ("industrial", "manufactur", "transport", "logistics", "engineering", "equip", "machinery", "distribution")):
        return "Industrials"
    return "Other"


def city_from_text(text: str, country: str) -> str:
    text = clean(text)
    if not text:
        return country
    lower = text.lower()
    city_maps = {
        "Ghana": ["Accra", "Tema", "Kumasi", "Takoradi", "Cape Coast"],
        "Kenya": ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Thika"],
        "Morocco": ["Casablanca", "Rabat", "Marrakech", "Tangier", "Fes"],
        "Benin": ["Cotonou", "Porto-Novo"],
        "Burkina Faso": ["Ouagadougou", "Bobo-Dioulasso"],
        "Cote d'Ivoire": ["Abidjan", "Yamoussoukro", "San Pedro"],
        "Mali": ["Bamako"],
        "Niger": ["Niamey"],
        "Senegal": ["Dakar", "Thiès"],
        "Togo": ["Lomé"],
    }
    for city in city_maps.get(country, []):
        if city.lower() in lower:
            return f"{city}, {country}"
    if "," not in text:
        return country
    last = [part.strip() for part in text.split(",") if part.strip()]
    if last:
        city = re.sub(r"^\d+\s*", "", last[-1]).strip()
        if city and city.lower() != country.lower():
            return f"{city.title()}, {country}"
    return country


def normalize_ghana_hq(text: str) -> str:
    lower = clean(text).lower()
    if not lower:
        return "Ghana"
    if "kumasi" in lower:
        return "Kumasi, Ghana"
    if "tema" in lower:
        return "Tema, Ghana"
    if "accra" in lower or any(k in lower for k in ("osu", "ridge", "latebu", "capital mall", "north industrial area")):
        return "Accra, Ghana"
    if "w4 5xt" in lower or "united kingdom" in lower:
        return "Ghana"
    return "Ghana"


def country_from_brvm(text: str) -> str:
    t = unicodedata.normalize("NFKD", clean(text)).replace("’", "'").encode("ascii", "ignore").decode().upper()
    mapping = {
        "BENIN": "Benin",
        "BURKINA FASO": "Burkina Faso",
        "COTE D'IVOIRE": "Cote d'Ivoire",
        "MALI": "Mali",
        "NIGER": "Niger",
        "SENEGAL": "Senegal",
        "TOGO": "Togo",
    }
    for k, v in mapping.items():
        if k in t:
            return v
    return "BRVM Region"


def parse_brvm_profile(html: str) -> dict[str, str]:
    text = clean(html)
    fields = {}
    for label in ("Raison sociale", "Secteur d’activités", "Date d’introduction à la BRVM"):
        m = re.search(label + r"\s*:\s*(.+?)(?=(Raison sociale|Secteur d’activités|Date d’introduction à la BRVM|Capital social|Symbole|Conseil d’administration|$))", text, re.I)
        if m:
            fields[label] = clean(m.group(1))
    symbol = re.search(r"Symbole\s*:\s*([A-Z0-9 .-]{2,20}?)(?=\s+(?:Conseil|Nom|$))", text)
    if symbol:
        fields["Symbole"] = clean(symbol.group(1))
    return fields


@dataclass
class Record:
    canonical_id: str
    name: str
    country: str
    exchange: str
    sector_or_sic: str
    ticker: str
    sub: str
    hq: str
    website: str = ""
    f: str = ""
    research: dict | None = None
    quote_symbol: str = ""

    def as_json(self) -> str:
        data = {
            "canonical_id": self.canonical_id,
            "name": self.name,
            "country": self.country,
            "exchange": self.exchange,
            "sector_or_sic": self.sector_or_sic,
            "ticker": self.ticker,
            "sub": self.sub,
            "hq": self.hq,
        }
        if self.website:
            data["website"] = self.website
        if self.f:
            data["f"] = self.f
        if self.quote_symbol:
            data["quote_symbol"] = self.quote_symbol
        if self.research:
            data["research"] = self.research
        return json.dumps(data, ensure_ascii=False)


def build_kenya() -> list[Record]:
    url = "https://www.nse.co.ke/listed-companies/"
    soup = bs4.BeautifulSoup(fetch(url).text, "html.parser")
    rows: list[Record] = []
    seen: set[str] = set()
    for toggle in soup.select("div.toggle.default"):
        heading = clean(toggle.find("h3").get_text(" ", strip=True))
        if "EXCHANGE TRADED FUND" in heading.upper():
            continue
        for col in toggle.select("div.vc_col-sm-3"):
            h6 = col.find("h6")
            if not h6:
                continue
            body = clean(col.get_text(" ", strip=True))
            if "Trading Symbol:" not in body or "ISIN CODE:" not in body:
                continue
            name = clean(h6.get_text(" ", strip=True))
            symbol = body.split("Trading Symbol:", 1)[1].split("ISIN CODE:", 1)[0].strip()
            if symbol in seen:
                continue
            seen.add(symbol)
            website = ""
            for a in col.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http"):
                    website = href
                    break
            rows.append(
                Record(
                    canonical_id=f"XNAI:{symbol}",
                    name=name,
                    country="Kenya",
                    exchange="XNAI",
                    sector_or_sic=broad_sector(heading),
                    ticker=symbol,
                    sub=heading,
                    hq="Kenya",
                    website=website,
                    research={"exchange_listing": url},
                )
            )
    return rows


def build_ghana() -> list[Record]:
    base = "https://gse.com.gh/listed-companies/"
    soup = bs4.BeautifulSoup(fetch(base).text, "html.parser")
    rows: list[Record] = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        a = tds[1].find("a")
        if not a:
            continue
        symbol = clean(a.get_text(" ", strip=True))
        name = clean(tds[2].get_text(" ", strip=True))
        if name == "NewGold Issuer Ltd.":
            continue
        info = {}
        detail_url = urljoin(base, a["href"])
        try:
            detail = fetch(detail_url).text
            dsoup = bs4.BeautifulSoup(detail, "html.parser")
            table = dsoup.find("table")
            if table:
                for row in table.find_all("tr"):
                    cells = row.find_all(["th", "td"])
                    if len(cells) == 2:
                        info[clean(cells[0].get_text(" ", strip=True))] = clean(cells[1].get_text(" ", strip=True))
        except requests.RequestException:
            detail_url = ""
        business = info.get("Nature of Business", "")
        website = ensure_url(info.get("Website", ""))
        listed = info.get("Date Listed", "")
        year = listed[-4:] if re.search(r"\b\d{4}\b", listed) else ""
        hq = normalize_ghana_hq(info.get("Registered Office") or info.get("Postal Address") or "")
        rows.append(
            Record(
                canonical_id=f"GSE:{symbol}",
                name=name,
                country="Ghana",
                exchange="GSE",
                sector_or_sic=broad_sector(business or info.get("Security", "")),
                ticker=symbol,
                sub=business or info.get("Security", ""),
                hq=hq,
                website=website,
                f=year,
                research={"exchange_profile": detail_url} if detail_url else {"exchange_listing": base},
            )
        )
    return rows


def build_morocco() -> list[Record]:
    url = "https://www.casablanca-bourse.com/fr/listing-des-emetteurs"
    soup = bs4.BeautifulSoup(fetch(url, verify=False).text, "html.parser")
    rows: list[Record] = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        issuer_a = tds[0].find("a", href=True)
        ticker_a = tds[2].find("a", href=True)
        name = clean(tds[0].get_text(" ", strip=True))
        ticker = clean((ticker_a["href"].rstrip("/").split("/")[-1] if ticker_a else "") or tds[2].get_text(" ", strip=True))
        sub = clean(tds[3].get_text(" ", strip=True))
        if " " in ticker:
            continue
        rows.append(
            Record(
                canonical_id=f"BCSE:{ticker}",
                name=name,
                country="Morocco",
                exchange="BCSE",
                sector_or_sic=broad_sector(sub),
                ticker=ticker,
                sub=sub or "Casablanca issuer",
                hq="Morocco",
                quote_symbol=f"{ticker}.CS",
                research={
                    "exchange_profile": urljoin("https://www.casablanca-bourse.com", issuer_a["href"]) if issuer_a else "",
                    "exchange_instrument": urljoin("https://www.casablanca-bourse.com", ticker_a["href"]) if ticker_a else "",
                },
            )
        )
    return rows


def build_brvm() -> list[Record]:
    base = "https://www.brvm.org/fr/emetteurs/societes-cotees"
    rows: list[Record] = []
    for page in range(5):
        soup = bs4.BeautifulSoup(fetch(f"{base}?page={page}", verify=False).text, "html.parser")
        for card in soup.select(".view-content .views-row"):
            title = clean(card.select_one(".title").get_text(" ", strip=True))
            detail_link = card.select_one(".visuel_sgi a")
            detail_url = urljoin(base, detail_link["href"]) if detail_link else ""
            address = clean(card.select_one(".adresse_sgi").get_text(" ", strip=True) if card.select_one(".adresse_sgi") else "")
            bp = clean(card.select_one(".bp").get_text(" ", strip=True) if card.select_one(".bp") else "")
            email = clean(card.select_one(".email_sgi").get_text(" ", strip=True) if card.select_one(".email_sgi") else "")
            website_tag = card.select_one(".site_sgi a")
            website = website_tag["href"].strip() if website_tag else ""
            try:
                detail_html = fetch(detail_url, verify=False).text if detail_url else ""
            except requests.RequestException:
                detail_html = ""
            profile = parse_brvm_profile(detail_html)
            symbol = clean(profile.get("Symbole", ""))
            if not symbol:
                continue
            country = country_from_brvm(f"{title} {bp}")
            sector = clean(profile.get("Secteur d’activités", ""))
            name = clean(profile.get("Raison sociale", "")) or re.sub(r"\s*\(.+\)$", "", title).strip()
            norm_name = unicodedata.normalize("NFKD", name).replace("’", "'").encode("ascii", "ignore").decode().upper()
            if country == "BRVM Region":
                if ".ci" in website or "IVOIRE" in norm_name:
                    country = "Cote d'Ivoire"
                elif ".sn" in website or "SENEGAL" in norm_name:
                    country = "Senegal"
                elif ".bf" in website or "BURKINA" in norm_name or "CORIS BANK INTERNATIONAL" in norm_name:
                    country = "Burkina Faso"
                elif ".bj" in website or "BENIN" in norm_name:
                    country = "Benin"
            listed = clean(profile.get("Date d’introduction à la BRVM", ""))
            year = listed[-4:] if re.search(r"\b\d{4}\b", listed) else ""
            hq = city_from_text(f"{bp} {address}", country)
            research = {"exchange_profile": detail_url}
            if email:
                research["email"] = email
            rows.append(
                Record(
                    canonical_id=f"BRVM:{symbol}",
                    name=name,
                    country=country,
                    exchange="BRVM",
                    sector_or_sic=broad_sector(sector),
                    ticker=symbol,
                    sub=sector or "BRVM issuer",
                    hq=hq,
                    website=website,
                    f=year,
                    research=research,
                )
            )
    unique = {}
    for row in rows:
        unique[row.canonical_id] = row
    return list(unique.values())


def write_records(records: Iterable[Record]) -> None:
    rows = sorted(records, key=lambda r: (r.country, r.exchange, r.ticker, r.name))
    OUT.write_text("\n".join(row.as_json() for row in rows) + "\n")
    print(f"wrote {len(rows)} records to {OUT}")


def main() -> None:
    records: list[Record] = []
    kenya = build_kenya()
    print("kenya", len(kenya))
    records.extend(kenya)
    ghana = build_ghana()
    print("ghana", len(ghana))
    records.extend(ghana)
    morocco = build_morocco()
    print("morocco", len(morocco))
    records.extend(morocco)
    brvm = build_brvm()
    print("brvm", len(brvm))
    records.extend(brvm)
    write_records(records)


if __name__ == "__main__":
    main()
