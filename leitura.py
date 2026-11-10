"""Leitura do regulamento: extrai e normaliza o texto do PDF/DOCX."""
from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# ---------------------------------------------------------------- texto

def texto_pdf(caminho: Path) -> str:
    import pymupdf
    with pymupdf.open(caminho) as doc:
        return "\n".join(p.get_text() for p in doc)


def texto_docx(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        txt = txt.replace(a, b)
    return txt


def extrair_texto(caminho: Path) -> str:
    ext = caminho.suffix.lower()
    if ext == ".pdf":
        return texto_pdf(caminho)
    if ext == ".docx":
        return texto_docx(caminho)
    if ext == ".zip":  # alguns administradores mandam o regulamento zipado
        import tempfile
        with zipfile.ZipFile(caminho) as z, tempfile.TemporaryDirectory() as tmp:
            nomes = [n for n in z.namelist() if n.lower().endswith((".pdf", ".docx"))]
            partes = []
            for n in nomes:
                destino = Path(tmp) / f"doc{len(partes)}{Path(n).suffix.lower()}"
                destino.write_bytes(z.read(n))
                partes.append(extrair_texto(destino))
            return "\n".join(partes)
    raise ValueError(f"formato de regulamento não suportado: {ext}")


# Rodapé/cabeçalho repetido em toda página e número de página solto
_RE_NUM_PAGINA = re.compile(r"^\s*(p[áa]gina\s+)?\d{1,3}(\s*(de|/)\s*\d{1,3})?\s*$", re.I)


def normalizar(texto: str) -> str:
    """Junta as linhas quebradas do PDF em parágrafos (preserva as quebras de item/cláusula)."""
    linhas = [l.strip() for l in texto.replace("\r", "").split("\n")]
    # cabeçalhos repetidos (aparecem em muitas páginas) atrapalham a leitura
    contagem: dict[str, int] = {}
    for l in linhas:
        if 15 < len(l) < 200:
            contagem[l] = contagem.get(l, 0) + 1
    repetidas = {l for l, n in contagem.items() if n >= 8 and not re.search(r"amostr|lastro", l, re.I)}

    saida: list[str] = []
    atual = ""
    for l in linhas:
        if not l or _RE_NUM_PAGINA.match(l) or l in repetidas:
            if not l and atual and re.search(r"[.;:]$", atual):
                saida.append(atual)
                atual = ""
            continue
        novo_item = re.match(r"^(\(?[a-z0-9]{1,4}\)|[ivxl]+\)|\d+(\.\d+)*\.?|art(igo)?\.?\s*\d+|cl[áa]usula|par[áa]grafo|§|anexo\s+[ivxl\d]+|cap[íi]tulo)\b", l, re.I)
        if atual and (novo_item or re.search(r"[.;:]$", atual) and l[:1].isupper()):
            saida.append(atual)
            atual = l
        else:
            if atual.endswith("-") and not atual.endswith(" -"):
                atual = atual[:-1] + l
            else:
                atual = f"{atual} {l}" if atual else l
    if atual:
        saida.append(atual)
    texto = "\n".join(saida)
    texto = re.sub(r"[ \t]+", " ", texto)
    # itens soltos ("(a)" numa linha e o texto na seguinte) voltam a ficar juntos
    texto = re.sub(r"(?m)^(\(?[a-z0-9]{1,4}\)|\d+(\.\d+)+\.?)\n", r"\1 ", texto)
    return texto


