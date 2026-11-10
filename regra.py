"""Interpreta o trecho do regulamento e monta a regra de amostragem (parâmetros estruturados).

A leitura é por padrões de texto: cobre os modelos de anexo mais comuns (fórmula com z, p e
erro, verificação integral, N maiores por cedente, 100% dos inadimplidos/substituídos…).
O que não for reconhecido vira uma *pendência* e o fundo vai para revisão humana.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

from leitura import sem_acento

# z de cada nível de confiança (distribuição normal, bicaudal)
Z_CONFIANCA = {80: 1.282, 85: 1.440, 90: 1.645, 95: 1.960, 98: 2.326, 99: 2.576}


@dataclass
class Regra:
    metodo: str = "nao_identificado"  # formula_cochran | formula_yamane | integral | quantidade_fixa | percentual | nao_identificado
    z: float | None = None
    confianca: float | None = None     # 0.95
    p: float | None = None             # 0.5
    erro: float | None = None          # 0.058
    erro_faixa: tuple[float, float] | None = None  # "entre 5% e 10%"
    quantidade: int | None = None      # amostra de N itens
    percentual: float | None = None    # amostra de X% dos itens
    minimo: int | None = None
    maximo: int | None = None
    limite_integral: int | None = None  # população até esse tamanho: verifica tudo
    arredondamento: str = "cima"
    populacao: list[str] = field(default_factory=list)       # a_vencer, vencidos, recomprados, substituidos, adquiridos_periodo
    integral_categorias: list[str] = field(default_factory=list)  # inadimplidos, substituidos, recomprados (100%)
    maiores_por_grupo: dict | None = None  # {"grupo": "cedente", "n_grupos": 5, "n_itens": 3, "bases": [...]}
    subamostra_i_max: int | None = None    # "Amostra (I)": até X itens dos inadimplidos/substituídos dentro da quantidade total
    maiores_incluir: int | None = None     # os N maiores DCs entram sempre
    maiores_excluir: int | None = None     # os N maiores DCs ficam fora da base
    maiores_excluir_pct: float | None = None
    selecao: str = "sistematica"           # sistematica (intervalo K) | aleatoria
    periodicidade: str | None = None
    pendencias: list[str] = field(default_factory=list)   # o que impede de usar a regra sem revisão
    observacoes: list[str] = field(default_factory=list)  # informativo
    regra_externa: bool = False  # o regulamento remete às políticas/procedimentos da gestora ou administradora
    evidencias: dict[str, str] = field(default_factory=dict)  # campo -> frase do regulamento

    @property
    def confiabilidade(self) -> str:
        if self.metodo == "nao_identificado":
            return "baixa"
        if self.pendencias:
            return "media"
        return "alta"

    def para_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 6)
            elif isinstance(v, tuple):
                d[k] = [round(x, 6) for x in v]
        d["confiabilidade"] = self.confiabilidade
        return d


# ---------------------------------------------------------------- utilidades de texto

def _num(s: str) -> float:
    s = s.strip().replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _frase(texto: str, pos: int, raio: int = 220) -> str:
    ini = max(texto.rfind(".", 0, pos - 5), texto.rfind("\n", 0, pos), pos - raio)
    fim_p = texto.find(".", pos)
    fim = min(x for x in (fim_p if fim_p >= 0 else len(texto), texto.find("\n", pos) if texto.find("\n", pos) >= 0 else len(texto), pos + raio))
    return re.sub(r"\s+", " ", texto[ini + 1:fim + 1]).strip()


def preparar(texto: str) -> str:
    """Normaliza símbolos matemáticos (𝑁, 𝑧², 𝑀𝐸), aspas e traços para facilitar os padrões."""
    t = unicodedata.normalize("NFKC", texto)
    t = t.replace("–", "-").replace("—", "-").replace("−", "-").replace("“", '"').replace("”", '"')
    t = t.replace(" ", " ")
    return t


_GRUPOS = {"cedente": "cedente", "sacado": "sacado", "devedor": "sacado", "endossante": "cedente",
           "originador": "cedente", "emitente": "sacado"}


def _grupo(palavra: str) -> str:
    p = sem_acento(palavra.lower())
    for k, v in _GRUPOS.items():
        if p.startswith(k):
            return v
    return p


# ---------------------------------------------------------------- interpretação

def interpretar(texto_secao: str) -> Regra:
    r = Regra()
    if not texto_secao.strip():
        r.pendencias.append("o regulamento não traz regra de verificação de lastro / amostragem")
        return r
    t = preparar(texto_secao)
    tl = t.lower()
    ts = sem_acento(tl)

    # ---- parâmetros estatísticos
    m = re.search(r"\bz\b\s*(?:\([^)]{0,40}\))?\s*[=:][^\n\d]{0,40}?(\d+[,.]\d+)", t, re.I)
    if m:
        r.z = _num(m.group(1)); r.evidencias["z"] = _frase(t, m.start())
    m = re.search(r"(\d{2}(?:[,.]\d+)?)\s*%\s*(?:\([^)]{0,40}\)\s*)?(?:de\s+)?(?:n[íi]vel|intervalo|grau)\s+de\s+confian", t, re.I) \
        or re.search(r"(?:n[íi]vel|intervalo|grau)\s+de\s+confian[çc]a\s+(?:de\s+)?(\d{2}(?:[,.]\d+)?)\s*%", t, re.I)
    if m:
        r.confianca = round(_num(m.group(1)) / 100, 6); r.evidencias["confianca"] = _frase(t, m.start())
        if r.z is None:
            r.z = Z_CONFIANCA.get(round(r.confianca * 100))
            if r.z is None:
                r.pendencias.append(f"nível de confiança de {r.confianca:.0%} sem z tabelado: informe o z")
    m = re.search(r"(?<![a-z])p\b[^=\n:%]{0,50}[=:]\s*(\d+(?:[,.]\d+)?)\s*%", t, re.I) \
        or re.search(r"propor[çc][ãa]o[^.\n%]{0,60}?(\d+(?:[,.]\d+)?)\s*%", t, re.I)
    if m:
        r.p = round(_num(m.group(1)) / 100, 6); r.evidencias["p"] = _frase(t, m.start())
    m = re.search(r"(?:\bME\b|\bE0?\b|\bEo\b|erro\s+m[ée]dio|margem\s+de\s+erro(?:\s+amostral)?|erro\s+amostral(?:\s+toler[áa]vel)?|erro\s+m[áa]ximo|erro\s+estimado)"
                  r"[^\d\n%]{0,30}?(\d+(?:[,.]\d+)?)\s*%(?:\s*\([^)]*\))?(\s*(?:e|a)\s*(\d+(?:[,.]\d+)?)\s*%)?", t, re.I)
    if m:
        if m.group(3):
            r.erro_faixa = (round(_num(m.group(1)) / 100, 6), round(_num(m.group(3)) / 100, 6))
        else:
            r.erro = round(_num(m.group(1)) / 100, 6)
        r.evidencias["erro"] = _frase(t, m.start())
    m2 = re.search(r"entre\s+(\d+(?:[,.]\d+)?)\s*%[^%]{0,40}?e\s+(\d+(?:[,.]\d+)?)\s*%", t, re.I)
    if m2 and "erro" in tl[max(0, m2.start() - 120):m2.start()]:
        r.erro_faixa = (round(_num(m2.group(1)) / 100, 6), round(_num(m2.group(2)) / 100, 6)); r.erro = None
        r.evidencias["erro"] = _frase(t, m2.start())

    tem_formula_cochran = bool(re.search(r"z\s*(²|2|\^\s*2)", t) and re.search(r"\(\s*n\s*-\s*1\s*\)", tl))
    tem_formula_yamane = bool(re.search(r"1\s*\+\s*\(?\s*n\s*[*x×.]?\s*\(?\s*e", tl)) or \
        bool(re.search(r"n\s*=\s*n\s*/\s*\(?\s*1\s*\+", tl))

    # ---- verificação integral
    padrao_integral = re.search(
        r"(forma|maneira)\s+(individualizada\s+e\s+)?integral\b|\bintegralmente\b|verifica[çc][ãa]o\s+integral"
        r"|100\s*%\s*(\([^)]*\)\s*)?d[oa]s?\s+(direitos\s+credit[óo]rios|documentos\s+comprobat[óo]rios|t[íi]tulos|cr[ée]ditos)"
        r"(?!\s+(inadimplid|vencid|substitu|recomprad))", t, re.I)
    if padrao_integral:
        r.evidencias["integral"] = _frase(t, padrao_integral.start())

    # ---- quantidade fixa / percentual / mínimo / máximo
    m = re.search(r"amostra\s+(?:m[íi]nima\s+)?(?:de\s+)?(?:at[ée]\s+)?(\d+)\s*(?:\([^)]*\)\s*)?(itens|direitos|documentos|t[íi]tulos|cr[ée]ditos|opera)", t, re.I)
    if m and "até" not in m.group(0).lower() and "ate " not in sem_acento(m.group(0).lower()):
        r.quantidade = int(m.group(1)); r.evidencias["quantidade"] = _frase(t, m.start())
    m = re.search(r"amostra\s+total[^.\d]{0,40}?(\d+)\s*(?:\([^)]*\)\s*)?itens", t, re.I)
    if m:
        r.quantidade = int(m.group(1)); r.evidencias["quantidade"] = _frase(t, m.start())
        # modelo "Amostra (I)" (inadimplidos e substituídos, até X itens) + "Amostra (A)" (a vencer, o restante)
        mi = re.search(r"amostra\s+de\s+at[ée]\s+(\d+)\s*(?:\([^)]*\)\s*)?itens[^.]{0,80}amostra\s*\(\s*i\s*\)", t, re.I)
        if mi and re.search(r"amostra\s*\(\s*a\s*\)[^.;]{0,80}a\s+vencer", t, re.I):
            r.subamostra_i_max = int(mi.group(1)); r.evidencias["subamostra_i_max"] = _frase(t, mi.start(), 300)
            r.populacao = ["a_vencer"]
        elif re.search(r"grupo\s+a\b|amostra\s*\(i\)|distribu[íi]d[oa]s?\s+da\s+seguinte\s+forma", tl):
            r.pendencias.append("a amostra total é dividida em grupos/subamostras: confira a distribuição dos itens "
                                "entre os grupos descritos no trecho")
    m = re.search(r"(?:amostra|selecionad[oa]s|verificad[oa]s)[^.\n]{0,60}?(\d+(?:[,.]\d+)?)\s*%\s*(?:\([^)]*\)\s*)?"
                  r"(?:d[aoe]s?\s+)?(?:quantidade|total|carteira|direitos|documentos|itens|t[íi]tulos|valor)", t, re.I)
    if m and _num(m.group(1)) < 100:
        r.percentual = round(_num(m.group(1)) / 100, 6); r.evidencias["percentual"] = _frase(t, m.start())
    m = re.search(r"m[íi]nimo\s+de\s+(\d+)\s*(?:\([^)]*\)\s*)?(itens|direitos|documentos|t[íi]tulos|cr[ée]ditos)", t, re.I)
    if m:
        r.minimo = int(m.group(1)); r.evidencias["minimo"] = _frase(t, m.start())
    m = re.search(r"(?:m[áa]ximo\s+de|limitad[ao]\s+a)\s+(\d+)\s*(?:\([^)]*\)\s*)?(itens|direitos|documentos|t[íi]tulos)", t, re.I)
    if m:
        r.maximo = int(m.group(1)); r.evidencias["maximo"] = _frase(t, m.start())

    # população pequena: verifica tudo ("caso o número de Itens seja superior a 100, a amostragem será aplicável")
    m = re.search(r"(?:superior|maior)\s+a\s+(\d+)\s*(?:\([^)]*\)\s*)?,?[^.]{0,40}amostragem\s+ser[áa]\s+aplic", t, re.I) \
        or re.search(r"(?:inferior|menor)(?:\s+ou\s+igual)?\s+a\s+(\d+)\s*(?:\([^)]*\)\s*)?[^.]{0,120}(?:totalidade|100\s*%|todos|sem\s+amostragem|integral)", t, re.I)
    if m:
        r.limite_integral = int(m.group(1)); r.evidencias["limite_integral"] = _frase(t, m.start())
    if re.search(r"arredondament\w*\s+para\s+baixo", ts):
        r.arredondamento = "baixo"

    # ---- método
    tem_parametros = r.erro is not None or r.erro_faixa is not None or r.z is not None
    if tem_formula_yamane and not tem_formula_cochran and (r.erro is not None or r.erro_faixa):
        r.metodo = "formula_yamane"
    elif tem_formula_cochran or (tem_parametros and r.erro is not None):
        r.metodo = "formula_cochran"
    elif r.erro_faixa and not r.z:
        r.metodo = "formula_yamane"
        r.pendencias.append("fórmula não reconhecida no texto (provável n = N / (1 + N·E²)): confira")
    elif r.quantidade:
        r.metodo = "quantidade_fixa"
    elif r.percentual:
        r.metodo = "percentual"
    elif padrao_integral:
        r.metodo = "integral"

    if r.metodo == "integral" and re.search(r"por\s+amostragem", ts) and padrao_integral:
        # integral para parte da carteira e amostragem para outra parte (ou "poderá ser 100%")
        if re.search(r"poder[áa]\s+ser\s+de\s+100", ts):
            r.metodo = "nao_identificado"
            r.pendencias.append("o regulamento diz que a verificação é por amostragem e só a verificação inicial "
                                "\"poderá\" ser de 100%: os parâmetros da amostra não foram encontrados")
        else:
            r.pendencias.append("o texto fala em verificação integral e também em amostragem: confira qual vale para a carteira")

    if r.metodo == "formula_cochran":
        if r.z is None:
            r.z = 1.96; r.pendencias.append("z não encontrado: usado 1,96 (95% de confiança)")
        if r.p is None:
            r.p = 0.5; r.pendencias.append("p não encontrado: usado 50%")
        if r.erro is None:
            if r.erro_faixa:
                r.erro = r.erro_faixa[0]
                r.pendencias.append(f"o erro varia entre {r.erro_faixa[0]:.1%} e {r.erro_faixa[1]:.1%} a critério do gestor: "
                                    f"usado {r.erro:.1%} (o mais conservador)")
            else:
                r.erro = 0.05; r.pendencias.append("erro amostral não encontrado: usado 5%")
    if r.metodo == "formula_yamane" and r.erro is None and r.erro_faixa:
        r.erro = r.erro_faixa[0]
        r.pendencias.append(f"o erro tolerável varia entre {r.erro_faixa[0]:.1%} e {r.erro_faixa[1]:.1%} a critério do gestor: "
                            f"usado {r.erro:.1%} (o mais conservador)")
    externa = re.search(r"(dispon[íi]ve(l|is)\s+n[oa]\s+(website|s[íi]tio|p[áa]gina)[^.;]{0,60}"
                        r"|nas\s+pol[íi]ticas\s+d[ao]\s+(gestor|gestora|administrador|administradora|custodiante))", ts)
    if r.metodo == "nao_identificado" and externa:
        r.regra_externa = True
        r.evidencias["regra_externa"] = _frase(t, externa.start(), 400)
        r.pendencias.append("o regulamento não traz a regra da amostra: remete às políticas da gestora / regras "
                            "publicadas no website da administradora. Peça o documento à gestora ou à administradora")
    if r.metodo == "nao_identificado" and re.search(r"com\s+dispensa[^.;]{0,80}valor\s+m[ée]dio", ts):
        r.observacoes.append("O regulamento admite dispensa da verificação de lastro pelo reduzido valor médio dos "
                             "direitos creditórios: confira se a gestora adota a dispensa.")
    if r.metodo == "nao_identificado" and not r.pendencias:
        if re.search(r"por\s+amostragem", ts):
            r.pendencias.append("o regulamento prevê verificação por amostragem, mas não define o tamanho da amostra "
                                "(fórmula, quantidade ou percentual)")
        else:
            r.pendencias.append("o trecho fala de verificação de lastro, mas não diz se é integral nem traz o tamanho da amostra")

    # ---- população base
    m = re.search(r"popula[çc][ãa]o\s+base[^.]{0,400}", t, re.I) or re.search(r"universo\s+de\s+amostragem[^.]{0,400}", t, re.I) \
        or re.search(r"\bN\s*=\s*[^=\n]{0,200}", t)
    frase_pop = sem_acento(m.group(0).lower()) if m else ""
    if m and not r.populacao:
        r.evidencias["populacao"] = _frase(t, m.start(), 400)
    if frase_pop and not r.populacao:
        if re.search(r"a vencer|em aberto|em estoque|integrantes da carteira|carteira", frase_pop):
            r.populacao.append("a_vencer")
        if re.search(r"vencidos(?! e a vencer| ou a vencer)|vencidos e a vencer|inadimplid", frase_pop):
            r.populacao.append("vencidos")
        if "recomprad" in frase_pop:
            r.populacao.append("recomprados")
        if "substitu" in frase_pop:
            r.populacao.append("substituidos")
        if re.search(r"(cedidos|adquiridos|transferidos)[^.]{0,60}(trimestre|periodo)", frase_pop) or \
                re.search(r"totalidade de direitos creditorios adquiridos", frase_pop):
            if not r.populacao:
                r.populacao.append("adquiridos_periodo")
    if not r.populacao and r.metodo not in ("nao_identificado", "integral"):
        r.populacao = ["a_vencer"]
        r.pendencias.append("população base não descrita: usada a carteira a vencer na data-base")

    # ---- categorias verificadas a 100%
    for m in re.finditer(r"(100\s*%|totalidade|cem por cento|individual(mente)?)[^.]{0,200}", t, re.I):
        trecho = sem_acento(m.group(0).lower())
        achou = False
        if "inadimplid" in trecho or re.search(r"\bvencid", trecho):
            if "inadimplidos" not in r.integral_categorias:
                r.integral_categorias.append("inadimplidos"); achou = True
        if "substitu" in trecho and "substituidos" not in r.integral_categorias:
            r.integral_categorias.append("substituidos"); achou = True
        if "recomprad" in trecho and "recomprados" not in r.integral_categorias and "selecionad" not in trecho:
            r.integral_categorias.append("recomprados"); achou = True
        if achou:
            r.evidencias.setdefault("integral_categorias", _frase(t, m.start(), 300))

    # ---- maiores
    m = re.search(r"(\d+)\s*(?:\([^)]*\)\s*)?(cedentes?|sacados?|devedor(?:es)?|endossantes?(?:\s*/\s*cedentes?)?|originadores?)\s+mais\s+representativ"
                  r"[^.]{0,250}?(\d+)\s*(?:\([^)]*\)\s*)?(?:direitos\s+credit[óo]rios|itens|t[íi]tulos|cr[ée]ditos|documentos)[^.]{0,40}?de\s+maior(?:es)?\s+valor", t, re.I)
    if m:
        bases = []
        trecho = sem_acento(m.group(0).lower())
        if re.search(r"em aberto|a vencer|na carteira", trecho):
            bases.append("em_aberto")
        if "recomprad" in trecho:
            bases.append("recomprados")
        r.maiores_por_grupo = {"grupo": _grupo(m.group(2)), "n_grupos": int(m.group(1)),
                               "n_itens": int(m.group(3)), "bases": bases or ["em_aberto"]}
        r.evidencias["maiores_por_grupo"] = _frase(t, m.start(), 400)
    m = re.search(r"(exclu[íi]d[oa]s?|desconsiderad[oa]s?|n[ãa]o\s+ser[ãa]o\s+considerad[oa]s|excetuad[oa]s|exceto)[^.]{0,80}?"
                  r"(?:os|as)\s+(\d+)\s*(?:\([^)]*\)\s*)?(?:maiores|de\s+maior\s+valor)", t, re.I) \
        or re.search(r"(?:os|as)\s+(\d+)\s*(?:\([^)]*\)\s*)?maiores[^.]{0,120}?(ser[ãa]o\s+exclu[íi]d|n[ãa]o\s+ser[ãa]o\s+considerad|ficar[ãa]o\s+de\s+fora)", t, re.I)
    if m:
        n = next(g for g in m.groups() if g and g.isdigit())
        r.maiores_excluir = int(n); r.evidencias["maiores_excluir"] = _frase(t, m.start())
    m = re.search(r"(exclu[íi]d[oa]s?|desconsiderad[oa]s?|n[ãa]o\s+ser[ãa]o\s+considerad[oa]s)[^.]{0,80}?(\d+(?:[,.]\d+)?)\s*%[^.]{0,60}maior", t, re.I)
    if m:
        r.maiores_excluir_pct = round(_num(m.group(2)) / 100, 6); r.evidencias["maiores_excluir"] = _frase(t, m.start())
    if not r.maiores_por_grupo and r.maiores_excluir is None:
        m = re.search(r"(?:os|as)\s+(\d+)\s*(?:\([^)]*\)\s*)?(?:maiores\s+(?:direitos|t[íi]tulos|cr[ée]ditos|itens)|(?:direitos\s+credit[óo]rios|itens|t[íi]tulos)\s+de\s+maior(?:es)?\s+valor)"
                      r"[^.]{0,120}?(selecionad|verificad|inclu[íi]d|comp(or|ão))", t, re.I)
        if m:
            r.maiores_incluir = int(m.group(1)); r.evidencias["maiores_incluir"] = _frase(t, m.start())

    # ---- forma de seleção
    if re.search(r"intervalo\s+de\s+(retirada|sele)|a\s+cada\s+[\"']?k|ponto\s+de\s+partida|sistem[áa]tic", t, re.I):
        r.selecao = "sistematica"
    elif re.search(r"aleat[óo]ri|sorteio|sortead", t, re.I):
        r.selecao = "aleatoria"
    if re.search(r"estratific", ts):
        r.pendencias.append("o regulamento fala em estratificação: confira se a amostra deve ser separada por estrato")

    m = re.search(r"\b(trimestral|mensal|semestral|anual)(mente)?\b", ts)
    if m:
        r.periodicidade = m.group(1)

    # ---- outras exigências que o script não aplica sozinho (só informativas)
    m = re.search(r"inconsist[eê]ncia\s+relevante[^.]{0,250}", t, re.I)
    if m:
        r.observacoes.append("O regulamento define \"Inconsistência Relevante\" (limite de erros na amostra). "
                             "O script gera a amostra; a conclusão sobre o resultado é manual: "
                             + _frase(t, m.start(), 300))
    if re.search(r"registrad[oa]s?\s+(em|na|perante)\s+(a\s+)?entidade\s+registradora[^.]{0,120}(dispensad|n[ãa]o\s+ser[ãa]o\s+objeto)", ts):
        r.observacoes.append("Direitos creditórios registrados em entidade registradora podem estar dispensados da verificação: confira o trecho.")
    return r
