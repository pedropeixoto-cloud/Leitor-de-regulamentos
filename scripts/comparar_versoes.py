"""Compara a regra lida por duas versões do leitor, em todos os regulamentos já baixados.

Uso (na pasta do projeto, com os regulamentos em _regulamento\\):

    git archive HEAD -o "%TEMP%\\leitor_head.tar"
    mkdir "%TEMP%\\leitor_head" && tar -xf "%TEMP%\\leitor_head.tar" -C "%TEMP%\\leitor_head"
    python -I scripts/comparar_versoes.py "%TEMP%\\leitor_head"

Compara a versão em <pasta da versão antiga> (normalmente o último commit) com a do disco e lista cada
regulamento em que algum campo da regra ou o status mudou. É a forma de saber o que uma mudança na leitura
faz nos fundos reais antes do commit: os testes mostram que o caso novo funciona, esta comparação mostra
o que mais mudou junto.
"""
from __future__ import annotations

import importlib
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
MODULOS = ("leitura", "secao", "regra", "readme_fundo", "motor_amostra")
CAMPOS = ("metodo", "z", "p", "erro", "quantidade", "subamostra_i_max", "percentual", "minimo", "maximo",
          "limite_integral", "populacao", "integral_categorias", "maiores_por_grupo", "maiores_incluir",
          "maiores_excluir", "selecao", "regra_externa")


def carregar(pasta: Path) -> dict:
    for m in MODULOS:
        sys.modules.pop(m, None)
    sys.path.insert(0, str(pasta))
    try:
        return {m: importlib.import_module(m) for m in ("leitura", "secao", "regra", "readme_fundo")}
    finally:
        sys.path.pop(0)


def ler_todos(mods: dict, regulamentos: list[Path]) -> dict[str, dict]:
    out = {}
    for f in regulamentos:
        texto = mods["leitura"].normalizar(mods["leitura"].extrair_texto(f))
        s = mods["secao"].localizar_secao(texto)
        r = mods["regra"].interpretar(s.completo if s.origem != "nenhuma" else "")
        d = r.para_dict()
        linha = {k: d.get(k) for k in CAMPOS}
        fic = mods["secao"].eh_fic(texto)[0] if hasattr(mods["secao"], "eh_fic") else False
        linha["status"] = "FIC FIDC" if fic else mods["readme_fundo"].status(r, s.avisos)
        linha["origem_trecho"] = s.origem
        out[f.name] = linha
    return out


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    antiga = Path(sys.argv[1]).resolve()
    regulamentos = sorted(p for p in (RAIZ / "_regulamento").rglob("*")
                          if p.suffix.lower() in (".pdf", ".docx", ".zip") and "_antigos" not in p.parts)
    if not regulamentos:
        raise SystemExit("Nenhum regulamento em _regulamento\\. Rode antes: python amostra_regulamento.py buscar")
    print(f"Lendo {len(regulamentos)} regulamentos com as duas versões…", flush=True)
    velho = ler_todos(carregar(antiga), regulamentos)
    novo = ler_todos(carregar(RAIZ), regulamentos)
    mudou = 0
    status_mudou = 0
    for nome, b in novo.items():
        a = velho.get(nome, {})
        dif = {k: (a.get(k), b.get(k)) for k in b if a.get(k) != b.get(k) and k != "origem_trecho"}
        if dif:
            mudou += 1
            status_mudou += "status" in dif
            print(f"{nome[:50]:50} | {json.dumps(dif, ensure_ascii=False)[:300]}")
    print(f"\n{len(novo)} regulamentos | regra ou status diferente em {mudou} | status diferente em {status_mudou}")


if __name__ == "__main__":
    main()
