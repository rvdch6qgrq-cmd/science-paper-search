from flask import Flask, request, render_template_string
import requests
import re
from difflib import SequenceMatcher

app = Flask(__name__)
HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Поиск научной статьи</title><style>body{font:18px system-ui;background:#f6f8fb;color:#1d2736;margin:0}.wrap{max-width:740px;margin:auto;padding:24px 16px}h1{font-size:clamp(26px,6vw,38px)}form{display:grid;gap:10px;margin:22px 0}input{border:1px solid #bbc8d8;border-radius:12px;padding:16px;font-size:18px;min-width:0}button,.btn{background:#174e87;color:white;border:0;border-radius:12px;padding:16px;text-decoration:none;display:block;text-align:center;font-size:18px}.card{background:white;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin:15px 0;overflow-wrap:anywhere}.muted{color:#68788b;font-size:16px}.error{color:#a22929}</style></head><body><main class="wrap"><h1>📚 Найти научную статью</h1><p class="muted">Введите точное название или DOI. Покажем одну наиболее подходящую статью и PDF, если он доступен.</p><form method="get"><input name="q" value="{{q}}" placeholder="Название статьи или DOI" aria-label="Название статьи или DOI" required><button>Найти PDF</button></form>{% if error %}<p class="error">{{error}}</p>{% endif %}{% if item %}<article class="card"><h2>{{item.title}}</h2><p class="muted">{{item.authors}} · {{item.year}}</p>{% if item.doi %}<p class="muted">DOI: {{item.doi}}</p>{% endif %}{% if item.pdf %}<a class="btn" href="{{item.pdf}}" target="_blank" rel="noopener noreferrer">📄 Открыть PDF для сохранения</a><p class="muted">На iPhone после открытия PDF нажмите «Поделиться» → «Сохранить в Файлы».</p>{% else %}<p>Открытый PDF этой статьи пока не найден.</p>{% endif %}</article>{% elif q and not error %}<p>Точного совпадения не найдено. Проверьте название или попробуйте DOI.</p>{% endif %}</main></body></html>"""

def norm(s):
    return re.sub(r"[^a-zа-яё0-9]+"," ",(s or "").casefold()).strip()

def get_pdf(w):
    locs = [w.get("best_oa_location"),w.get("primary_location")] + (w.get("locations") or [])
    for loc in locs:
        if isinstance(loc,dict) and loc.get("is_oa") and isinstance(loc.get("pdf_url"),str) and loc["pdf_url"].startswith("https://"):
            return loc["pdf_url"]
    return None

@app.route("/")
def home():
    q = request.args.get("q","").strip()[:300]
    item,error = None,None
    if q:
        try:
            doi_match = re.search(r"10\.\d{4,9}/[^\s]+",q,re.I)
            if doi_match:
                doi = doi_match.group(0).rstrip(".,;")
                r = requests.get("https://api.openalex.org/works/https://doi.org/"+doi,timeout=18)
                works = [r.json()] if r.ok else []
            else:
                r = requests.get("https://api.openalex.org/works",params={"search":q,"per-page":25},timeout=18)
                r.raise_for_status()
                works = r.json().get("results",[])
            ranked = sorted(works,key=lambda w:SequenceMatcher(None,norm(q),norm(w.get("display_name"))).ratio(),reverse=True)
            if ranked:
                w = ranked[0]
                score = 1 if doi_match else SequenceMatcher(None,norm(q),norm(w.get("display_name"))).ratio()
                if score >= 0.72:
                    item={"title":w.get("display_name") or "Без названия","authors":", ".join(a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:5]),"year":w.get("publication_year") or "","doi":w.get("doi"),"pdf":get_pdf(w)}
        except (requests.RequestException,ValueError):
            error="Поиск временно недоступен. Попробуйте позже."
    return render_template_string(HTML,q=q,item=item,error=error)

if __name__=="__main__":
    app.run()
