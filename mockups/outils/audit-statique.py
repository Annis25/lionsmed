"""Contrôles hors navigateur, sans dépendance ; aucune requête réseau."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import re,json,hashlib
R=Path(__file__).resolve().parents[1]
class Parser(HTMLParser):
 def __init__(self,s):
  super().__init__();self.ids=[];self.refs=[];self.imgs=[];self.scripts=[];self.forms=[];self.feed(s)
 def handle_starttag(self,t,a):
  d=dict(a)
  if 'id' in d:self.ids.append(d['id'])
  if t in ['a','link','script']:
   u=d.get('href',d.get('src',''))
   if u:self.refs.append(u)
  if t=='img':self.imgs.append(d)
  if t=='script':self.scripts.append(d)
  if t=='form':self.forms.append(d)
files=[p for p in R.rglob('*.html') if not any(x in p.relative_to(R).parts for x in ['_backup','outils','validation'])]
errors=[];images=[];headers={};footers={};titles={};forms=0
for p in files:
 s=p.read_text();clean=re.sub(r'<!--.*?-->','',s,flags=re.S);pa=Parser(clean);rel=str(p.relative_to(R))
 for ref in pa.refs:
  u=urlsplit(ref)
  if u.scheme or u.netloc:continue
  target=(p.parent/unquote(u.path) if u.path else p).resolve()
  if not target.exists():errors.append([rel,'fichier absent',ref]);continue
  if u.fragment and target.suffix=='.html' and unquote(u.fragment) not in Parser(target.read_text()).ids:errors.append([rel,'ancre absente',ref])
  if ref=='#':errors.append([rel,'lien vide'])
 for i in pa.imgs:
  for attr in ['alt','width','height']:
   if attr not in i:errors.append([rel,'image sans '+attr,i.get('src')])
  if i.get('src') and not urlsplit(i['src']).scheme:
   sources=[i['src']]+[v.strip().split()[0] for v in i.get('srcset','').split(',') if v.strip()]
   for src in set(sources):
    if not (p.parent/src).exists():images.append({'page':rel,'src':src,'attendu':src.startswith('assets/images/tmp-axe-')})
 for form in pa.forms:
  forms+=1
  if form.get('action')!='#' or 'data-maquette' not in form:errors.append([rel,'formulaire non bloqué'])
 if len(re.findall(r'<h1\b',clean))!=1:errors.append([rel,'nombre de h1'])
 if re.search(r'\sstyle=|\son(?:click|change|submit|load|error)=',clean):errors.append([rel,'code inline'])
 if any('src' not in d and d.get('type')!='application/ld+json' for d in pa.scripts):errors.append([rel,'script inline'])
 for script in re.findall(r'<script type="application/ld\+json">(.*?)</script>',s,re.S):
  try:json.loads(script)
  except:errors.append([rel,'JSON-LD invalide'])
 for term in ['name="description"','rel="canonical"','noindex','property="og:image"','name="twitter:card"']:
  if term not in s:errors.append([rel,'SEO manquant',term])
 title=re.search('<title>(.*?)</title>',s,re.S).group(1)
 if title in titles:errors.append([rel,'title dupliqué',titles[title]])
 titles[title]=rel
 if p.parent==R:
  for name,target in [('EN-TÊTE',headers),('PIED DE PAGE',footers)]:
   block=re.search(r'<!-- ══ '+name+r' PARTAGÉ.*?<!-- ══ FIN '+name+r' PARTAGÉ ══ -->',s,re.S)
   if not block:errors.append([rel,'include manquant',name]);continue
   normalized=block.group().replace(' actif','').replace(' aria-current="page"','')
   target[rel]=hashlib.sha256(normalized.encode()).hexdigest()
if len(set(headers.values()))!=1:errors.append(['global','en-têtes divergents'])
if len(set(footers.values()))!=1:errors.append(['global','pieds de page divergents'])
report={'pages':len(files),'forms':forms,'errors':errors,'images_attendues':images,'header_hashes':headers,'footer_hashes':footers}
(R/'validation/statique.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'pages':len(files),'forms':forms,'errors':errors,'images_attendues':images},ensure_ascii=False,indent=2))
