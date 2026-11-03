from flask import Flask, request, render_template_string, Response, abort
import requests
import re
import socket
import ipaddress
from urllib.parse import urlparse, quote
from difflib import SequenceMatcher

app = Flask(__name__)
UA = {"User-Agent": "SciencePaperSearch/1.1 (academic open access discovery)"}
HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Найти PDF статьи</title><style>body{font:18px system-ui;background:#f6f8fb;color:#1d2736;margin:0}.wrap{max-width:740px;margin:auto;padding:24px 16px}h1{font-size:clamp(26px,6vw,38px)}form{display:grid;gap:10px;margin:22px 0}input{border:1px solid #bbc8d8;border-radius:12px;padding:16px;font-size:18px;min-width:0}button,.btn{background:#174e87;color:white;border:0;border-radius:12px;padding:16px;text-decoration:none;display:block;text-align:center;font-size:18px}.card{background:white;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin:15px 0;overflow-wrap:anywhere}.muted{color:#68788b;font-size:16px}.error{color:#a22929}</style></head><body><main class="wrap"><h1>📚 Скачать научную статью</h1><p class="muted">Введите название или DOI. Ищем один доступный PDF.</p><form method="get"><input name="q" value="{{q}}" placeholder="Название статьи или DOI" required><button>Найти PDF</button></form>{% if error %}<p class="error">{{error}}</p>{% endif %}{% if item %}<article class="card"><h2>{{item.title}}</h2><p class="muted">{{item.authors}} · {{item.year}}</p>{% if item.pdf %}<a class="btn" href="/download?doi={{item.doi|urlencode}}&amp;title={{item.title|urlencode}}">⬇ Скачать PDF</a><p class="muted">Файл будет скачан с доступного научного источника.</p>{% else %}<p>Открытый PDF пока не найден.</p>{% endif %}</article>{% elif q and not error %}<p>Подходящая статья не найдена. Проверьте название или попробуйте DOI.</p>{% endif %}</main></body></html>"""

def norm(s):
    return re.sub(r"[^a-zа-яё0-9]+"," ",(s or "").casefold()).strip()

def doi_of(q):
    m = re.search(r"10\.\d{4,9}/[^\s]+",q,re.I)
    return m.group(0).rstrip(".,;") if m else None

def openalex(q):
    doi = doi_of(q)
    if doi:
        r=requests.get("https://api.openalex.org/works/https://doi.org/"+quote(doi,safe="/"),timeout=12,headers=UA)
        return [r.json()] if r.ok else []
    r=requests.get("https://api.openalex.org/works",params={"search":q,"per-page":25},timeout=12,headers=UA)
    r.raise_for_status()
    return r.json().get("results",[])

def pdf_candidates(w):
    locs=[w.get("best_oa_location"),w.get("primary_location")]+(w.get("locations") or [])
    return list(dict.fromkeys(loc["pdf_url"] for loc in locs if isinstance(loc,dict) and loc.get("is_oa") and isinstance(loc.get("pdf_url"),str) and loc["pdf_url"].startswith("https://")))

def semantic_pdf(doi):
    if not doi: return None
    try:
        r=requests.get("https://api.semanticscholar.org/graph/v1/paper/DOI:"+quote(doi,safe="/"),params={"fields":"openAccessPdf"},headers=UA,timeout=10)
        if r.ok:
            obj=r.json().get("openAccessPdf") or {}
            url=obj.get("url")
            if isinstance(url,str) and url.startswith("https://"): return url
    except (requests.RequestException,ValueError):
        pass
    return None

def find(q):
    works=openalex(q)
    ranked=sorted(works,key=lambda w:SequenceMatcher(None,norm(q),norm(w.get("display_name"))).ratio(),reverse=True)
    if not ranked: return None
    w=ranked[0]
    if not doi_of(q) and SequenceMatcher(None,norm(q),norm(w.get("display_name"))).ratio()<0.72: return None
    doi=doi_of(w.get("doi") or "")
    urls=pdf_candidates(w)
    if not urls:
        extra=semantic_pdf(doi)
        if extra: urls.append(extra)
    return {"title":w.get("display_name") or "Статья","authors":", ".join(a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:5]),"year":w.get("publication_year") or "","doi":doi or "","pdf":bool(urls),"urls":urls}

def safe_url(url):
    p=urlparse(url)
    if p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in (None,443): return False
    try:
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (OSError,ValueError):
        return False

def fetch_pdf(url):
    for _ in range(4):
        if not safe_url(url): return None
        try:
            r=requests.get(url,headers=UA,stream=True,timeout=(7,18),allow_redirects=False)
            if r.status_code in (301,302,303,307,308):
                from urllib.parse import urljoin
                url=urljoin(url,r.headers.get("Location",""))
                r.close()
                continue
            if not r.ok:
                r.close()
                return None
            if int(r.headers.get("Content-Length","0"))>25000000:
                r.close()
                return None
            chunks=r.iter_content(chunk_size=65536)
            first=next(chunks,b"")
            if not first.lstrip().startswith(b"%PDF-"):
                r.close()
                return None
            def body():
                total=len(first)
                try:
                    yield first
                    for chunk in chunks:
                        total+=len(chunk)
                        if total>25000000: break
                        yield chunk
                finally: r.close()
            return body()
        except (requests.RequestException,ValueError):
            return None
    return None

@app.route("/")
def home():
    q=request.args.get("q","").strip()[:300]
    item,error=None,None
    if q:
        try: item=find(q)
        except (requests.RequestException,ValueError): error="Поиск временно недоступен. Попробуйте позже."
    return render_template_string(HTML,q=q,item=item,error=error)

@app.route("/download")
def download():
    doi=doi_of(request.args.get("doi","")[:250])
    if not doi: abort(400)
    try: item=find(doi)
    except (requests.RequestException,ValueError): item=None
    if not item or not item["pdf"]: return "Открытый PDF сейчас недоступен. Вернитесь к поиску.",404
    for url in item["urls"]:
        stream=fetch_pdf(url)
        if stream:
            filename=re.sub(r"[^a-zA-Z0-9._-]+","_",item["title"])[:90].strip("_")+".pdf"
            return Response(stream,mimetype="application/pdf",headers={"Content-Disposition":'attachment; filename="'+filename+'"',"X-Content-Type-Options":"nosniff"})
    return "Не удалось скачать PDF из открытых источников. Попробуйте позже.",404

if __name__=="__main__":
    app.run()
