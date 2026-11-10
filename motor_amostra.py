# ===================================================================== motor da amostra
# Gera a amostra de verificação de lastro a partir da base analítica de direitos creditórios
# (uma linha por recebível, em .xlsx ou .csv) e da REGRA lida do regulamento.
# Só usa a biblioteca padrão + openpyxl.
import argparse
import csv
import math
import random
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

# Nomes de coluna aceitos (sem acento, minúsculas). Use --col-<campo> para indicar outro nome.
COLUNAS = {
    "id": ["seu_numero", "seu numero", "nu_documento", "numero_documento", "documento", "id_recebivel", "id", "titulo",
           "nosso_numero", "chave", "contrato"],
    "valor": ["valor_presente", "vl_presente", "valor presente", "valor_aquisicao", "valor_nominal", "vl_nominal",
              "valor nominal", "valor_face", "valor"],
    "situacao": ["situacao_recebivel", "situacao", "status", "tipo_movimento", "movimento", "categoria"],
    "vencimento": ["data_vencimento", "dt_vencimento", "vencimento", "data vencimento"],
    "cedente": ["nome_cedente", "cedente", "doc_cedente", "cnpj_cedente", "originador", "endossante"],
    "sacado": ["nome_sacado", "sacado", "doc_sacado", "cpf_cnpj_sacado", "devedor", "nome_devedor"],
}
# Palavras da coluna de situação que indicam cada categoria (primeira que casar vale)
SITUACOES = [
    ("recomprados", ["recompra", "recomprad"]),
    ("substituidos", ["substitu"]),
    ("vencidos", ["vencid", "inadimpl", "atras"]),
    ("a_vencer", ["a vencer", "aberto", "vincend", "em dia", "adimpl", "estoque"]),
]
NOMES_CATEGORIA = {"a_vencer": "a vencer", "vencidos": "vencidos/inadimplidos", "recomprados": "recomprados",
                   "substituidos": "substituídos", "adquiridos_periodo": "adquiridos no período"}


def _chave(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", s)


def _valor(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def ler_base(caminho):
    caminho = Path(caminho)
    if caminho.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        ws = wb.active
        linhas = ws.iter_rows(values_only=True)
        cab = [str(c or "").strip() for c in next(linhas)]
        dados = [dict(zip(cab, l)) for l in linhas if any(x not in (None, "") for x in l)]
        wb.close()
        return cab, dados
    texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    sep = ";" if texto.split("\n", 1)[0].count(";") >= texto.split("\n", 1)[0].count(",") else ","
    leitor = csv.DictReader(texto.splitlines(), delimiter=sep)
    return list(leitor.fieldnames or []), [l for l in leitor if any(v for v in l.values())]


def achar_colunas(cabecalho, forcadas=None):
    forcadas = forcadas or {}
    mapa = {}
    chaves = {_chave(c): c for c in cabecalho}
    for campo, candidatos in COLUNAS.items():
        if forcadas.get(campo):
            if forcadas[campo] not in cabecalho:
                raise SystemExit(f"A coluna \"{forcadas[campo]}\" não existe na base. Colunas: {', '.join(cabecalho)}")
            mapa[campo] = forcadas[campo]
            continue
        for c in candidatos:
            if c in chaves:
                mapa[campo] = chaves[c]
                break
        else:
            for c in candidatos:  # nome parecido ("VALOR PRESENTE (R$)")
                achado = next((orig for k, orig in chaves.items() if k.startswith(c)), None)
                if achado:
                    mapa[campo] = achado
                    break
    return mapa


def categoria(linha, col, data_base):
    if "situacao" in col:
        s = _chave(linha.get(col["situacao"]))
        for cat, palavras in SITUACOES:
            if any(p in s for p in palavras):
                return cat
    if "vencimento" in col:
        venc = _data(linha.get(col["vencimento"]))
        if venc:
            return "vencidos" if venc < data_base else "a_vencer"
    return "a_vencer"


def tamanho_amostra(regra, n_pop):
    if n_pop <= 0:
        return 0
    if regra["metodo"] == "integral" or (regra.get("limite_integral") and n_pop <= regra["limite_integral"]):
        return n_pop
    m = regra["metodo"]
    if m == "formula_cochran":
        z, p, e = regra["z"], regra["p"], regra["erro"]
        n = (n_pop * z ** 2 * p * (1 - p)) / (e ** 2 * (n_pop - 1) + z ** 2 * p * (1 - p))
    elif m == "formula_yamane":
        n = n_pop / (1 + n_pop * regra["erro"] ** 2)
    elif m == "quantidade_fixa":
        n = regra["quantidade"]
    elif m == "percentual":
        n = n_pop * regra["percentual"]
    else:
        raise SystemExit("A regra deste fundo não foi identificada no regulamento: monte a amostra manualmente.")
    n = math.ceil(n - 1e-9) if regra.get("arredondamento", "cima") == "cima" else round(n)
    if regra.get("minimo"):
        n = max(n, regra["minimo"])
    if regra.get("maximo"):
        n = min(n, regra["maximo"])
    return min(n, n_pop)


def sortear(itens, n, metodo, rnd):
    """Sorteio sistemático (intervalo K, ponto de partida aleatório) ou aleatório simples."""
    if n <= 0 or not itens:
        return [], None, None
    if n >= len(itens):
        return list(itens), 1.0, 0.0
    if metodo == "aleatoria":
        return rnd.sample(itens, n), None, None
    k = len(itens) / n
    inicio = rnd.uniform(0, k)
    return [itens[int(inicio + i * k)] for i in range(n)], k, inicio


def gerar_amostra(dados, col, regra, data_base, semente):
    rnd = random.Random(semente)
    for i, l in enumerate(dados):
        l["_cat"] = categoria(l, col, data_base)
        l["_valor"] = _valor(l.get(col["valor"])) if "valor" in col else 0.0
        l["_ordem"] = i
    resumo = {"semente": semente, "data_base": data_base.isoformat(), "linhas_base": len(dados)}
    for cat in NOMES_CATEGORIA:
        resumo[f"base_{cat}"] = sum(1 for l in dados if l["_cat"] == cat)
    selecao = {}  # _ordem -> motivo

    def marcar(linhas, motivo):
        for l in linhas:
            selecao.setdefault(l["_ordem"], motivo)

    # 1) categorias verificadas a 100% (fora da conta da amostra)
    integral_cats = {"inadimplidos": "vencidos"}.get
    cats_100 = {integral_cats(c, c) for c in regra.get("integral_categorias", [])}
    pool_i = [l for l in dados if l["_cat"] in cats_100]
    if regra.get("subamostra_i_max"):
        # Modelo "Amostra (I)" + "Amostra (A)": os inadimplidos/substituídos são verificados a 100% pelo custodiante,
        # e até X deles entram na amostra total
        marcar(pool_i, "100% (inadimplido/substituído)")
        n_i = min(regra["subamostra_i_max"], len(pool_i))
        sel_i, _, _ = sortear(pool_i, n_i, regra.get("selecao", "sistematica"), rnd)
        for l in sel_i:
            selecao[l["_ordem"]] = "Amostra (I) - inadimplido/substituído"
        resumo["amostra_i"] = n_i
    else:
        marcar(pool_i, "100% (" + ", ".join(NOMES_CATEGORIA.get(c, c) for c in sorted(cats_100)) + ")")
    resumo["verificados_100"] = len(pool_i)

    # 2) população base da amostra
    cats_pop = set(regra.get("populacao") or ["a_vencer"])
    if "adquiridos_periodo" in cats_pop:
        cats_pop |= {"a_vencer", "vencidos"}
    pop = [l for l in dados if l["_cat"] in cats_pop and l["_ordem"] not in selecao]
    excluidos = []
    if regra.get("maiores_excluir") or regra.get("maiores_excluir_pct"):
        n_exc = regra.get("maiores_excluir") or math.ceil(len(pop) * regra["maiores_excluir_pct"])
        excluidos = sorted(pop, key=lambda l: -l["_valor"])[:n_exc]
        ids = {l["_ordem"] for l in excluidos}
        pop = [l for l in pop if l["_ordem"] not in ids]
    resumo["populacao_N"] = len(pop)
    resumo["excluidos_maiores"] = len(excluidos)

    # 3) tamanho da amostra
    if regra.get("subamostra_i_max"):
        n = max(0, min(regra["quantidade"] - resumo["amostra_i"], len(pop)))
    else:
        n = tamanho_amostra(regra, len(pop))
    resumo["amostra_n"] = n

    # 4) itens obrigatórios (maiores) — contam dentro do n
    obrig = []
    mg = regra.get("maiores_por_grupo")
    if mg:
        campo = "cedente" if mg["grupo"] == "cedente" else "sacado"
        if campo not in col:
            raise SystemExit(f"A regra pede os maiores por {campo}, mas a base não tem coluna de {campo}. "
                             f"Use --col-{campo} <nome da coluna>.")
        bases = {"em_aberto": ("a_vencer", "vencidos"), "recomprados": ("recomprados",)}
        for b in mg.get("bases", ["em_aberto"]):
            linhas = [l for l in pop if l["_cat"] in bases.get(b, (b,))]
            soma = {}
            for l in linhas:
                g = str(l.get(col[campo]) or "").strip()
                soma[g] = soma.get(g, 0.0) + l["_valor"]
            for g in sorted(soma, key=lambda x: -soma[x])[:mg["n_grupos"]]:
                do_grupo = sorted((l for l in linhas if str(l.get(col[campo]) or "").strip() == g), key=lambda l: -l["_valor"])
                rotulo = {"em_aberto": "em aberto", "recomprados": "recomprados"}.get(b, b)
                obrig += [(l, f"maior valor do {campo} {g} ({rotulo})") for l in do_grupo[:mg["n_itens"]]]
    if regra.get("maiores_incluir"):
        obrig += [(l, "maior valor da carteira") for l in sorted(pop, key=lambda l: -l["_valor"])[:regra["maiores_incluir"]]]
    for l, motivo in obrig:
        selecao.setdefault(l["_ordem"], motivo)
    n_obrig = sum(1 for l in pop if l["_ordem"] in selecao)
    resumo["obrigatorios_maiores"] = n_obrig

    # 5) sorteio do restante
    resto = [l for l in pop if l["_ordem"] not in selecao]
    sorteados, k, inicio = sortear(resto, max(0, n - n_obrig), regra.get("selecao", "sistematica"), rnd)
    marcar(sorteados, "sorteio sistemático" if regra.get("selecao", "sistematica") == "sistematica" else "sorteio aleatório")
    resumo["sorteados"] = len(sorteados)
    resumo["intervalo_K"] = round(k, 4) if k else None
    resumo["ponto_partida"] = round(inicio, 4) if inicio is not None else None
    resumo["total_a_verificar"] = len(selecao)
    amostra = [(l, selecao[l["_ordem"]]) for l in dados if l["_ordem"] in selecao]
    return amostra, excluidos, resumo


def gravar(saida, cabecalho, amostra, excluidos, resumo, regra):
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Amostra"
    ws.append(["MOTIVO", "CATEGORIA", *cabecalho])
    for l, motivo in amostra:
        ws.append([motivo, NOMES_CATEGORIA.get(l["_cat"], l["_cat"]), *[l.get(c) for c in cabecalho]])
    if excluidos:
        we = wb.create_sheet("Excluídos (maiores)")
        we.append(["CATEGORIA", *cabecalho])
        for l in excluidos:
            we.append([NOMES_CATEGORIA.get(l["_cat"], l["_cat"]), *[l.get(c) for c in cabecalho]])
    wr = wb.create_sheet("Resumo")
    for k, v in resumo.items():
        wr.append([k, v])
    wr.append([])
    for k, v in regra.items():
        if k not in ("evidencias", "pendencias", "observacoes"):
            wr.append([f"regra.{k}", str(v)])
    for w in wb.worksheets:
        for c in w[1]:
            c.font = Font(bold=True)
    wb.save(saida)


def main(regra, argv=None, nome_saida="amostra.xlsx"):
    ap = argparse.ArgumentParser(description="Gera a amostra de verificação de lastro conforme o regulamento.")
    ap.add_argument("base", help="base analítica de direitos creditórios (.xlsx ou .csv), uma linha por recebível")
    ap.add_argument("--saida", default=nome_saida)
    ap.add_argument("--data-base", default=date.today().isoformat(), help="AAAA-MM-DD (para separar vencidos de a vencer)")
    ap.add_argument("--semente", type=int, default=None, help="semente do sorteio (anote para reproduzir a amostra)")
    for campo in COLUNAS:
        ap.add_argument(f"--col-{campo}", default=None, help=f"nome da coluna de {campo} na base")
    a = ap.parse_args(argv)
    cab, dados = ler_base(a.base)
    col = achar_colunas(cab, {c: getattr(a, f"col_{c}") for c in COLUNAS})
    if "valor" not in col:
        raise SystemExit("Não achei a coluna de valor na base. Use --col-valor <nome da coluna>.")
    if "situacao" not in col and "vencimento" not in col:
        print("[AVISO] a base não tem coluna de situação nem de vencimento: todos os itens foram tratados como a vencer.")
    semente = a.semente if a.semente is not None else random.SystemRandom().randint(1, 999_999)
    data_base = datetime.strptime(a.data_base, "%Y-%m-%d").date()
    amostra, excluidos, resumo = gerar_amostra(dados, col, regra, data_base, semente)
    gravar(a.saida, cab, amostra, excluidos, resumo, regra)
    print(f"Colunas usadas: {col}")
    for k, v in resumo.items():
        print(f"  {k}: {v}")
    print(f"Amostra gravada em {a.saida} ({resumo['total_a_verificar']} itens a verificar). Semente: {semente}")
    return resumo
