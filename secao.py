"""Localiza, no texto do regulamento, o trecho que define a amostra de verificação de lastro."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from leitura import sem_acento


@dataclass
class Secao:
    texto: str                  # trecho que descreve a regra (anexo ou cláusulas)
    origem: str                 # "anexo", "clausulas" ou "nenhuma"
    titulo: str = ""
    inicio: int = 0             # posição no texto normalizado
    mencoes: list[str] = field(default_factory=list)  # outras cláusulas sobre amostragem
    avisos: list[str] = field(default_factory=list)

    @property
    def completo(self) -> str:
        """Trecho + menções (o que é lido para identificar a regra)."""
        return "\n".join([self.texto, *self.mencoes])


# termos que indicam a REGRA de amostragem (peso)
_TERMOS = [
    (r"tamanho d[ao] amostra", 4), (r"n[íi]vel de confian", 4),
    (r"margem de erro|erro (m[ée]dio|amostral|toler|m[áa]ximo)", 4),
    (r"intervalo de (retirada|sele)", 3), (r"ponto de partida", 3), (r"f[óo]rmula", 3), (r"\bz\s*[=:]", 3),
    (r"\bn\s*=", 2), (r"popula[çc][ãa]o", 2), (r"amostra", 2), (r"aleat[óo]ri|sorte", 2), (r"estratific", 2),
    (r"\b(forma|maneira) (individualizada e )?integral\b|\bintegralmente\b|\bverifica[çc][ãa]o integral"
     r"|100\s*%\s*\(cem por cento\)\s*d[oa]s? (direitos|documentos|cr[ée]ditos|t[íi]tulos)", 4),
    (r"maiores?\b", 1), (r"inadimplid", 1), (r"substitu[íi]d", 1), (r"recomprad", 1), (r"\bitens\b", 2),
    (r"lastro", 1), (r"documentos? comprobat", 1),
    # modelo "individualizada / por amostragem / com dispensa", com as regras nas políticas da gestora
    (r"modelo estat[íi]stico", 2), (r"individualizad", 1), (r"\bdispensa\b", 2),
    (r"website|pol[íi]ticas? da gestora|procedimentos para verifica[çc][ãa]o de lastro", 2),
]
# cláusulas sobre o tema que NÃO são a regra (fatores de risco, definições, obrigações genéricas)
_RE_NAO_REGRA = re.compile(
    r"^\W*(risco|“|\")|fatores? de risco|poder[áa] (conter|levar|obstar)|significa\b"
    r"|podendo contratar|poder[áa] contratar|n[ãa]o [ée] respons[áa]vel", re.I)
# obrigação genérica do prestador ("verificação da existência, integralidade e titularidade…, podendo contratar terceiros")
_RE_GENERICA = re.compile(r"podendo contratar terceiros|despesas com verifica|guarda da documenta", re.I)
# título de subseção ("Verificação do Lastro dos Direitos Creditórios")
_RE_SUBTITULO = re.compile(r"^[^.;:]{0,15}(verifica[çc][ãa]o|valida[çc][ãa]o|par[âa]metros)[^.;:]{0,30}(lastro|amostr|documentos comprobat)[^.;:]{0,60}$", re.I)
# linha de sumário: pontilhado/sublinhado ou termina em número de página
_RE_SUMARIO = re.compile(r"(\.{4,}|_{4,}|…{2,}|\s\d{1,3}\s*$)")
_RE_TITULO_ANEXO = re.compile(r"(?m)^(ANEXO|ADENDO|AP[ÊE]NDICE|SUPLEMENTO)\b[^\n]*")
_ID = r"([IVXL]+(?:\s*[-–]\s*[A-Z]\b)?|\d+)"
_RE_REF_ANEXO = re.compile(
    r"(?:verifica[çc][ãa]o d[oa] lastro|amostragem|documentos comprobat)[^\n]{0,250}?"
    r"\b(?:no|do|ao|o|conforme|nos termos do)\s+(?:Anexo|Adendo)\s+" + _ID, re.I)


def pontos(trecho: str) -> int:
    t = trecho.lower()
    return sum(peso for p, peso in _TERMOS if re.search(p, t))


def _limpa_id(s: str) -> str:
    return re.sub(r"\s", "", s).replace("–", "-").upper()


def _anexos(texto_norm: str) -> list[tuple[int, int, str]]:
    """(início, fim, título) dos anexos de verdade (ignora o sumário e as citações no meio do texto)."""
    titulos = []
    for m in _RE_TITULO_ANEXO.finditer(texto_norm):
        linha = m.group(0)
        if _RE_SUMARIO.search(linha):
            continue
        if len(linha) > 40 and not linha[:60].isupper() and \
                re.search(r"\b(deste|referente|conforme|nos termos|na forma|previst)", linha[:100], re.I):
            continue
        titulos.append(m)
    out = []
    for i, m in enumerate(titulos):
        fim = titulos[i + 1].start() if i + 1 < len(titulos) else len(texto_norm)
        titulo = " ".join(texto_norm[m.start():fim].split("\n")[:3])[:250]
        out.append((m.start(), fim, titulo))
    return out


def _id_anexo(titulo: str) -> str:
    m = re.match(r"\s*(?:ANEXO|ADENDO|AP[ÊE]NDICE)\s+" + _ID, titulo, re.I)
    return _limpa_id(m.group(1)) if m else ""


def localizar_secao(texto_norm: str) -> Secao:
    """Acha o trecho do regulamento que define a amostra de verificação de lastro.

    1) um anexo cujo título fala de verificação de lastro / amostragem, ou o anexo que as
       cláusulas de verificação de lastro citam ("na forma do Anexo III");
    2) senão, as cláusulas (parágrafos) com mais termos de regra de amostragem.
    """
    anexos = _anexos(texto_norm)
    citados = {_limpa_id(m.group(1)) for m in _RE_REF_ANEXO.finditer(texto_norm)}
    avisos: list[str] = []
    melhor = None
    for ini, fim, titulo in anexos:
        tit = sem_acento(titulo.lower())
        corpo = texto_norm[ini:fim]
        tema = "lastro" in tit or "amostr" in tit
        citado = _id_anexo(titulo) in citados
        if not (tema or citado) or len(corpo) < 200:
            continue
        if not tema and re.search(r"cobran|modelo de ap[eê]ndice|suplemento", tit):
            continue
        p = pontos(corpo[:15000]) + (6 if tema else 0)
        if melhor is None or p > melhor[0]:
            melhor = (p, ini, fim, titulo)
    if melhor and melhor[0] >= 10:
        _, ini, fim, titulo = melhor
        corpo = texto_norm[ini:fim]
        # o anexo termina no "ESTE ANEXO É PARTE INTEGRANTE DO REGULAMENTO…"
        m = re.search(r"(?i)\n[^\n]*(parte integrante|faz(endo)? parte)[^\n]*regulamento", corpo)
        if m and m.start() > 300:
            corpo = corpo[:m.start()]
        if len(corpo) > 15000:
            avisos.append("anexo muito longo: o trecho foi cortado em 15 mil caracteres")
            corpo = corpo[:15000]
        return Secao(texto=corpo.strip(), origem="anexo", titulo=titulo, inicio=ini,
                     mencoes=_mencoes(texto_norm, ini, fim), avisos=avisos)
    for c in sorted(citados):
        achado = [t for _, _, t in anexos if _id_anexo(t) == c]
        if not achado:
            avisos.append(f"o regulamento cita o Anexo {c} para a verificação de lastro, mas esse anexo não está no documento")
        else:
            avisos.append(f"o regulamento cita o Anexo {c} para a verificação de lastro, mas o Anexo {c} "
                          f"trata de outro assunto ({achado[0][:90]})")
    # o sumário lista um anexo de lastro/amostragem que não aparece no corpo do documento
    reais = {_id_anexo(t) for _, _, t in anexos}
    for m in _RE_TITULO_ANEXO.finditer(texto_norm):
        linha = m.group(0)
        if _RE_SUMARIO.search(linha) and re.search(r"lastro|amostr", sem_acento(linha.lower())):
            ident = _id_anexo(linha)
            if ident and ident not in reais and ident not in citados:
                avisos.append(f"o sumário lista \"{re.sub(r'[ ._…]{4,}.*', '', linha)[:90]}\", mas esse anexo não está "
                              "no documento publicado no Fundos.NET")

    # 2) cláusulas no corpo do regulamento
    paragrafos = texto_norm.split("\n")
    posicoes, pos = [], 0
    for p in paragrafos:
        posicoes.append(pos)
        pos += len(p) + 1
    notas = []
    sob_titulo = set()
    for i, p in enumerate(paragrafos):
        if len(p) < 120 and _RE_SUBTITULO.match(p.strip()):
            for j in range(i + 1, min(len(paragrafos), i + 6)):
                if len(paragrafos[j]) < 120 and not re.match(r"^\(?[a-z0-9]", paragrafos[j], re.I):
                    break
                sob_titulo.add(j)
    for i, p in enumerate(paragrafos):
        pl = sem_acento(p.lower())
        if not ("lastro" in pl or "documentos comprobat" in pl or "amostr" in pl or i in sob_titulo):
            continue
        if _RE_SUMARIO.search(p) and len(p) < 200:
            continue
        nota = pontos(p)
        if _RE_NAO_REGRA.search(p.strip()[:250]) or _RE_GENERICA.search(p):
            nota -= 6
        if i in sob_titulo:
            nota += 3
        if nota >= 5:
            notas.append((nota, i))
    m = re.search(r"[“\"](Par[âa]metros de (Amostragem|Verifica[çc][ãa]o)[^”\"]*)[”\"]", texto_norm)
    if m:
        avisos.append(f"o regulamento define “{m.group(1)}”, mas o anexo correspondente não foi encontrado no documento")
    if not notas:
        return Secao(texto="", origem="nenhuma", avisos=avisos)
    notas.sort(key=lambda x: (-x[0], x[1]))
    escolhidos = sorted({i for _, i in notas[:6]})
    # inclui os subitens (a), (b)… logo abaixo de cada cláusula escolhida
    extra = set()
    for i in escolhidos:
        for j in range(i + 1, min(len(paragrafos), i + 12)):
            if re.match(r"^(\(?[a-z]{1,4}\)|[ivxl]+\)|\d+(\.\d+){2,})", paragrafos[j], re.I) and pontos(paragrafos[j]) > 0:
                extra.add(j)
            else:
                break
    sel = sorted(set(escolhidos) | extra)
    return Secao(texto="\n".join(paragrafos[i] for i in sel).strip(), origem="clausulas",
                 inicio=posicoes[sel[0]], mencoes=[paragrafos[i] for _, i in notas[6:9]], avisos=avisos)


def _mencoes(texto_norm: str, ini: int, fim: int) -> list[str]:
    """Cláusulas fora do anexo que também tratam da amostra (ex.: '100% dos inadimplidos')."""
    out, pos = [], 0
    for linha in texto_norm.split("\n"):
        inicio_linha, pos = pos, pos + len(linha) + 1
        if ini <= inicio_linha < fim:
            continue
        p = linha.strip()
        pl = p.lower()
        if "amostr" not in pl and "lastro" not in pl:
            continue
        if len(p) < 60 or _RE_NAO_REGRA.search(p[:250]) or _RE_SUMARIO.search(p[-6:]):
            continue
        if pontos(p) >= 7:
            out.append(p)
    return out[:5]


# ---------------------------------------------------------------- FIC FIDC (pela leitura do regulamento)

_RE_TITULO_FIC = re.compile(
    # \s* tolera palavras grudadas pelo PDF ("FUNDO DEINVESTIMENTO")
    r"\b(fundo\s*de\s*investimento|fi)\s+em\s+cotas\s+de\s+"
    r"(fidcs?\b|(classes?\s*de\s*)?fundos?\s*de\s*investimento\s*em\s*direitos\s*credit)"
    r"|\bfic[\s-]*fidc\b", re.I)
_RE_POLITICA_FIC = re.compile(
    r"(classe|fundo)\s+(investe|aplica|alocar[áa])\s+(preponderantemente|majoritariamente|exclusivamente|no\s+m[íi]nimo[^.]{0,40})"
    r"\s+(seus\s+recursos\s+)?em\s+cotas\s+de\s+(outros\s+|classes\s+de\s+)?(fidcs?|fundos\s+de\s+investimento\s+em\s+direitos)", re.I)


def eh_fic(texto_norm: str) -> tuple[bool, str]:
    """(é FIC-FIDC?, trecho que mostra). Olha o título do regulamento e a política de investimento.

    O título é procurado logo depois de "REGULAMENTO DO/DA" (as assinaturas eletrônicas no topo do PDF citam
    cotistas que são FIC e não valem como título).
    """
    t = re.sub(r"\s+", " ", texto_norm)
    for m in re.finditer(r"regulamento\s+d[oa]\s+", t[:20000], re.I):
        titulo = t[m.start():m.start() + 260]
        titulo = re.split(r"CNPJ|DEFINI|Esse documento foi assinado", titulo, maxsplit=1, flags=re.I)[0]
        if _RE_TITULO_FIC.search(titulo):
            return True, titulo.strip()
        break
    m = _RE_POLITICA_FIC.search(t)
    if m:
        return True, t[max(0, m.start() - 60):m.end() + 80].strip()
    return False, ""
