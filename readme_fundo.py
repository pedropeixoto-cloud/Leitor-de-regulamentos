"""Monta o README.md de cada fundo: regra lida do regulamento + trecho + script da amostra."""
from __future__ import annotations

import pprint
from datetime import date
from pathlib import Path

import motor_amostra
from regra import Regra

AQUI = Path(__file__).resolve().parent
URL_DOCUMENTO = "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={id}"

NOMES_METODO = {
    "formula_cochran": "Fórmula estatística (população finita)",
    "formula_yamane": "Fórmula n = N / (1 + N·E²)",
    "integral": "Verificação integral (100% dos direitos creditórios)",
    "quantidade_fixa": "Quantidade fixa de itens",
    "percentual": "Percentual da carteira",
    "nao_identificado": "Não identificada",
}
NOMES_CAT = {"a_vencer": "a vencer (em aberto)", "vencidos": "vencidos / inadimplidos", "recomprados": "recomprados no período",
             "substituidos": "substituídos no período", "adquiridos_periodo": "adquiridos/cedidos no período",
             "inadimplidos": "inadimplidos"}


def _pct(x):
    return f"{x * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def _num(x):
    return f"{x:g}".replace(".", ",")


def descrever_tamanho(r: Regra) -> str:
    if r.metodo == "formula_cochran":
        s = (f"n = N·z²·p·(1−p) / [E²·(N−1) + z²·p·(1−p)], com z = {_num(r.z)}"
             + (f" ({_pct(r.confianca)} de confiança)" if r.confianca else "")
             + f", p = {_pct(r.p)} e E = {_pct(r.erro)}; arredondado para {'cima' if r.arredondamento == 'cima' else 'baixo'}")
    elif r.metodo == "formula_yamane":
        s = f"n = N / (1 + N·E²), com E = {_pct(r.erro)}"
    elif r.metodo == "quantidade_fixa":
        s = f"{r.quantidade} itens"
        if r.subamostra_i_max:
            s += (f": Amostra (I) com até {r.subamostra_i_max} inadimplidos/substituídos e Amostra (A) com o restante, "
                  f"tirado da carteira a vencer")
    elif r.metodo == "percentual":
        s = f"{_pct(r.percentual)} dos itens da população"
    elif r.metodo == "integral":
        return "todos os direitos creditórios (sem amostragem)"
    else:
        return "—"
    if r.limite_integral:
        s += f". Se a população tiver até {r.limite_integral} itens, verificam-se todos"
    if r.minimo:
        s += f". Mínimo de {r.minimo} itens"
    if r.maximo:
        s += f". Máximo de {r.maximo} itens"
    return s


def tabela_regra(r: Regra) -> list[str]:
    linhas = ["| Item | Regra |", "|---|---|",
              f"| Método | {NOMES_METODO[r.metodo]} |",
              f"| Tamanho da amostra | {descrever_tamanho(r)} |"]
    if r.metodo != "integral":
        linhas.append(f"| População base (N) | {', '.join(NOMES_CAT.get(c, c) for c in r.populacao) or '—'} |")
    if r.integral_categorias:
        linhas.append(f"| Verificados a 100% (além da amostra) | {', '.join(NOMES_CAT.get(c, c) for c in r.integral_categorias)} |")
    if r.maiores_por_grupo:
        mg = r.maiores_por_grupo
        bases = " e ".join({"em_aberto": "em aberto", "recomprados": "com títulos recomprados"}.get(b, b) for b in mg["bases"])
        linhas.append(f"| Maiores (obrigatórios, contam no n) | os {mg['n_itens']} direitos creditórios de maior valor de cada um dos "
                      f"{mg['n_grupos']} {mg['grupo']}s mais representativos ({bases}) |")
    if r.maiores_incluir:
        linhas.append(f"| Maiores (obrigatórios) | os {r.maiores_incluir} direitos creditórios de maior valor |")
    if r.maiores_excluir or r.maiores_excluir_pct:
        q = r.maiores_excluir or _pct(r.maiores_excluir_pct)
        linhas.append(f"| Excluídos da base | os {q} maiores direitos creditórios não entram na população |")
    if r.metodo != "integral":
        linhas.append("| Seleção do restante | " + (
            "sistemática: K = N/n, ponto de partida sorteado, um item a cada K" if r.selecao == "sistematica"
            else "aleatória simples") + " |")
    if r.periodicidade:
        linhas.append(f"| Periodicidade | {r.periodicidade} |")
    return linhas


def exemplos(r: Regra) -> list[str]:
    if r.metodo in ("nao_identificado", "integral") or r.subamostra_i_max:
        return []
    d = r.para_dict()
    out = ["| N (população) | n (amostra) |", "|---:|---:|"]
    for n_pop in (50, 100, 500, 1_000, 5_000, 10_000, 100_000):
        out.append(f"| {n_pop:,} | {motor_amostra.tamanho_amostra(d, n_pop):,} |".replace(",", "."))
    return out


def regra_para_script(r: Regra) -> str:
    d = {k: v for k, v in r.para_dict().items() if k not in ("evidencias", "observacoes")}
    return "REGRA = " + pprint.pformat(d, width=110, sort_dicts=False)


def script(r: Regra, cnpj_fmt: str, cnpj: str, nome: str, doc_id) -> str:
    motor = (AQUI / "motor_amostra.py").read_text(encoding="utf-8")
    cab = (f'"""Amostra de verificação de lastro - {nome} ({cnpj_fmt}).\n\n'
           f"Gerado em {date.today():%d/%m/%Y} a partir do regulamento {doc_id} do Fundos.NET.\n"
           f"Uso: python amostra_{cnpj}.py <base.xlsx|csv> --data-base AAAA-MM-DD [--semente N]\n"
           '"""\n')
    return (cab + regra_para_script(r) + "\n\n" + motor.rstrip() + "\n\n\n"
            f'if __name__ == "__main__":\n    main(REGRA, nome_saida="amostra_{cnpj}.xlsx")\n')


SELOS = {
    "OK": "✅ Regra identificada",
    "CONFERIR": "⚠️ Regra identificada com pendências: conferir",
    "REVISÃO HUMANA": "❌ Revisão humana: a regra não foi identificada automaticamente",
    "PROCEDIMENTOS PRÉ-ACORDADOS": "📋 Procedimentos pré-acordados: o regulamento remete a regra às políticas da "
                                   "gestora/administradora (fora do regulamento)",
    "FIC FIDC": "📁 FIC FIDC: fundo de investimento em cotas de FIDC (pela leitura do regulamento)",
    "REVISADO MANUALMENTE": "✅ Regra revisada manualmente (regra.json)",
}


def status(r: Regra, avisos: list[str], fic: bool = False) -> str:
    """Prioridade: FIC FIDC > procedimentos pré-acordados > revisão humana > conferir > ok."""
    if fic:
        return "FIC FIDC"
    if r.metodo == "nao_identificado":
        return "PROCEDIMENTOS PRÉ-ACORDADOS" if r.regra_externa else "REVISÃO HUMANA"
    if r.pendencias or avisos:
        return "CONFERIR"
    return "OK"


def montar(*, nome: str, cnpj: str, doc, arquivo: Path | None, secao, r: Regra, local: str = "_regulamento",
           st: str | None = None, trecho_fic: str = "") -> str:
    """cnpj: só os dígitos (vai no nome dos arquivos). local: pasta onde o regulamento está. st: status final."""
    cnpj_fmt = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    st = st or status(r, secao.avisos)
    selo = SELOS.get(st, st)
    L = [f"# Amostra de verificação de lastro: {nome}", "",
         f"- **CNPJ:** {cnpj_fmt}"]
    if doc is not None:
        entrega = doc.data_entrega.strftime("%d/%m/%Y") if doc.data_entrega else "?"
        L.append(f"- **Regulamento:** documento {doc.id} do Fundos.NET, entregue em {entrega} "
                 f"([abrir]({URL_DOCUMENTO.format(id=doc.id)}))")
    if arquivo is not None:
        L.append(f"- **Arquivo:** `{arquivo.name}` (pasta `{local}`)")
    L += [f"- **Gerado em:** {date.today():%d/%m/%Y}", "", f"**Status: {selo}**", ""]
    if st == "FIC FIDC" and trecho_fic:
        L += [f"*Reconhecido como FIC FIDC por este trecho do regulamento:* \"{trecho_fic[:300]}\"", ""]

    if r.pendencias or secao.avisos:
        L += ["## Pendências", ""] + [f"- {p}" for p in [*secao.avisos, *r.pendencias]] + [""]

    L += ["## Regra do regulamento", ""] + tabela_regra(r) + [""]
    ex = exemplos(r)
    if ex:
        L += ["Tamanho da amostra para alguns tamanhos de população:", ""] + ex + [""]
    if r.observacoes:
        L += ["### Observações", ""] + [f"- {o}" for o in r.observacoes] + [""]
    if r.evidencias:
        L += ["### Onde está cada parâmetro no texto", "", "| Parâmetro | Trecho |", "|---|---|"]
        agrupado: dict[str, list[str]] = {}
        for k, v in r.evidencias.items():
            agrupado.setdefault(v, []).append(k)
        for v, ks in agrupado.items():
            L.append(f"| {', '.join(ks)} | {v.replace('|', '/')} |")
        L.append("")

    L += ["## Trecho do regulamento", ""]
    if secao.texto:
        origem = "anexo do regulamento" if secao.origem == "anexo" else "cláusulas do regulamento"
        L.append(f"*Origem: {origem}.*")
        L.append("")
        for par in secao.texto.split("\n"):
            L.append(f"> {par}")
            L.append(">")
        if secao.mencoes:
            L += ["", "Outras cláusulas sobre o tema:", ""]
            for p in secao.mencoes:
                L.append(f"> {p}")
                L.append(">")
    else:
        L.append("*Não foi encontrado trecho sobre verificação de lastro ou amostragem no regulamento.*")
    L.append("")

    if r.metodo != "nao_identificado":
        L += ["## Script da amostra", "",
              f"Salve o bloco abaixo como `amostra_{cnpj}.py` e rode com a base analítica de direitos creditórios "
              "do fundo (uma linha por recebível, `.xlsx` ou `.csv`):", "",
              "```bash",
              f"python amostra_{cnpj}.py base_{cnpj}.xlsx --data-base 2026-09-30",
              "```", "",
              "Ou, sem copiar o código, pela ferramenta:", "",
              "```bash",
              f"python amostra_regulamento.py amostra --cnpj {cnpj} --base base_{cnpj}.xlsx --data-base 2026-09-30",
              "```", "",
              "- A base precisa de uma coluna de **valor** e, de preferência, de **situação** (a vencer, vencido, "
              "recomprado, substituído) ou de **vencimento**. Para as regras dos maiores por cedente/sacado, também a "
              "coluna do **cedente** ou do **sacado**. Se o nome da coluna for diferente, use `--col-valor`, "
              "`--col-situacao`, `--col-cedente` etc.",
              "- O sorteio sistemático percorre a base na ordem do arquivo (sem os itens obrigatórios).",
              "- A semente do sorteio sai na tela e na aba *Resumo*: anote-a para reproduzir a mesma amostra.",
              "- Saída: `amostra_<cnpj>.xlsx` com as abas *Amostra* (itens a verificar e o motivo de cada um), "
              "*Resumo* (N, n, K, ponto de partida, parâmetros) e, se houver, *Excluídos (maiores)*.", "",
              "```python", script(r, cnpj_fmt, cnpj, nome, doc.id if doc is not None else "?").rstrip(), "```", ""]
    elif st == "PROCEDIMENTOS PRÉ-ACORDADOS":
        L += ["## Script da amostra", "",
              "Não gerado: o regulamento não traz a regra da amostra e remete às políticas/procedimentos da gestora "
              "ou da administradora (veja o trecho em *regra_externa* acima). Peça o documento de procedimentos à "
              "gestora ou à administradora. Com a regra em mãos, registre-a no `regra.json` desta pasta (marque "
              "`\"revisado_manualmente\": true`) e rode "
              f"`python amostra_regulamento.py amostra --cnpj {cnpj} --base <base>`.", ""]
    else:
        L += ["## Script da amostra", "",
              "Não gerado: a regra não foi identificada. Leia o trecho acima (ou o regulamento completo), "
              "monte a regra e ajuste o `regra.json` desta pasta; depois rode "
              f"`python amostra_regulamento.py amostra --cnpj {cnpj} --base <base>`.", ""]
    return "\n".join(L)
