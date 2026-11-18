"""Generate the full Imweb widget; cards are also present before JavaScript."""
from collections import Counter
from html import escape
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
WIDGETS = ROOT / 'widgets'


def build() -> dict:
    data = json.loads((ROOT / 'data/sowhat_archive.json').read_text(encoding='utf-8'))['items']
    cards = []
    for i, item in enumerate(data):
        title = escape(item['title'])
        image = f'<img src="{escape(item["image"], quote=True)}" alt="{title}" width="630" height="360" loading="{"eager" if i < 3 else "lazy"}" decoding="async">' if item.get('image') else '<span class="swa-cover-fallback">SO WHAT?</span>'
        badge = '<span class="swa-latest">LATEST</span>' if i == 0 else ''
        volume = 'Vol. ' + str(item['volume']).zfill(3) if item.get('volume') else 'SO WHAT LETTER'
        cards.append(f'<article class="swa-card"><a href="{escape(item["url"], quote=True)}" target="_blank" rel="noopener" aria-label="{title} — 스티비 원문 새 창"><div class="swa-cover">{image}{badge}</div><p class="swa-meta"><span class="swa-volume">{volume}</span><i>·</i><time datetime="{item["date"]}">{item["date"].replace("-", ".")}</time></p><h2>{title}</h2></a></article>')
    counts = Counter(x['date'][:7] for x in data)
    month_links = f'<button class="swa-month-link" type="button" aria-pressed="true">전체 뉴스레터 <span>{len(data)}</span></button>'
    for key, value in list(counts.items())[:3]:
        month_links += f'<button class="swa-month-link" type="button" aria-pressed="false">{key[:4]}년 {int(key[5:])}월 <span>{value}</span></button>'
    structured = {'@context':'https://schema.org','@type':'CollectionPage','name':'쏘왓레터 모아보기','url':'https://bestexit.co.kr/sowhat-archives','mainEntity':{'@type':'ItemList','numberOfItems':len(data),'itemListElement':[{'@type':'ListItem','position':i+1,'name':x['title'],'url':x['url']} for i,x in enumerate(data)]}}
    template = (WIDGETS / 'sowhat-archive-template.html').read_text(encoding='utf-8')
    markup = template.replace('__COUNT__', str(len(data))).replace('__CARDS__','\n'.join(cards)).replace('__MONTH_LINKS__', month_links).replace('__DATA__', json.dumps(data,ensure_ascii=False).replace('<','\\u003c')).replace('__STRUCTURED__',json.dumps(structured,ensure_ascii=False).replace('<','\\u003c'))
    css = (WIDGETS / 'sowhat-archive.css').read_text(encoding='utf-8')
    js = (WIDGETS / 'sowhat-archive.js').read_text(encoding='utf-8')
    result = '<style>\n' + css + '\n</style>\n' + markup + '\n<script>\n' + js + '\n</script>\n'
    (WIDGETS / 'sowhat-archives-code.txt').write_text(result,encoding='utf-8')
    preview = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex"><title>쏘왓레터 모아보기 · 베스트엑싯</title><style>body{margin:0;background:#fff}</style></head><body>' + result + '</body></html>'
    (WIDGETS / 'sowhat-archives-preview.html').write_text(preview,encoding='utf-8')
    return {'items':len(data),'characters':len(result)}


if __name__ == '__main__':
    print(json.dumps(build()))
