"""Regras de amostragem da verificação de lastro, lidas do regulamento de cada fundo.

Fluxo: lista de fundos > busca o regulamento vigente no Fundos.NET pelo CNPJ > baixa em _regulamento >
lê a seção de verificação de lastro / amostragem > gera README.md (regra + script) em _script de amostra.

Comandos:
  python amostra_regulamento.py buscar     baixa os regulamentos (só os novos ou atualizados)
  python amostra_regulamento.py ler        lê os regulamentos baixados e gera os README.md
  python amostra_regulamento.py tudo       buscar + ler
  python amostra_regulamento.py amostra --cnpj <cnpj> --base <base.xlsx>   roda a amostra de um fundo
  python amostra_regulamento.py tabela     refaz a tabela _regras.xlsx com a regra de todos os fundos
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import warnings
from dataclasses import fields
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import leitura  # noqa: E402
import motor_amostra  # noqa: E402
import readme_fundo  # noqa: E402
import secao as secao_mod  # noqa: E402
import tabela  # noqa: E402
from fundosnet import Documento, FundosNet, so_digitos  # noqa: E402
from regra import Regra, interpretar  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)
CAMPOS_INDICE = ["cnpj", "nome", "status", "doc_id", "data_entrega", "arquivo", "baixado_em"]
CAMPOS_RESUMO = ["cnpj", "nome", "status", "metodo", "confiabilidade", "n_para_N_1000", "doc_id", "origem_trecho",
                 "pendencias", "pasta"]


# ---------------------------------------------------------------- configuração e lista de fundos

def carregar_config(caminho: Path) -> dict:
    cfg = json.loads(caminho.read_text(encoding="utf-8"))
    base = caminho.parent
    for chave in ("fundos", "regulamentos", "scripts"):
        p = Path(cfg["pastas"][chave])
        cfg["pastas"][chave] = p if p.is_absolute() else (base / p)
    return cfg


def formatar_cnpj(c: str) -> str:
    c = so_digitos(c)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def nome_pasta(texto: str, limite: int = 70) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", texto or "")
    texto = re.sub(r"\s+", " ", texto).strip().rstrip(".")
    return texto[:limite].strip()


def ler_fundos(caminho: Path) -> list[tuple[str, str]]:
    """[(cnpj só dígitos, nome)] da lista de fundos (.xlsx ou .csv com colunas de CNPJ e nome)."""
    if not caminho.exists():
        raise SystemExit(f"Lista de fundos não encontrada: {caminho}. Ajuste pastas.fundos no config.json.")
    cab, linhas = motor_amostra.ler_base(caminho)
    chaves = {motor_amostra._chave(c): c for c in cab}
    col_cnpj = next((chaves[k] for k in chaves if "cnpj" in k), None)
    col_nome = next((chaves[k] for k in chaves
                     if k in ("nome fundo", "nome do fundo", "fundo", "nome", "nome_fundo", "name", "fund name")), None)
    # coluna "Gerar (x)" / "gerar": só as linhas marcadas
    col_gerar = next((chaves[k] for k in chaves if k.startswith("gerar")), None)
    if not col_cnpj:
        raise SystemExit(f"A lista de fundos ({caminho.name}) não tem coluna de CNPJ. Colunas: {', '.join(cab)}")
    vistos, out = set(), []
    for l in linhas:
        if col_gerar and not str(l.get(col_gerar) or "").strip():
            continue
        c = so_digitos(l.get(col_cnpj))
        if c == "0" * 14 or c in vistos:
            continue
        vistos.add(c)
        out.append((c, str(l.get(col_nome) or "").strip() if col_nome else ""))
    return out


def ler_indice(pasta: Path) -> dict[str, dict]:
    p = pasta / "_indice.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        return {l["cnpj"]: l for l in csv.DictReader(f, delimiter=";")}


def gravar_csv(caminho: Path, campos: list[str], linhas: list[dict]):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def filtrar(fundos, cnpjs):
    if not cnpjs:
        return fundos
    alvo = {so_digitos(c) for c in cnpjs}
    return [f for f in fundos if f[0] in alvo] + [(c, "") for c in alvo - {f[0] for f in fundos}]


# ---------------------------------------------------------------- buscar

def cmd_buscar(cfg, args):
    pasta = cfg["pastas"]["regulamentos"]
    pasta.mkdir(parents=True, exist_ok=True)
    indice = ler_indice(pasta)
    fundos = filtrar(ler_fundos(cfg["pastas"]["fundos"]), args.cnpj)
    fn = FundosNet(pausa=cfg.get("fundosnet", {}).get("pausa_segundos", 0.3))
    novos = iguais = falhas = 0
    for i, (cnpj, nome) in enumerate(fundos, 1):
        ant = indice.get(cnpj, {})
        reg = {"cnpj": cnpj, "nome": nome or ant.get("nome", "")}
        try:
            doc = fn.regulamento_vigente(cnpj)
        except ConnectionError as e:
            reg.update(ant, status=f"erro na busca: {e}")
            indice[cnpj] = reg
            falhas += 1
            print(f"[{i}/{len(fundos)}] {formatar_cnpj(cnpj)} ERRO: {e}")
            continue
        if doc is None:
            reg.update(status="sem regulamento no Fundos.NET", doc_id="", data_entrega="", arquivo="")
            indice[cnpj] = reg
            print(f"[{i}/{len(fundos)}] {formatar_cnpj(cnpj)} sem regulamento no Fundos.NET")
            continue
        reg["nome"] = reg["nome"] or doc.nome_fundo
        arquivo_ant = pasta / ant.get("arquivo", "") if ant.get("arquivo") else None
        if not args.forcar and ant.get("doc_id") == str(doc.id) and arquivo_ant and arquivo_ant.exists():
            iguais += 1
            continue
        try:
            dados, ext = fn.baixar(doc.id)
        except ConnectionError as e:
            reg.update(ant, status=f"erro no download: {e}")
            indice[cnpj] = reg
            falhas += 1
            print(f"[{i}/{len(fundos)}] {formatar_cnpj(cnpj)} ERRO no download: {e}")
            continue
        arquivo = f"{cnpj} - {nome_pasta(reg['nome'], 60)} - REG {doc.id}{ext}"
        (pasta / arquivo).write_bytes(dados)
        if arquivo_ant and arquivo_ant.exists() and arquivo_ant.name != arquivo:
            (pasta / "_antigos").mkdir(exist_ok=True)
            arquivo_ant.replace(pasta / "_antigos" / arquivo_ant.name)
        reg.update(status="ok", doc_id=str(doc.id),
                   data_entrega=doc.data_entrega.strftime("%d/%m/%Y %H:%M") if doc.data_entrega else "",
                   arquivo=arquivo, baixado_em=datetime.now().strftime("%d/%m/%Y %H:%M"))
        indice[cnpj] = reg
        novos += 1
        print(f"[{i}/{len(fundos)}] {formatar_cnpj(cnpj)} {'atualizado' if ant else 'baixado'}: {arquivo}")
    gravar_csv(pasta / "_indice.csv", CAMPOS_INDICE, sorted(indice.values(), key=lambda x: x.get("nome", "")))
    print(f"\nRegulamentos: {novos} baixado(s), {iguais} já atualizado(s), {falhas} falha(s). Índice: {pasta / '_indice.csv'}")
    return falhas


# ---------------------------------------------------------------- ler

def regra_de_dict(d: dict) -> Regra:
    nomes = {f.name for f in fields(Regra)}
    r = Regra(**{k: v for k, v in d.items() if k in nomes})
    if isinstance(r.erro_faixa, list):
        r.erro_faixa = tuple(r.erro_faixa)
    return r


def posicionar_regulamento(arquivo: Path, pasta_reg: Path, revisar: bool, subpasta: str) -> Path:
    """Põe o regulamento em _regulamento/<subpasta> (revisão humana) ou na raiz de _regulamento (demais)."""
    destino = (pasta_reg / subpasta if revisar else pasta_reg) / arquivo.name
    if destino != arquivo and arquivo.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        arquivo.replace(destino)
    return destino


def processar_fundo(cnpj: str, nome: str, arquivo: Path, doc: Documento | None, destino_base: Path,
                    pasta_reg: Path | None = None, sub_revisar: str = "_revisar") -> dict:
    texto = leitura.normalizar(leitura.extrair_texto(arquivo))
    sec = secao_mod.localizar_secao(texto)
    if len(texto) < 2000:
        sec.avisos.append("o PDF quase não tem texto (provavelmente digitalizado/imagem): leia o regulamento manualmente")
    pasta = destino_base / f"{cnpj} - {nome_pasta(nome)}"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_regra = pasta / "regra.json"
    revisada = None
    if caminho_regra.exists():
        try:
            antiga = json.loads(caminho_regra.read_text(encoding="utf-8"))
            if antiga.get("revisado_manualmente") and str(antiga.get("doc_id")) == str(doc.id if doc else ""):
                revisada = antiga
        except ValueError:
            pass
    if revisada:
        r = regra_de_dict(revisada["regra"])
        r.pendencias = []
        sec.avisos = []
    else:
        r = interpretar(sec.completo if sec.origem != "nenhuma" else "")
    status = "REVISADO MANUALMENTE" if revisada else readme_fundo.status(r, sec.avisos)
    local = "_regulamento"
    if pasta_reg is not None:
        arquivo = posicionar_regulamento(arquivo, pasta_reg, status == "REVISÃO HUMANA", sub_revisar)
        local = pasta_reg.name if arquivo.parent == pasta_reg else f"{pasta_reg.name}\\{arquivo.parent.name}"
    (pasta / "README.md").write_text(
        readme_fundo.montar(nome=nome, cnpj=cnpj, doc=doc, arquivo=arquivo, secao=sec, r=r, local=local),
        encoding="utf-8")
    caminho_regra.write_text(json.dumps({
        "cnpj": cnpj, "nome": nome, "doc_id": str(doc.id) if doc else "",
        "status": status, "revisado_manualmente": bool(revisada),
        "regra": r.para_dict(), "avisos_leitura": sec.avisos, "origem_trecho": sec.origem,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        n1000 = motor_amostra.tamanho_amostra(r.para_dict(), 1000) if r.metodo != "nao_identificado" else ""
    except (KeyError, TypeError, SystemExit):
        n1000 = ""
    return {"cnpj": formatar_cnpj(cnpj), "nome": nome, "status": status, "metodo": r.metodo,
            "confiabilidade": r.confiabilidade, "n_para_N_1000": n1000, "doc_id": doc.id if doc else "",
            "origem_trecho": sec.origem, "pendencias": " | ".join([*sec.avisos, *r.pendencias]), "pasta": pasta.name,
            "_arquivo": arquivo}


def cmd_ler(cfg, args):
    pasta_reg = cfg["pastas"]["regulamentos"]
    destino = cfg["pastas"]["scripts"]
    sub_revisar = cfg.get("subpastas", {}).get("revisar", "_revisar")
    indice = ler_indice(pasta_reg)
    if not indice:
        raise SystemExit(f"Nenhum regulamento baixado em {pasta_reg}. Rode primeiro: python amostra_regulamento.py buscar")
    da_lista = {c for c, _ in ler_fundos(cfg["pastas"]["fundos"])} if cfg["pastas"]["fundos"].exists() else set(indice)
    alvo = {so_digitos(c) for c in args.cnpj} if args.cnpj else da_lista
    resumo_path = destino / "_resumo.csv"
    resumo = {}
    if resumo_path.exists() and args.cnpj:
        with resumo_path.open(encoding="utf-8-sig", newline="") as f:
            resumo = {so_digitos(l["cnpj"]): l for l in csv.DictReader(f, delimiter=";")}
    erros = 0
    for cnpj, reg in sorted(indice.items(), key=lambda x: x[1].get("nome", "")):
        if alvo and cnpj not in alvo:
            continue
        nome = reg.get("nome") or cnpj
        if reg.get("status") != "ok" or not reg.get("arquivo"):
            resumo[cnpj] = {"cnpj": formatar_cnpj(cnpj), "nome": nome, "status": "SEM REGULAMENTO",
                            "pendencias": reg.get("status", ""), "metodo": "", "confiabilidade": ""}
            continue
        arquivo = pasta_reg / reg["arquivo"]
        if not arquivo.exists():  # movido à mão entre a raiz e a subpasta de revisão
            nome_arq = Path(reg["arquivo"]).name
            arquivo = next((p for p in (pasta_reg / nome_arq, pasta_reg / sub_revisar / nome_arq) if p.exists()), arquivo)
        doc = Documento(id=int(reg["doc_id"]), categoria="Regulamento", tipo="",
                        data_entrega=datetime.strptime(reg["data_entrega"], "%d/%m/%Y %H:%M") if reg.get("data_entrega") else None,
                        data_referencia="", status="Ativo", versao=1, nome_fundo=nome)
        try:
            linha = processar_fundo(cnpj, nome, arquivo, doc, destino, pasta_reg, sub_revisar)
            # caminho relativo à _regulamento, já com a subpasta de revisão quando for o caso
            reg["arquivo"] = linha.pop("_arquivo").relative_to(pasta_reg).as_posix()
            resumo[cnpj] = linha
            print(f"{linha['cnpj']} {linha['status']:<20} {linha['metodo']:<18} {nome[:60]}")
        except Exception as e:  # um regulamento ruim não para o lote
            erros += 1
            resumo[cnpj] = {"cnpj": formatar_cnpj(cnpj), "nome": nome, "status": "ERRO", "pendencias": str(e)}
            print(f"{formatar_cnpj(cnpj)} ERRO ao ler {arquivo.name}: {e}")
    gravar_csv(resumo_path, CAMPOS_RESUMO, sorted(resumo.values(), key=lambda x: x.get("nome", "")))
    gravar_csv(pasta_reg / "_indice.csv", CAMPOS_INDICE, sorted(indice.values(), key=lambda x: x.get("nome", "")))
    print(f"Tabela das regras: {tabela.gerar(list(resumo.values()), destino)}")
    n_rev = sum(1 for p in (pasta_reg / sub_revisar).glob("*") if p.is_file()) if (pasta_reg / sub_revisar).exists() else 0
    print(f"Regulamentos para revisão humana em {pasta_reg / sub_revisar}: {n_rev}")
    cont = {}
    for l in resumo.values():
        cont[l["status"]] = cont.get(l["status"], 0) + 1
    print("\n" + ", ".join(f"{v} {k}" for k, v in sorted(cont.items())) + f". Resumo: {resumo_path}")
    return erros


# ---------------------------------------------------------------- amostra

def cmd_amostra(cfg, args, extras):
    if not args.cnpj or len(args.cnpj) != 1:
        raise SystemExit("Informe um fundo: --cnpj <cnpj>")
    cnpj = so_digitos(args.cnpj[0])
    pastas = list(cfg["pastas"]["scripts"].glob(f"{cnpj} - *"))
    if not pastas or not (pastas[0] / "regra.json").exists():
        raise SystemExit(f"Não há regra gerada para {formatar_cnpj(cnpj)}. Rode: python amostra_regulamento.py tudo --cnpj {cnpj}")
    dados = json.loads((pastas[0] / "regra.json").read_text(encoding="utf-8"))
    if dados["regra"]["metodo"] == "nao_identificado":
        raise SystemExit(f"A regra de {formatar_cnpj(cnpj)} não foi identificada. Revise o regra.json em {pastas[0]} "
                         "(e marque \"revisado_manualmente\": true).")
    if dados.get("status") == "CONFERIR":
        print(f"[AVISO] A regra deste fundo tem pendências (veja o README.md em {pastas[0]}).")
    motor_amostra.main(dados["regra"], extras, nome_saida=f"amostra_{cnpj}.xlsx")


def cmd_tabela(cfg):
    """Refaz o _regras.xlsx a partir do _resumo.csv (sem reler os regulamentos)."""
    destino = cfg["pastas"]["scripts"]
    resumo_path = destino / "_resumo.csv"
    if not resumo_path.exists():
        raise SystemExit(f"Não há {resumo_path}. Rode primeiro: python amostra_regulamento.py ler")
    with resumo_path.open(encoding="utf-8-sig", newline="") as f:
        resumo = list(csv.DictReader(f, delimiter=";"))
    print(f"Tabela das regras: {tabela.gerar(resumo, destino)} ({len(resumo)} fundos)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["buscar", "ler", "tudo", "amostra", "tabela"])
    ap.add_argument("--config", default=str(AQUI / "config.json"))
    ap.add_argument("--cnpj", nargs="+", help="só estes fundos")
    ap.add_argument("--fundos", help="lista de fundos (.xlsx/.csv) no lugar da do config.json")
    ap.add_argument("--forcar", action="store_true", help="baixa de novo mesmo se o regulamento não mudou")
    args, extras = ap.parse_known_args(argv)
    cfg = carregar_config(Path(args.config))
    if args.fundos:
        cfg["pastas"]["fundos"] = Path(args.fundos)
    if args.comando == "amostra":
        if "--base" in extras:
            i = extras.index("--base")
            extras = [extras[i + 1], *extras[:i], *extras[i + 2:]]
        return cmd_amostra(cfg, args, extras)
    if extras:
        ap.error(f"opções desconhecidas: {' '.join(extras)}")
    if args.comando == "tabela":
        return cmd_tabela(cfg)
    erros = 0
    if args.comando in ("buscar", "tudo"):
        erros += cmd_buscar(cfg, args)
    if args.comando in ("ler", "tudo"):
        erros += cmd_ler(cfg, args)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
