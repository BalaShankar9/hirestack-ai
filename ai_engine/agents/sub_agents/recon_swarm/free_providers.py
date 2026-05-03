"""S18 — Free Data Providers (No API Keys).

Free sources: GitHub (60/hr), Wikipedia, SEC EDGAR, HN, Reddit, arXiv.
"""
from __future__ import annotations
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx


@dataclass
class FreeResult:
    provider: str
    success: bool
    data: Dict[str, Any]
    latency_ms: int = 0
    error: Optional[str] = None


class FreeProvider:
    name: str = "base"
    rpm: int = 60
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        raise NotImplementedError


class GitHubFree(FreeProvider):
    """GitHub API - 60/hr unauthenticated."""
    name = "github_free"
    rpm = 10
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        org = self._org(company)
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://api.github.com/orgs/{org}", headers={"Accept":"application/vnd.github.v3+json"})
                if r.status_code == 404:
                    r = await c.get(f"https://api.github.com/users/{org}")
                if r.status_code != 200:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), f"404: {org}")
                
                # Repos
                repos = await c.get(f"https://api.github.com/orgs/{org}/repos", params={"per_page":100,"sort":"updated"})
                if repos.status_code != 200:
                    repos = await c.get(f"https://api.github.com/users/{org}/repos", params={"per_page":100,"sort":"updated"})
                rl = repos.json() if repos.status_code == 200 else []
                
                stars = sum(r.get("stargazers_count",0) for r in rl)
                forks = sum(r.get("forks_count",0) for r in rl)
                langs = list(dict.fromkeys(r.get("language") for r in rl if r.get("language")))[:10]
                
                return FreeResult(self.name, True, {
                    "github_org": org, "repo_count": len(rl), "stars": stars,
                    "forks": forks, "tech_stack": langs,
                    "repos": [{"n":r.get("name"),"s":r.get("stargazers_count"),"l":r.get("language")} for r in rl[:10]],
                }, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])
    
    def _org(self, c: str) -> str:
        m = {"stripe":"stripe","openai":"openai","meta":"facebook","uber":"uber","airbnb":"airbnb"}
        return m.get(c.lower(), re.sub(r'[^a-z0-9]','',c.lower()))


class WikiFree(FreeProvider):
    """Wikipedia - free, no key."""
    name = "wikipedia_free"
    rpm = 30
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                # Search
                r = await c.get("https://en.wikipedia.org/w/api.php", params={"action":"query","list":"search","srsearch":company,"format":"json","srlimit":5})
                res = r.json().get("query",{}).get("search",[])
                if not res:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), "No results")
                
                title = res[0]["title"].replace(" ","_")
                
                # Summary
                s = await c.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title,safe='')}")
                summary = s.json() if s.status_code == 200 else {}
                
                # Get content for infobox
                p = await c.get("https://en.wikipedia.org/w/api.php", params={"action":"query","prop":"revisions","titles":title,"rvprop":"content","format":"json","rvslots":"main"})
                content = ""
                if p.status_code == 200:
                    for pg in p.json().get("query",{}).get("pages",{}).values():
                        if pg.get("revisions"):
                            content = pg["revisions"][0].get("slots",{}).get("main",{}).get("*","")
                
                def ex(f): 
                    m = re.search(rf'\|\s*{f}\s*=\s*\[?\[?([^\]|\n\r]+)', content, re.I)
                    return m.group(1).strip().replace("[[","").replace("]]","") if m else None
                
                data = {"description": summary.get("extract"), "wiki_url": f"https://en.wikipedia.org/wiki/{title}"}
                if ex("industry"): data["industry"] = ex("industry")
                if ex("headquarters"): data["hq"] = ex("headquarters")
                if ex("website"): data["website"] = ex("website")
                
                fy = re.search(r'\|\s*founded\s*=.*?(\d{4})', content)
                if fy:
                    y = int(fy.group(1))
                    if 1800 <= y <= 2030:
                        data["founded"] = y
                
                return FreeResult(self.name, True, data, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])


class SECFree(FreeProvider):
    """SEC EDGAR - public, free."""
    name = "sec_free"
    rpm = 8
    headers = {"User-Agent": "HireStack AI contact@hirestack.ai"}
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10, headers=self.headers) as c:
                # Search for CIK
                r = await c.get("https://www.sec.gov/cgi-bin/browse-edgar", params={"action":"getcompany","company":company,"type":"10-K","output":"xml","count":10})
                m = re.search(r'<CIK>(\d+)</CIK>', r.text)
                if not m:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), "No CIK")
                
                cik = m.group(1).zfill(10)
                
                # Get submissions
                s = await c.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
                data = s.json() if s.status_code == 200 else {}
                recent = data.get("filings",{}).get("recent",{})
                
                filings = [{"form":f,"date":d} for f,d in zip(recent.get("form",[])[:10], recent.get("filingDate",[])[:10])]
                
                return FreeResult(self.name, True, {
                    "ticker": data.get("tickers",[None])[0],
                    "cik": cik, "is_public": True,
                    "filings": filings,
                }, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])


class HNFree(FreeProvider):
    """HackerNews via Algolia - free."""
    name = "hackernews_free"
    rpm = 30
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://hn.algolia.com/api/v1/search", params={"query":company,"tags":"story","hitsPerPage":20})
                if r.status_code != 200:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), f"Status {r.status_code}")
                
                hits = r.json().get("hits",[])
                stories = [{"t":h.get("title"),"p":h.get("points"),"c":h.get("num_comments")} for h in hits[:15]]
                engagement = sum(s["p"] or 0 + s["c"] or 0 for s in stories)
                
                return FreeResult(self.name, True, {
                    "stories": stories, "engagement": engagement,
                    "news": [{"title":h.get("title"),"url":h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"} for h in hits[:10]],
                }, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])


class RedditFree(FreeProvider):
    """Reddit JSON API - free, no auth."""
    name = "reddit_free"
    rpm = 30
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent":"HireStack/1.0"}) as c:
                r = await c.get("https://www.reddit.com/search.json", params={"q":company,"limit":25})
                if r.status_code != 200:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), f"Status {r.status_code}")
                
                posts = r.json().get("data",{}).get("children",[])
                discussions = [{"t":p["data"].get("title"),"s":p["data"].get("score"),"sub":p["data"].get("subreddit")} for p in posts[:15]]
                subs = list(set(d["sub"] for d in discussions if d["sub"]))[:10]
                
                return FreeResult(self.name, True, {
                    "discussions": discussions, "subreddits": subs,
                }, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])


class ArxivFree(FreeProvider):
    """arXiv Atom API - free."""
    name = "arxiv_free"
    rpm = 10
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        try:
            import xml.etree.ElementTree as ET
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("http://export.arxiv.org/api/query", params={
                    "search_query": f'all:"{company}"', "start":0, "max_results":20,
                    "sortBy":"submittedDate", "sortOrder":"descending",
                })
                if r.status_code != 200:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), f"Status {r.status_code}")
                
                root = ET.fromstring(r.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                papers = []
                for e in root.findall("atom:entry", ns):
                    t = e.find("atom:title", ns)
                    p = e.find("atom:published", ns)
                    papers.append({"title": t.text if t else "", "date": p.text if p else ""})
                
                return FreeResult(self.name, True, {
                    "papers": papers[:15], "paper_count": len(papers),
                }, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])


class StackFree(FreeProvider):
    """StackOverflow API - 300/day no key."""
    name = "stackoverflow_free"
    rpm = 5
    
    async def fetch(self, company: str, **ctx) -> FreeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://api.stackexchange.com/2.3/search/advanced", params={
                    "q": company, "site": "stackoverflow", "pagesize": 20,
                })
                if r.status_code != 200:
                    return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), f"Status {r.status_code}")
                
                items = r.json().get("items",[])
                questions = [{"title":i.get("title"),"tags":i.get("tags",[])} for i in items[:15]]
                tags = list(set(t for q in questions for t in q["tags"]))[:20]
                
                return FreeResult(self.name, True, {
                    "questions": questions, "tech_tags": tags,
                }, int((time.perf_counter()-t0)*1000))
        except Exception as e:
            return FreeResult(self.name, False, {}, int((time.perf_counter()-t0)*1000), str(e)[:100])


# ─── Factory ────────────────────────────────────────────────────────────

FREE_PROVIDERS: List[type] = [
    GitHubFree, WikiFree, SECFree, HNFree,
    RedditFree, ArxivFree, StackFree,
]


async def fetch_all_free(company: str, **ctx) -> Dict[str, FreeResult]:
    """Fetch from all free providers concurrently."""
    results = {}
    for cls in FREE_PROVIDERS:
        p = cls()
        results[p.name] = await p.fetch(company, **ctx)
    return results
