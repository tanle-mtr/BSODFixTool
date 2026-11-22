#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 3z9w.com 抓取蓝屏代码库，生成离线 JSON 数据库。"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

BASE = "https://www.3z9w.com"
HUB_URL = f"{BASE}/bsod-codes"
SITEMAP_URL = f"{BASE}/bsod-sitemap.xml"
OUT = Path(__file__).with_name("bsod_data.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BSODFixTool/1.0 (+offline database builder)"


def fetch(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - 网络重试需要捕获所有异常
            last = exc
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"抓取失败: {url} -> {last}")


def text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_hub(html: str) -> tuple[dict[str, dict], list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    catalog: dict[str, dict] = {}
    categories: list[dict] = []
    current = ""
    for section in soup.select("section.zbs-hub-cat"):
        h2 = section.find("h2")
        current = text(h2) if h2 else "未分类"
        categories.append({"name": current})
        for item in section.select("a.zbs-hub-item"):
            b = item.find("b")
            span = item.find("span")
            code = text(b).upper().replace("0X", "0x")
            name = text(span).upper()
            if not code:
                continue
            catalog[code] = {
                "code": code,
                "name": name,
                "category": current,
                "source_url": item.get("href", ""),
                "keywords": [k for k in text(item).split() if k],
            }
    return catalog, categories


def parse_detail(html: str, meta: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    data = dict(meta)

    code_node = soup.select_one("span.zbs-code")
    if code_node:
        data["code"] = text(code_node).upper().replace("0X", "0x")

    sev = soup.select_one("span.zbs-sev")
    data["severity"] = text(sev)

    cat = soup.select_one("span.zbs-cat")
    if cat:
        data["category"] = text(cat)

    h1 = soup.select_one("h1")
    data["title"] = text(h1)

    lead = soup.select_one("p.zbs-lead")
    data["summary"] = text(lead)

    data["quick_tips"] = [text(li) for li in soup.select("ul.zbs-quick li") if text(li)]

    params = []
    for tr in soup.select("table.zbs-table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            params.append({"name": text(th), "desc": text(td)})
    data["params"] = params

    causes = []
    for cause in soup.select("div.zbs-cause"):
        strong = cause.find("strong")
        p = cause.find("p")
        tag = cause.find("span", class_=re.compile(r"zbs-tag"))
        causes.append(
            {
                "title": text(strong),
                "desc": text(p),
                "level": text(tag) or "未知",
            }
        )
    data["causes"] = causes

    steps = []
    for li in soup.select("ol.zbs-steps > li"):
        strong = li.find("strong")
        p = li.find("p")
        step_text = text(li)
        if strong:
            title = text(strong)
            desc = step_text[len(title):].strip(" :：") if step_text.startswith(title) else text(p)
        else:
            title, desc = "排查步骤", step_text
        steps.append({"title": title, "desc": desc})
    data["steps"] = steps

    warnings = []
    for warn_card in soup.select("section.zbs-warn"):
        for li in warn_card.select("li"):
            if text(li):
                warnings.append(text(li))
    data["warnings"] = warnings

    faqs = []
    for faq in soup.select("details.zbs-faq"):
        q = faq.find("summary")
        p = faq.find("p")
        faqs.append({"q": text(q), "a": text(p) or text(faq)})
    data["faqs"] = faqs

    related = []
    for rel in soup.select("div.zbs-rel > a"):
        b, span = rel.find("b"), rel.find("span")
        if b and span:
            related.append({"code": text(b).upper().replace("0X", "0x"), "name": text(span).upper()})
    data["related"] = related

    disclaimer = soup.select_one("p.zbs-disclaimer")
    data["disclaimer"] = text(disclaimer)

    data["source_url"] = data.get("source_url") or ""
    data["detail_url"] = data.get("detail_url", "")
    return data


def main() -> None:
    print("[1/3] 抓取代码库目录...")
    hub_html = fetch(HUB_URL)
    catalog, categories = parse_hub(hub_html)
    print(f"  目录条目: {len(catalog)}, 分类: {len(categories)}")

    print("[2/3] 读取 sitemap...")
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>(.*?)</loc>", sitemap)
    detail_urls = [u for u in urls if re.search(r"/bsod/0x[0-9a-fA-F]+/?$", u)]
    print(f"  详情页: {len(detail_urls)}")

    print("[3/3] 抓取详情页...")
    entries: list[dict] = []
    for idx, url in enumerate(detail_urls, 1):
        code_match = re.search(r"(0x[0-9a-fA-F]+)", url)
        if not code_match:
            continue
        code = code_match.group(1).upper().replace("0X", "0x")
        meta = catalog.get(code, {"code": code, "name": "", "category": "未分类", "keywords": []})
        try:
            entry = parse_detail(fetch(url), meta)
            entry["detail_url"] = url
            entries.append(entry)
            print(f"  [{idx:02d}/{len(detail_urls)}] {entry['code']} {entry['name']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{idx:02d}/{len(detail_urls)}] {code} 失败: {exc}")
        time.sleep(0.12)

    entries.sort(key=lambda e: e["code"])
    payload = {
        "source": BASE,
        "source_pages": [HUB_URL, f"{BASE}/bsod", SITEMAP_URL],
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(entries),
        "categories": categories,
        "entries": entries,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成: {OUT} ({len(entries)} 条)")


if __name__ == "__main__":
    main()
