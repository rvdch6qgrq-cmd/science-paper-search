from flask import Flask, request, render_template_string
import requests
import re

app = Flask(__name__)
HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Поиск научных статей</title><style>body{font:16px system-ui;background:#f6f8fb;color:#1d2736;margin:0}.wrap{max-width:850px;margin:auto;padding:28px 18px}h1{font-size:30px}form{display:flex;gap:8px;margin:22px 0}input{flex:1;min-width:0;border:1px solid #bbc8d8;border-radius:12px;padding:14px;font-size:16px}button,.btn{background:#174e87;color:white;border:0;border-radius:12px;padding:14px 17px;text-decoration:none;display:inline-block;font-size:15px}.card{background:white;border:1px solid #e2e8f0;border-radius:16px;padding:18px;margin:12px 0;overflow-wrap:anywhere}.muted{color:#68788b;font-size:14px}.btn{padding:10px 14px;margin:5px 6px 0 0}.secondary{background:#e7eef7;color:#174e87}.error{color:#a22929}@media(max-width:520px){form{flex-direction:column}}</style></head><body><main class="wrap"><h1>📚 Поиск научных статей</h1><p class="muted">Поиск по названию, автору, DOI и ключевым словам. Открытые PDF — когда доступны.</p><form method="get"><input name="q" aria-label="Поисковый запрос" value="{{ q }}" placeholder="Название статьи, DOI или автор" required><button>Найти</button></form>{% if error %}<p class="error">{{error}}</p>{% endif %}{% if q and not error %}<p class="muted">Найдено: {{items|length}}. Результаты из научного каталога OpenAlex.</p>{% endif %}{% for item in items %}<article class="card"><h3>{{item.title}}</h3><p class="muted">{{item.authors}} · {{item.year}} · {{item.journal}}</p>{% if item.doi %}<p class="muted">DOI: {{item.doi}}</p>{% endif %}{% if item.pdf %}<a class="btn" href="{{item.pdf}}" target="_blank" rel="noopener noreferrer">Открыть PDF</a>{% endif %}{% if item.url %}<a class="btn secondary" href="{{item.url}}" target="_blank" rel="noopener noreferrer">Страница статьи</a>{% endif %}{% if not item.pdf %}<p class="muted">Открытый PDF не найден в каталоге</p>{% endif %}</article>{% endfor %}<p class="muted">Доступность файлов определяется правообладателями и научными репозиториями.</p></main></body></html>"""

def safe_url(url):
    if isinstance(url,str) and url.startswith(("https://","http://")):
        return url
    return None

@app.route("/")
def home():
    q = request.args.get("q","").strip()[:300]
    items, error = [], None
    if q:
        try:
            response = requests.get("https://api.openalex.org/works",params={"search":q,"per-page":20},timeout=15,headers={"User-Agent":"SciencePaperSearch/1.0 (academic search)"})
            response.raise_for_status()
            for w in response.json().get("results",[]):
                locations = [w.get("best_oa_location") or {},w.get("primary_location") or {}] + (w.get("locations") or [])
                pdf = next((safe_url(loc.get("pdf_url")) for loc in locations if loc and safe_url(loc.get("pdf_url"))),None)
                doi = safe_url(w.get("doi"))
                items.append({"title":w.get("display_name") or "Без названия","authors":", ".join(a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:5]),"year":w.get("publication_year") or "","journal":((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "","doi":doi,"pdf":pdf,"url":doi or safe_url(w.get("id"))})
        except (requests.RequestException,ValueError):
            error = "Не удалось получить результаты. Попробуйте ещё раз позже."
    return render_template_string(HTML,q=q,items=items,error=error)

if __name__ == "__main__":
    app.run()
