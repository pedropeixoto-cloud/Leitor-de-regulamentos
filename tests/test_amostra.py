"""Testes com textos e bases fictícios (sem acesso à internet)."""
import csv
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))

import fundosnet  # noqa: E402
import leitura  # noqa: E402
import motor_amostra  # noqa: E402
import readme_fundo  # noqa: E402
import secao  # noqa: E402
from regra import interpretar  # noqa: E402

ANEXO_FORMULA = """ANEXO III
CRITÉRIOS PARA A VERIFICAÇÃO DO LASTRO DOS DIREITOS CREDITÓRIOS POR AMOSTRAGEM DA CLASSE ÚNICA DO FUNDO TESTE
Para a verificação do lastro dos Direitos Creditórios, a Gestora deverá utilizar os seguintes procedimentos:
(b) seleção de uma amostra aleatória de itens a serem verificados: (1) dividindo-se o tamanho da população (N) pelo tamanho da amostra (n), obtendo um intervalo de retirada (K); (2) sorteando-se o ponto de partida; e (3) retirando-se uma amostra a cada K elementos;
Tamanho da amostra:
O tamanho da amostra será definido por meio da aplicação da seguinte fórmula matemática:
n = N * z² * p * (1 – p) ME² * (N – 1) + z² * p * (1-p) Onde: n = tamanho da amostra N = totalidade de Direitos Creditórios adquiridos z = Critical score = 1,96 p = proporção a ser estimada = 50% ME = erro médio = 5,8%
Sem prejuízo do disposto abaixo, a população base para a seleção da amostra compreenderá os Direitos Creditórios em aberto (a vencer) e Direitos Creditórios recomprados no trimestre de referência.
Além da verificação por amostragem, serão verificados, ainda, 100% (cem por cento) dos Direitos Creditórios inadimplidos e os substituídos no referido trimestre.
A seleção dos Direitos Creditórios será obtida da seguinte forma: (1) para as 5 (cinco) Cedentes mais representativas em aberto na carteira e para as 5 (cinco) Cedentes mais representativas que tiveram títulos recomprados, serão selecionados os 3 (três) Direitos Creditórios de maior valor; e, (2) adicionalmente, serão selecionados os demais itens para completar a quantidade total de itens da amostra.
ESTE ANEXO É PARTE INTEGRANTE DO REGULAMENTO DO FUNDO TESTE
ANEXO IV
MODELO DE APÊNDICE DAS COTAS SENIORES
"""

ANEXO_120 = """(b) seleção de uma amostra aleatória de itens a serem verificados. A seleção será obtida da seguinte forma:
(i) A amostra total (N) compreende 120 (cento e vinte) itens distribuídos da seguinte forma; (ii) Amostra (I) da carteira de direitos creditórios inadimplidos e substituídos no trimestre; (iii) Amostra (A) da carteira de direitos creditórios a vencer na data base da seleção; (iv) Para distribuição da amostra será dividido o tamanho da população (N – I) pelo tamanho da População (P), obtendo um intervalo de retirada (K), sorteia-se o ponto de partida, e a cada "K" elementos, será retirado um para a amostra.
(c) a totalidade dos créditos inadimplidos e os substituídos no referido trimestre, serão objeto de verificação individual pelo custodiante, desta carteira, será ainda selecionada uma amostra de até 36 (trinta e seis) itens para compor a Amostra (I) prevista no item acima.
"""


def base_ficticia(n=1000, semente=1):
    rnd = random.Random(semente)
    cab = ["SEU_NUMERO", "NOME_CEDENTE", "VALOR_PRESENTE", "SITUACAO_RECEBIVEL"]
    sits = ["A vencer"] * 85 + ["Vencido"] * 8 + ["Recompra"] * 5 + ["Substituído"] * 2
    dados = [{"SEU_NUMERO": f"T{i:05d}", "NOME_CEDENTE": f"CED {rnd.randint(1, 20):02d}",
              "VALOR_PRESENTE": round(rnd.lognormvariate(8, 1.2), 2), "SITUACAO_RECEBIVEL": rnd.choice(sits)}
             for i in range(n)]
    return cab, dados


class TestRegra(unittest.TestCase):
    def test_modelo_formula(self):
        r = interpretar(ANEXO_FORMULA)
        self.assertEqual(r.metodo, "formula_cochran")
        self.assertEqual((r.z, r.p, r.erro), (1.96, 0.5, 0.058))
        self.assertEqual(r.populacao, ["a_vencer", "recomprados"])
        self.assertEqual(sorted(r.integral_categorias), ["inadimplidos", "substituidos"])
        self.assertEqual(r.maiores_por_grupo, {"grupo": "cedente", "n_grupos": 5, "n_itens": 3,
                                               "bases": ["em_aberto", "recomprados"]})
        self.assertEqual(r.selecao, "sistematica")
        self.assertEqual(r.confiabilidade, "alta")

    def test_integral(self):
        r = interpretar("11.7 Os Documentos Comprobatórios serão recebidos e verificados, de forma individualizada e "
                        "integral, pelo Gestor previamente à Data de Aquisição.")
        self.assertEqual(r.metodo, "integral")
        self.assertEqual(r.pendencias, [])

    def test_integralidade_generica_nao_e_integral(self):
        r = interpretar("(j) verificação da existência, integralidade e titularidade do lastro dos Direitos Creditórios, "
                        "podendo contratar terceiros.")
        self.assertEqual(r.metodo, "nao_identificado")

    def test_quantidade_com_amostra_i(self):
        r = interpretar(ANEXO_120)
        self.assertEqual((r.metodo, r.quantidade, r.subamostra_i_max), ("quantidade_fixa", 120, 36))
        self.assertEqual(r.populacao, ["a_vencer"])

    def test_confianca_vira_z_e_exclusao_de_maiores(self):
        r = interpretar("O tamanho da amostra considera nível de confiança de 90% e margem de erro de 5%. "
                        "Serão excluídos da população os 10 (dez) maiores Direitos Creditórios.")
        self.assertEqual((r.metodo, r.z, r.erro, r.maiores_excluir), ("formula_cochran", 1.645, 0.05, 10))

    def test_faixa_de_erro(self):
        r = interpretar("Eo = Erro Amostral Tolerável (o erro amostral tolerável será entre 5% (cinco por cento) e "
                        "10% (dez por cento)); N = tamanho da população.")
        self.assertEqual(r.metodo, "formula_yamane")
        self.assertEqual(r.erro, 0.05)
        self.assertTrue(r.pendencias)

    def test_sem_parametros_vai_para_revisao(self):
        r = interpretar("O responsável realizará a verificação do lastro por amostragem, de acordo com as diretrizes "
                        "descritas no presente Anexo.")
        self.assertEqual(r.metodo, "nao_identificado")
        self.assertIn("não define o tamanho", r.pendencias[0])

    def test_limite_integral(self):
        r = interpretar(ANEXO_FORMULA + "\nCaso o número de Itens a serem verificados seja superior a 100 (cem), a "
                        "amostragem será aplicável.")
        self.assertEqual(r.limite_integral, 100)
        self.assertEqual(motor_amostra.tamanho_amostra(r.para_dict(), 80), 80)


class TestSecao(unittest.TestCase):
    def test_ignora_sumario_e_acha_anexo(self):
        texto = ("SUMÁRIO\nANEXO III - CRITÉRIOS PARA A VERIFICAÇÃO DO LASTRO ........ 82\n"
                 "CAPÍTULO 1\n1.1 O Fundo é regido por este Regulamento.\n" + "texto qualquer.\n" * 50
                 + "7.4. A Gestora fará a verificação do lastro por amostragem, na forma do Anexo III.\n"
                 + ANEXO_FORMULA)
        s = secao.localizar_secao(texto)
        self.assertEqual(s.origem, "anexo")
        self.assertTrue(s.texto.startswith("ANEXO III"))
        self.assertIn("5,8%", s.texto)
        self.assertNotIn("MODELO DE APÊNDICE", s.texto)

    def test_clausulas(self):
        texto = ("Risco da Verificação do Lastro por Amostragem - a carteira poderá conter direitos com problemas.\n"
                 "Verificação do Lastro\n"
                 "11.7 Os Documentos Comprobatórios serão recebidos e verificados, de forma individualizada e integral, "
                 "pelo Gestor previamente à Data de Aquisição.\n12. CONDIÇÕES DE CESSÃO\n")
        s = secao.localizar_secao(texto)
        self.assertEqual(s.origem, "clausulas")
        self.assertIn("individualizada e integral", s.texto)
        self.assertNotIn("Risco", s.texto)

    def test_anexo_citado_que_nao_existe(self):
        s = secao.localizar_secao("6.4. A verificação do lastro por amostragem será realizada conforme a metodologia "
                                  "disposta no Anexo III deste Anexo Descritivo.\n")
        self.assertTrue(any("Anexo III" in a for a in s.avisos))

    def test_normalizar_junta_linhas(self):
        n = leitura.normalizar("A verificação do lastro\nserá feita por\namostragem.\n\n(a) primeiro item;\n12\n(b) segundo.")
        self.assertIn("A verificação do lastro será feita por amostragem.", n)
        self.assertIn("(a) primeiro item;", n)
        self.assertNotIn("\n12\n", n)


class TestMotor(unittest.TestCase):
    def regra(self, texto=ANEXO_FORMULA):
        return interpretar(texto).para_dict()

    def test_tamanho_formula(self):
        r = self.regra()
        self.assertEqual([motor_amostra.tamanho_amostra(r, n) for n in (100, 1000, 10000)], [75, 223, 278])

    def test_amostra_modelo_formula(self):
        cab, dados = base_ficticia()
        col = motor_amostra.achar_colunas(cab)
        amostra, _, res = motor_amostra.gerar_amostra(dados, col, self.regra(), date(2026, 9, 30), 42)
        motivos = [m for _, m in amostra]
        # todos os vencidos e substituídos entram a 100%
        self.assertEqual(res["verificados_100"], res["base_vencidos"] + res["base_substituidos"])
        self.assertEqual(res["populacao_N"], res["base_a_vencer"] + res["base_recomprados"])
        self.assertEqual(res["amostra_n"], motor_amostra.tamanho_amostra(self.regra(), res["populacao_N"]))
        self.assertEqual(res["obrigatorios_maiores"] + res["sorteados"], res["amostra_n"])
        self.assertTrue(any(m.startswith("maior valor do cedente") for m in motivos))
        self.assertEqual(len(amostra), res["total_a_verificar"])
        # mesma semente, mesma amostra
        _, dados2 = base_ficticia()
        amostra2, _, _ = motor_amostra.gerar_amostra(dados2, col, self.regra(), date(2026, 9, 30), 42)
        self.assertEqual([l["SEU_NUMERO"] for l, _ in amostra], [l["SEU_NUMERO"] for l, _ in amostra2])

    def test_maiores_sao_os_maiores_do_cedente(self):
        cab, dados = base_ficticia()
        col = motor_amostra.achar_colunas(cab)
        amostra, _, _ = motor_amostra.gerar_amostra(dados, col, self.regra(), date(2026, 9, 30), 1)
        ced = next(m for _, m in amostra if m.endswith("(em aberto)")).split("cedente ")[1].replace(" (em aberto)", "")
        abertos = sorted((l for l in dados if l["NOME_CEDENTE"] == ced and l["_cat"] == "a_vencer"),
                         key=lambda l: -l["_valor"])
        escolhidos = {l["SEU_NUMERO"] for l, m in amostra if m == f"maior valor do cedente {ced} (em aberto)"}
        self.assertTrue({l["SEU_NUMERO"] for l in abertos[:3]} <= escolhidos)

    def test_amostra_i_e_a(self):
        cab, dados = base_ficticia()
        col = motor_amostra.achar_colunas(cab)
        amostra, _, res = motor_amostra.gerar_amostra(dados, col, self.regra(ANEXO_120), date(2026, 9, 30), 3)
        self.assertEqual(res["amostra_i"], 36)
        self.assertEqual(res["amostra_n"], 120 - 36)
        self.assertEqual(sum(1 for _, m in amostra if m.startswith("Amostra (I)")), 36)

    def test_exclusao_de_maiores(self):
        cab, dados = base_ficticia()
        col = motor_amostra.achar_colunas(cab)
        r = self.regra("Tamanho da amostra com nível de confiança de 95% e margem de erro de 5%. "
                       "Serão excluídos da população os 10 (dez) maiores Direitos Creditórios.")
        amostra, excluidos, res = motor_amostra.gerar_amostra(dados, col, r, date(2026, 9, 30), 3)
        self.assertEqual(len(excluidos), 10)
        top = sorted((l for l in dados if l["_cat"] == "a_vencer"), key=lambda l: -l["_valor"])[:10]
        self.assertEqual({l["SEU_NUMERO"] for l in excluidos}, {l["SEU_NUMERO"] for l in top})
        self.assertFalse({l["SEU_NUMERO"] for l in excluidos} & {l["SEU_NUMERO"] for l, _ in amostra})

    def test_situacao_pelo_vencimento(self):
        col = motor_amostra.achar_colunas(["ID", "VALOR", "DATA_VENCIMENTO"])
        self.assertEqual(motor_amostra.categoria({"DATA_VENCIMENTO": "15/08/2026"}, col, date(2026, 9, 30)), "vencidos")
        self.assertEqual(motor_amostra.categoria({"DATA_VENCIMENTO": "2026-12-01"}, col, date(2026, 9, 30)), "a_vencer")

    def test_numeros_brasileiros(self):
        self.assertEqual(motor_amostra._valor("1.234,56"), 1234.56)
        self.assertEqual(motor_amostra._valor("R$ 10,5"), 10.5)


class TestReadme(unittest.TestCase):
    def test_script_do_readme_roda(self):
        sec = secao.localizar_secao(ANEXO_FORMULA)
        r = interpretar(sec.completo)
        doc = fundosnet.Documento(id=123, categoria="Regulamento", tipo="", data_entrega=datetime(2026, 4, 17),
                                  data_referencia="", status="Ativo", versao=1, nome_fundo="FUNDO TESTE")
        md = readme_fundo.montar(nome="FUNDO TESTE", cnpj="12345678000190", doc=doc, arquivo=None, secao=sec, r=r)
        self.assertIn("12.345.678/0001-90", md)
        self.assertIn("✅", md)
        codigo = md.split("```python\n", 1)[1].split("```", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "amostra.py").write_text(codigo, encoding="utf-8")
            cab, dados = base_ficticia(300)
            with (tmp / "base.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cab, delimiter=";")
                w.writeheader()
                for l in dados:
                    w.writerow({**l, "VALOR_PRESENTE": str(l["VALOR_PRESENTE"]).replace(".", ",")})
            res = subprocess.run([sys.executable, "-I", "amostra.py", "base.csv", "--data-base", "2026-09-30",
                                  "--semente", "5", "--saida", "saida.xlsx"], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((tmp / "saida.xlsx").exists())

    def test_regra_nao_identificada_nao_gera_script(self):
        sec = secao.Secao(texto="", origem="nenhuma")
        md = readme_fundo.montar(nome="X", cnpj="12345678000190", doc=None, arquivo=None, secao=sec, r=interpretar(""))
        self.assertIn("Revisão humana", md)
        self.assertNotIn("```python", md)


class TestFundosNet(unittest.TestCase):
    def test_escolhe_regulamento_ativo_mais_recente(self):
        def doc(i, entrega, status="Ativo com visualização"):
            return fundosnet.Documento.do_json({"id": i, "categoriaDocumento": "Regulamento", "dataEntrega": entrega,
                                                "descricaoStatus": status})
        fn = fundosnet.FundosNet()
        fn.documentos = lambda cnpj, categoria=None: [doc(1, "29/04/2025 19:21"), doc(3, "17/04/2026 10:42", "Cancelado"),
                                                       doc(2, "02/01/2026 15:53")]
        self.assertEqual(fn.regulamento_vigente("1").id, 2)

    def test_so_digitos(self):
        self.assertEqual(fundosnet.so_digitos("48.169.685/0001-20"), "48169685000120")


class TestFic(unittest.TestCase):
    def test_titulo_fic(self):
        for titulo in ("REGULAMENTO DO SIG VI FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO EM DIREITOS CREDITÓRIOS CNPJ nº 1",
                       "Página 4 de 49 REGULAMENTO DO ATLAS FUNDO DE INVESTIMENTO EM COTAS DE FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS",
                       "REGULAMENTO DO IGNIS FUNDO DE INVESTIMENTO EM COTAS DE FUNDO DEINVESTIMENTO EM DIREITOS CREDITÓRIOS CNPJ: 1",
                       "REGULAMENTO DO MANACÁ FUNDO DE INVESTIMENTO EM COTAS DE FIDC RESPONSABILIDADE LIMITADA CNPJ/MF nº 1"):
            self.assertTrue(secao.eh_fic(titulo)[0], titulo)

    def test_assinatura_de_cotista_fic_nao_conta(self):
        texto = ("REGULAMENTO DO AMALFI FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS CNPJ/MF nº 1 Esse documento foi "
                 "assinado por Fulano e BRM CARBYNE CRÉDITO ESTRUTURADO FIC FIDC RL.")
        self.assertFalse(secao.eh_fic(texto)[0])

    def test_politica_de_investimento(self):
        texto = ("REGULAMENTO DO INVICTO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS CNPJ 1\n"
                 "Artigo 39. Considerando que a Classe investe preponderantemente em cotas de outros FIDCs, não é possível detalhar.")
        self.assertTrue(secao.eh_fic(texto)[0])

    def test_procedimentos_pre_acordados(self):
        r = interpretar("Artigo 15. Para fins da verificação da existência, integridade e titularidade do lastro, a verificação "
                        "pela Gestora poderá ser efetuada: (a) de forma individualizada; (b) por amostragem, utilizando modelo "
                        "estatístico consistente e passível de verificação, conforme previsto neste Regulamento e nas políticas "
                        "da Gestora, sendo que tais regras estão disponíveis no website da Administradora.")
        self.assertTrue(r.regra_externa)
        self.assertEqual(readme_fundo.status(r, []), "PROCEDIMENTOS PRÉ-ACORDADOS")
        self.assertEqual(readme_fundo.status(interpretar("verificação do lastro por amostragem, conforme as diretrizes "
                                                          "do presente Anexo."), []), "REVISÃO HUMANA")


def docx_ficticio(caminho: Path, texto: str):
    import zipfile
    from xml.sax.saxutils import escape
    corpo = "".join(f"<w:p><w:r><w:t>{escape(l)}</w:t></w:r></w:p>" for l in texto.split("\n"))
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="w"><w:body>{corpo}</w:body></w:document>')


class TestPastaRevisar(unittest.TestCase):
    def test_revisao_humana_vai_para_revisar_e_volta(self):
        import json
        import amostra_regulamento as app
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reg = tmp / "_regulamento"
            reg.mkdir()
            enchimento = "\n".join(f"{i}.1 Cláusula genérica número {i} do regulamento." for i in range(60))
            docx_ficticio(reg / "11111111000111 - FUNDO OK - REG 1.docx", enchimento + "\n" + ANEXO_FORMULA)
            docx_ficticio(reg / "22222222000122 - FUNDO SEM REGRA - REG 2.docx",
                          enchimento + "\nO Gestor verificará o lastro por amostragem, conforme as diretrizes descritas no presente Anexo.")
            linhas = [{"cnpj": "11111111000111", "nome": "FUNDO OK", "status": "ok", "doc_id": "1",
                       "data_entrega": "01/01/2026 10:00", "arquivo": "11111111000111 - FUNDO OK - REG 1.docx"},
                      {"cnpj": "22222222000122", "nome": "FUNDO SEM REGRA", "status": "ok", "doc_id": "2",
                       "data_entrega": "01/01/2026 10:00", "arquivo": "22222222000122 - FUNDO SEM REGRA - REG 2.docx"}]
            app.gravar_csv(reg / "_indice.csv", app.CAMPOS_INDICE, linhas)
            (tmp / "config.json").write_text(json.dumps({
                "pastas": {"fundos": "nao_existe.xlsx", "regulamentos": "_regulamento", "scripts": "_script de amostra"},
                "subpastas": {"revisar": "_revisar"}}), encoding="utf-8")
            self.assertEqual(app.main(["ler", "--config", str(tmp / "config.json")]), 0)

            self.assertTrue((reg / "11111111000111 - FUNDO OK - REG 1.docx").exists())
            self.assertTrue((reg / "_revisar" / "22222222000122 - FUNDO SEM REGRA - REG 2.docx").exists())
            self.assertFalse((reg / "22222222000122 - FUNDO SEM REGRA - REG 2.docx").exists())
            indice = app.ler_indice(reg)
            self.assertEqual(indice["22222222000122"]["arquivo"], "_revisar/22222222000122 - FUNDO SEM REGRA - REG 2.docx")
            readme = next((tmp / "_script de amostra").glob("2222*")) / "README.md"
            self.assertIn("_regulamento\\_revisar", readme.read_text(encoding="utf-8"))

            # rodar de novo não quebra (o arquivo já está na subpasta)
            self.assertEqual(app.main(["ler", "--config", str(tmp / "config.json")]), 0)
            self.assertTrue((reg / "_revisar" / "22222222000122 - FUNDO SEM REGRA - REG 2.docx").exists())

            # depois da revisão manual, o regulamento volta para a raiz
            caminho_regra = next((tmp / "_script de amostra").glob("2222*")) / "regra.json"
            dados = json.loads(caminho_regra.read_text(encoding="utf-8"))
            dados["revisado_manualmente"] = True
            dados["regra"].update(metodo="quantidade_fixa", quantidade=50, populacao=["a_vencer"], pendencias=[])
            caminho_regra.write_text(json.dumps(dados), encoding="utf-8")
            self.assertEqual(app.main(["ler", "--config", str(tmp / "config.json")]), 0)
            self.assertTrue((reg / "22222222000122 - FUNDO SEM REGRA - REG 2.docx").exists())
            self.assertFalse((reg / "_revisar" / "22222222000122 - FUNDO SEM REGRA - REG 2.docx").exists())

            # a tabela das regras sai junto com o ler
            import openpyxl
            ws = openpyxl.load_workbook(tmp / "_script de amostra" / "_regras.xlsx")["Regras"]
            cab = [c.value for c in ws[4]]
            linhas = {r[0]: dict(zip(cab, r)) for r in ws.iter_rows(min_row=5, values_only=True)}
            ok = linhas["11.111.111/0001-11"]
            self.assertEqual((ok["Status"], ok["z"], ok["p"], ok["Erro (E)"], ok["n p/ N = 1.000"]), ("OK", 1.96, 0.5, 0.058, 223))
            self.assertIn("5 cedentes", ok["Maiores obrigatórios"])
            self.assertEqual(linhas["22.222.222/0001-22"]["Status"], "REVISADO MANUALMENTE")
            self.assertEqual(linhas["22.222.222/0001-22"]["n p/ N = 1.000"], 50)

    def test_fic_e_procedimentos_vao_para_pastas_proprias(self):
        import json
        import amostra_regulamento as app
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reg = tmp / "_regulamento"
            reg.mkdir()
            ench = "\n".join(f"{i}.1 Cláusula genérica número {i} do regulamento." for i in range(60))
            fundos = {
                # nome na lista NÃO diz que é FIC: o que vale é o título do regulamento
                "33333333000133": ("FUNDO X", "REGULAMENTO DO X FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO "
                                              "EM DIREITOS CREDITÓRIOS CNPJ 1\n" + ench),
                "44444444000144": ("FUNDO Y", "REGULAMENTO DO Y FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS CNPJ 1\n" + ench +
                                   "\nArtigo 15. A verificação do lastro pela Gestora poderá ser efetuada de forma individualizada "
                                   "ou por amostragem, utilizando modelo estatístico consistente, conforme as políticas da "
                                   "Gestora, sendo que tais regras estão disponíveis no website da Administradora."),
                "55555555000155": ("FUNDO Z", "REGULAMENTO DO Z FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS CNPJ 1\n" + ench +
                                   "\nO Gestor verificará o lastro por amostragem, conforme as diretrizes descritas no presente Anexo."),
            }
            linhas = []
            for c, (nome, texto) in fundos.items():
                arq = f"{c} - {nome} - REG 9.docx"
                docx_ficticio(reg / arq, texto)
                linhas.append({"cnpj": c, "nome": nome, "status": "ok", "doc_id": "9", "data_entrega": "", "arquivo": arq})
            app.gravar_csv(reg / "_indice.csv", app.CAMPOS_INDICE, linhas)
            (tmp / "config.json").write_text(json.dumps({"pastas": {
                "fundos": "nao_existe.xlsx", "regulamentos": "_regulamento", "scripts": "_script de amostra"}}), encoding="utf-8")
            self.assertEqual(app.main(["ler", "--config", str(tmp / "config.json")]), 0)
            self.assertTrue((reg / "_FIC FIDC" / "33333333000133 - FUNDO X - REG 9.docx").exists())
            self.assertTrue((reg / "_Procedimentos pré acordados" / "44444444000144 - FUNDO Y - REG 9.docx").exists())
            self.assertTrue((reg / "_revisar" / "55555555000155 - FUNDO Z - REG 9.docx").exists())
            indice = app.ler_indice(reg)
            self.assertEqual(indice["33333333000133"]["arquivo"], "_FIC FIDC/33333333000133 - FUNDO X - REG 9.docx")
            readme = (next((tmp / "_script de amostra").glob("4444*")) / "README.md").read_text(encoding="utf-8")
            self.assertIn("Procedimentos pré-acordados", readme)
            # rodar de novo mantém tudo no lugar
            self.assertEqual(app.main(["ler", "--config", str(tmp / "config.json")]), 0)
            self.assertTrue((reg / "_FIC FIDC" / "33333333000133 - FUNDO X - REG 9.docx").exists())


if __name__ == "__main__":
    unittest.main()
