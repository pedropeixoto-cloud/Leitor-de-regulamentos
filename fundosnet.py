"""Busca e download de regulamentos no Fundos.NET (B3).

Usa a mesma API JSON da tela pública
https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM
(só biblioteca padrão do Python).
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

BASE = "https://fnet.bmfbovespa.com.br/fnet/publico"
CATEGORIA_REGULAMENTO = 5          # idCategoriaDocumento de "Regulamento"
CATEGORIA_ATOS_ADMINISTRADOR = 11  # "Atos de Deliberação do Administrador" (alterações de regulamento)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) auditoria-lastro/1.0"


def so_digitos(cnpj) -> str:
    return re.sub(r"\D", "", str(cnpj or "")).zfill(14)


@dataclass
class Documento:
    id: int
    categoria: str
    tipo: str
    data_entrega: datetime | None
    data_referencia: str
    status: str
    versao: int
    nome_fundo: str

    @property
    def ativo(self) -> bool:
        return self.status.lower().startswith("ativo")

    @classmethod
    def do_json(cls, x: dict) -> "Documento":
        try:
            entrega = datetime.strptime(x.get("dataEntrega") or "", "%d/%m/%Y %H:%M")
        except ValueError:
            entrega = None
        return cls(
            id=int(x["id"]),
            categoria=(x.get("categoriaDocumento") or "").strip(),
            tipo=(x.get("tipoDocumento") or "").strip(),
            data_entrega=entrega,
            data_referencia=(x.get("dataReferencia") or "").strip(),
            status=(x.get("descricaoStatus") or "").strip(),
            versao=int(x.get("versao") or 1),
            nome_fundo=(x.get("descricaoFundo") or "").strip(),
        )


class FundosNet:
    def __init__(self, timeout: int = 60, pausa: float = 0.3, tentativas: int = 3):
        self.timeout = timeout
        self.pausa = pausa
        self.tentativas = tentativas
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._sessao_aberta = False

    def _get(self, url: str, ajax: bool = False) -> tuple[bytes, dict]:
        headers = {"User-Agent": USER_AGENT}
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        erro = None
        for tentativa in range(self.tentativas):
            try:
                req = urllib.request.Request(url, headers=headers)
                with self._opener.open(req, timeout=self.timeout) as r:
                    dados = r.read()
                    time.sleep(self.pausa)
                    return dados, dict(r.headers)
            except Exception as e:  # rede instável: tenta de novo
                erro = e
                time.sleep(2 * (tentativa + 1))
        raise ConnectionError(f"Fundos.NET não respondeu ({url}): {erro}")

    def _abrir_sessao(self):
        if not self._sessao_aberta:
            self._get(f"{BASE}/abrirGerenciadorDocumentosCVM")
            self._sessao_aberta = True

    def documentos(self, cnpj: str, categoria: int | None = None) -> list[Documento]:
        """Todos os documentos do fundo (ou da classe) no Fundos.NET, mais recentes primeiro."""
        self._abrir_sessao()
        docs, inicio, pagina = [], 0, 200
        while True:
            params = {
                "d": 1, "s": inicio, "l": pagina,
                "o[0][dataEntrega]": "desc",
                "cnpjFundo": so_digitos(cnpj),
            }
            if categoria is not None:
                params["idCategoriaDocumento"] = categoria
            url = f"{BASE}/pesquisarGerenciadorDocumentosDados?{urllib.parse.urlencode(params)}"
            dados, _ = self._get(url, ajax=True)
            try:
                resp = json.loads(dados.decode("utf-8"))
            except ValueError as e:
                raise ConnectionError(f"Fundos.NET devolveu uma resposta inesperada para {cnpj}") from e
            lote = resp.get("data") or []
            docs += [Documento.do_json(x) for x in lote]
            inicio += len(lote)
            if not lote or inicio >= int(resp.get("recordsTotal") or 0):
                return docs

    def regulamento_vigente(self, cnpj: str) -> Documento | None:
        """O regulamento ativo entregue por último.

        Se o fundo não tem documento na categoria Regulamento, usa o último
        "Instrumento Particular de Alteração do Regulamento" (que costuma trazer o
        regulamento consolidado anexo).
        """
        regs = [d for d in self.documentos(cnpj, CATEGORIA_REGULAMENTO) if d.ativo]
        if not regs:
            regs = [d for d in self.documentos(cnpj, CATEGORIA_ATOS_ADMINISTRADOR)
                    if d.ativo and "regulamento" in d.tipo.lower()]
        regs.sort(key=lambda d: (d.data_entrega or datetime.min, d.id), reverse=True)
        return regs[0] if regs else None

    def baixar(self, doc_id: int) -> tuple[bytes, str]:
        """Conteúdo do documento e a extensão (.pdf, .docx…) informada pelo Fundos.NET."""
        dados, headers = self._get(f"{BASE}/downloadDocumento?id={doc_id}")
        nome = ""
        disp = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
        m = re.search(r'filename="?([^";]+)', disp)
        if m:
            nome = m.group(1)
        ext = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ""
        if not ext:
            ext = ".pdf" if dados[:4] == b"%PDF" else ".bin"
        # Alguns documentos antigos vêm em base64 dentro do corpo
        if ext == ".pdf" and not dados.startswith(b"%PDF"):
            import base64
            try:
                bruto = base64.b64decode(dados.strip(b'"'), validate=False)
                if bruto.startswith(b"%PDF"):
                    dados = bruto
            except ValueError:
                pass
        return dados, ext
