"""Tabela (Excel) com a regra de amostragem de cada fundo: _script de amostra/_regras.xlsx."""
from __future__ import annotations

import json
from pathlib import Path

import motor_amostra
import readme_fundo
from regra import Regra

N_EXEMPLOS = (100, 1_000, 10_000)
FONTE = "Arial"
CORES_STATUS = {"OK": "E2EFDA", "CONFERIR": "FFF2CC", "REVISÃO HUMANA": "F8CBAD",
                "PROCEDIMENTOS PRÉ-ACORDADOS": "E4DFEC", "FIC FIDC": "FCE4D6",
                "REVISADO MANUALMENTE": "DDEBF7", "SEM REGULAMENTO": "D9D9D9", "ERRO": "F8CBAD"}

# (cabeçalho, largura, chave)
COLUNAS = [
    ("CNPJ", 20, "cnpj"), ("Fundo", 46, "nome"), ("Status", 18, "status"), ("Método", 30, "metodo"),
    ("Tamanho da amostra", 60, "tamanho"),
    ("z", 7, "z"), ("Confiança", 10, "confianca"), ("p", 8, "p"), ("Erro (E)", 9, "erro"),
    ("Qtde fixa", 9, "quantidade"), ("Amostra (I) até", 11, "subamostra_i_max"), ("% da carteira", 11, "percentual"),
    ("Mínimo", 8, "minimo"), ("Máximo", 8, "maximo"), ("Até N itens: 100%", 12, "limite_integral"),
    ("População base (N)", 34, "populacao"), ("Verificados a 100%", 30, "integral"),
    ("Maiores obrigatórios", 48, "maiores"), ("Maiores excluídos da base", 14, "excluir"),
    ("Seleção", 12, "selecao"),
    *[(f"n p/ N = {n:,}".replace(",", "."), 11, f"n_{n}") for n in N_EXEMPLOS],
    ("Pendências", 70, "pendencias"), ("Observações", 50, "observacoes"),
    ("Regulamento (Fundos.NET)", 16, "link"), ("Pasta", 40, "pasta"),
]
PERCENTUAIS = {"confianca", "p", "erro", "percentual"}


def _linha(fundo: dict, pasta_scripts: Path) -> dict:
    """Uma linha da tabela a partir do resumo + regra.json do fundo."""
    out = {"cnpj": fundo.get("cnpj", ""), "nome": fundo.get("nome", ""), "status": fundo.get("status", ""),
           "pendencias": fundo.get("pendencias", ""), "pasta": fundo.get("pasta", "")}
    caminho = pasta_scripts / fundo.get("pasta", "") / "regra.json" if fundo.get("pasta") else None
    if not caminho or not caminho.exists():
        out["metodo"] = "—"
        return out
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    d = dados["regra"]
    nomes = {f for f in Regra.__dataclass_fields__}
    r = Regra(**{k: v for k, v in d.items() if k in nomes})
    if dados.get("doc_id"):
        out["link"] = readme_fundo.URL_DOCUMENTO.format(id=dados["doc_id"])
    out["metodo"] = readme_fundo.NOMES_METODO.get(r.metodo, r.metodo)
    out["tamanho"] = readme_fundo.descrever_tamanho(r)
    for k in ("z", "confianca", "p", "erro", "quantidade", "subamostra_i_max", "percentual", "minimo", "maximo",
              "limite_integral"):
        out[k] = d.get(k)
    if r.metodo not in ("integral", "nao_identificado"):
        out["populacao"] = ", ".join(readme_fundo.NOMES_CAT.get(c, c) for c in r.populacao)
        out["selecao"] = "sistemática" if r.selecao == "sistematica" else "aleatória"
    out["integral"] = ", ".join(readme_fundo.NOMES_CAT.get(c, c) for c in r.integral_categorias)
    if r.maiores_por_grupo:
        mg = r.maiores_por_grupo
        out["maiores"] = (f"{mg['n_itens']} maiores de cada um dos {mg['n_grupos']} {mg['grupo']}s mais representativos "
                          f"({', '.join({'em_aberto': 'em aberto', 'recomprados': 'recomprados'}.get(b, b) for b in mg['bases'])})")
    elif r.maiores_incluir:
        out["maiores"] = f"os {r.maiores_incluir} maiores da carteira"
    if r.maiores_excluir:
        out["excluir"] = r.maiores_excluir
    elif r.maiores_excluir_pct:
        out["excluir"] = f"{r.maiores_excluir_pct:.0%}"
    if r.metodo != "nao_identificado":
        for n in N_EXEMPLOS:
            try:
                if r.subamostra_i_max:
                    out[f"n_{n}"] = r.quantidade
                else:
                    out[f"n_{n}"] = motor_amostra.tamanho_amostra(d, n)
            except (KeyError, TypeError, SystemExit):
                pass
    out["observacoes"] = " | ".join(r.observacoes)
    return out


def gerar(resumo: list[dict], pasta_scripts: Path, destino: Path | None = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    destino = destino or pasta_scripts / "_regras.xlsx"
    linhas = sorted((_linha(f, pasta_scripts) for f in resumo), key=lambda x: (x["nome"] or "").upper())
    wb = Workbook()
    ws = wb.active
    ws.title = "Regras"
    fonte = Font(name=FONTE, size=9)
    negrito = Font(name=FONTE, size=9, bold=True, color="FFFFFF")
    fino = Side(style="thin", color="BFBFBF")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)

    ws["A1"] = "Regras de amostragem da verificação de lastro, por fundo (lidas do regulamento vigente no Fundos.NET)"
    ws["A1"].font = Font(name=FONTE, size=12, bold=True)
    ws["A2"] = ("Gerada pelo comando ler do Leitor de regulamentos. Os valores de \"n p/ N\" são o tamanho da amostra que a "
                "regra de cada fundo dá para aquela população, calculado pela ferramenta (mesmo cálculo do script de "
                "amostra). Os itens verificados a 100% não entram no n. Confira as pendências antes de usar.")
    ws["A2"].font = Font(name=FONTE, size=9, italic=True)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=12)
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 36

    cab = 4
    for j, (titulo, largura, _) in enumerate(COLUNAS, 1):
        c = ws.cell(row=cab, column=j, value=titulo)
        c.font = negrito
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = borda
        ws.column_dimensions[get_column_letter(j)].width = largura
    ws.row_dimensions[cab].height = 30
    ws.cell(row=cab, column=[k for _, _, k in COLUNAS].index("n_1000") + 1).comment = Comment(
        "Tamanho da amostra (sem os itens verificados a 100%) para uma população de 1.000 direitos creditórios, "
        "calculado pela ferramenta com os parâmetros da regra.", "Leitor de regulamentos")

    for i, l in enumerate(linhas, cab + 1):
        cor = CORES_STATUS.get(l.get("status"))
        for j, (_, _, k) in enumerate(COLUNAS, 1):
            v = l.get(k)
            if v in ("", None):
                v = None
            c = ws.cell(row=i, column=j, value=v)
            c.font = fonte
            c.border = borda
            c.alignment = Alignment(vertical="top", wrap_text=k in ("tamanho", "pendencias", "observacoes", "maiores",
                                                                     "populacao", "integral", "nome"))
            if k in PERCENTUAIS and isinstance(v, (int, float)):
                c.number_format = "0.0%"
            elif k == "z" and isinstance(v, (int, float)):
                c.number_format = "0.000"
            elif k.startswith("n_") or k in ("quantidade", "subamostra_i_max", "minimo", "maximo", "limite_integral"):
                c.number_format = "#,##0"
            if k == "status" and cor:
                c.fill = PatternFill("solid", fgColor=cor)
            if k == "link" and v:
                c.value = "abrir"
                c.hyperlink = v
                c.font = Font(name=FONTE, size=9, color="0563C1", underline="single")
    ultima = cab + len(linhas)
    ws.freeze_panes = ws.cell(row=cab + 1, column=3)
    ws.auto_filter.ref = f"A{cab}:{get_column_letter(len(COLUNAS))}{max(ultima, cab)}"

    # aba de resumo por status e por método
    wr = wb.create_sheet("Resumo")
    wr["A1"] = "Fundos por status"
    wr["A1"].font = Font(name=FONTE, size=11, bold=True)
    col_status = get_column_letter([k for _, _, k in COLUNAS].index("status") + 1)
    col_metodo = get_column_letter([k for _, _, k in COLUNAS].index("metodo") + 1)
    faixa_s = f"Regras!${col_status}${cab + 1}:${col_status}${max(ultima, cab + 1)}"
    faixa_m = f"Regras!${col_metodo}${cab + 1}:${col_metodo}${max(ultima, cab + 1)}"
    r0 = 2
    todos = list(CORES_STATUS)
    for k, nome in enumerate(todos):
        wr.cell(row=r0 + k, column=1, value=nome)
        wr.cell(row=r0 + k, column=2, value=f'=COUNTIF({faixa_s},A{r0 + k})')
        wr.cell(row=r0 + k, column=1).fill = PatternFill("solid", fgColor=CORES_STATUS.get(nome, "FFFFFF"))
    tot = r0 + len(todos)
    wr.cell(row=tot, column=1, value="Total")
    wr.cell(row=tot, column=2, value=f"=SUM(B{r0}:B{tot - 1})")
    wr.cell(row=tot + 2, column=1, value="Fundos por método").font = Font(name=FONTE, size=11, bold=True)
    for k, nome in enumerate(readme_fundo.NOMES_METODO.values()):
        wr.cell(row=tot + 3 + k, column=1, value=nome)
        wr.cell(row=tot + 3 + k, column=2, value=f'=COUNTIF({faixa_m},A{tot + 3 + k})')
    for row in wr.iter_rows():
        for c in row:
            if c.font is None or not c.font.bold:
                c.font = Font(name=FONTE, size=10, bold=bool(c.font and c.font.bold))
    wr.column_dimensions["A"].width = 52
    wr.column_dimensions["B"].width = 10
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(destino)
    except PermissionError:  # planilha aberta no Excel
        from datetime import datetime
        alternativo = destino.with_name(f"{destino.stem} ({datetime.now():%Y-%m-%d %H%M%S}){destino.suffix}")
        print(f"[AVISO] {destino.name} está aberto em outro programa (feche o Excel). Gravado em {alternativo.name}.")
        wb.save(alternativo)
        destino = alternativo
    return destino
