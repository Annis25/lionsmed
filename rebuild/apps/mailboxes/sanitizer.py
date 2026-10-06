"""Rendu sûr d'un e-mail HTML reçu.

Le HTML d'origine n'est jamais stocké ni affiché. Il est relu balise par balise et réécrit
depuis une liste blanche : seules des balises de mise en forme simples ressortent, sans aucun
attribut d'origine. Scripts, styles, cadres, formulaires et images disparaissent — une image
distante serait un traceur d'ouverture. Les liens ne gardent qu'une adresse http(s) ou mailto
complète, revalidée, et s'ouvrent dans un nouvel onglet sans transmettre de référent.

Le texte passe toujours par html.escape : la sortie ne contient que des balises écrites ici.
"""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

# Balise d'origine → balise émise. Titres et tableaux de mise en page deviennent de simples
# blocs : un e-mail ne doit ni ajouter de titre à la page ni imposer sa grille à un mobile.
_EMIT = {
    "p": "p", "div": "div", "blockquote": "blockquote", "pre": "pre", "ul": "ul", "ol": "ol", "li": "li",
    "b": "strong", "strong": "strong", "i": "em", "em": "em", "u": "u", "s": "s", "strike": "s", "del": "s",
    "sub": "sub", "sup": "sup", "small": "small", "code": "code",
    "h1": "p", "h2": "p", "h3": "p", "h4": "p", "h5": "p", "h6": "p",
    "table": "div", "tr": "div", "td": "div", "th": "div", "center": "div", "section": "div", "article": "div",
    "header": "div", "footer": "div", "main": "div", "address": "div", "dl": "div", "dt": "div", "dd": "div",
    "a": "a",
}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_VOID = {"br": "<br>", "hr": "<hr>"}
# Contenu entièrement ignoré, texte compris.
_DROPPED = {"script", "style", "head", "title", "iframe", "object", "noscript", "template", "svg", "math",
            "select", "textarea", "button", "audio", "video", "canvas", "applet", "frameset", "map", "datalist"}
_BLOCKS = {"p", "div", "blockquote", "pre", "ul", "ol", "li", "br", "hr"}
_MAX_DEPTH = 40
MAX_HTML = 300_000
MAX_TEXT = 200_000


def safe_link(value):
    """Adresse d'un lien si elle est sûre et complète, sinon chaîne vide."""
    url = "".join(ch for ch in (value or "") if ch > " " and ch != "\x7f")[:2000]
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() in {"http", "https"} and parts.netloc:
        return url
    if parts.scheme.lower() == "mailto" and "@" in parts.path:
        return url
    return ""


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []      # HTML réécrit
        self.text = []     # même contenu en texte brut
        self.stack = []    # balises émises encore ouvertes : (balise d'origine, balise émise)
        self.dropping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROPPED:
            self.dropping += 1
            return
        if self.dropping:
            return
        if tag in _VOID:
            self.out.append(_VOID[tag]); self.text.append("\n")
            return
        if tag == "img":
            alt = " ".join((dict(attrs).get("alt") or "").split())[:120]
            if alt:
                self._data(f"[Image : {alt}]")
            return
        emitted = _EMIT.get(tag)
        if not emitted or len(self.stack) >= _MAX_DEPTH:
            return
        if emitted == "a":
            href = safe_link(dict(attrs).get("href"))
            if not href:
                return
            self.out.append(f'<a href="{escape(href, quote=True)}" rel="noopener noreferrer nofollow" target="_blank">')
        else:
            self.out.append(f"<{emitted}>")
            if tag in _HEADINGS:
                self.out.append("<strong>")
            if emitted in _BLOCKS:
                self.text.append("\n")
        self.stack.append((tag, emitted))

    def handle_startendtag(self, tag, attrs):
        if tag in _DROPPED:
            return  # <script/> ne doit pas ouvrir une zone ignorée sans fin
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and tag != "img":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in _DROPPED:
            self.dropping = max(self.dropping - 1, 0)
            return
        if self.dropping or not any(opened == tag for opened, _ in self.stack):
            return
        while self.stack:
            opened, emitted = self.stack.pop()
            self._close(opened, emitted)
            if opened == tag:
                break

    def _close(self, opened, emitted):
        if opened in _HEADINGS:
            self.out.append("</strong>")
        self.out.append(f"</{emitted}>")
        if emitted in _BLOCKS:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.dropping:
            self._data(data)

    def _data(self, data):
        data = data.replace("\x00", "")
        self.out.append(escape(data, quote=False))
        self.text.append(data)

    def finish(self):
        while self.stack:
            self._close(*self.stack.pop())


def _run(html):
    cleaner = _Cleaner()
    try:
        cleaner.feed((html or "")[:MAX_HTML * 4])
        cleaner.close()
    except Exception:
        # Balisage que l'analyseur refuse : on garde ce qui a été réécrit jusque-là.
        pass
    cleaner.finish()
    return cleaner


def _tidy(text):
    lines = [" ".join(line.split()) for line in text.replace("\r", "\n").split("\n")]
    compact, blank = [], False
    for line in lines:
        if line:
            compact.append(line); blank = False
        elif compact and not blank:
            compact.append(""); blank = True
    return "\n".join(compact).strip()[:MAX_TEXT]


def clean_html(html):
    """HTML réécrit, sûr à afficher tel quel. Vide si le message n'a aucun texte visible."""
    cleaner = _run(html)
    out = "".join(cleaner.out)
    # Trop long pour être coupé sans casser l'imbrication des balises : le texte brut prend le relais.
    if not "".join(cleaner.text).strip() or len(out) > MAX_HTML:
        return ""
    return out


def html_to_text(html):
    return _tidy("".join(_run(html).text))


def clean_text(text):
    """Texte brut stockable : sans octet nul, fins de ligne normalisées, longueur bornée."""
    return (text or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()[:MAX_TEXT]
