# Amostra pelo regulamento

A Resolução CVM 175 permite verificar o lastro dos direitos creditórios por amostragem, mas cada fundo define no
**regulamento** como a amostra é montada: fórmula estatística, quantidade fixa, verificação de 100% da carteira,
os maiores por cedente, exclusão dos maiores etc. Esta ferramenta lê a regra no regulamento de cada fundo e gera um
script que monta a amostra conforme essa regra.

```
lista de fundos ─► Fundos.NET (CNPJ) ─► _regulamento\ ─► seção de amostragem ─► _script de amostra\<fundo>\README.md
```

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

1. Coloque a lista de fundos em `entrada/fundos.xlsx` (colunas `Nome Fundo` e `CNPJ`, a mesma lista da Geradora CVM;
   também aceita `.csv`). Para usar outro arquivo ou gravar no G:, ajuste `pastas` no `config.json`.
2. Rode:
   ```bash
   python amostra_regulamento.py tudo
   ```
   - `buscar`: procura no [Fundos.NET](https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM) o
     regulamento **ativo mais recente** de cada CNPJ (categoria "Regulamento"; se não houver, o último
     "Instrumento Particular de Alteração do Regulamento") e baixa em `_regulamento\`. Na próxima execução só baixa
     o que mudou. A versão anterior vai para `_regulamento\_antigos\`.
   - `ler`: lê cada regulamento, acha a seção de verificação de lastro, interpreta a regra e grava, por fundo,
     `_script de amostra\<CNPJ> - <nome>\README.md` e `regra.json`.
   - `tudo`: os dois.
   - `--cnpj 48.169.685/0001-20 ...` limita a alguns fundos. `--forcar` baixa de novo mesmo sem mudança.
   - `--fundos <arquivo.xlsx>` usa outra lista de fundos. A lista precisa de uma coluna de CNPJ e aceita `Nome Fundo`,
     `Nome` ou `Name` como nome. Se tiver uma coluna `Gerar`, só entram as linhas marcadas.
3. Abra `_script de amostra\_resumo.csv` e trate os fundos por status (abaixo).
4. Na hora da auditoria, gere a amostra com a base analítica do fundo (uma linha por recebível):
   ```bash
   python amostra_regulamento.py amostra --cnpj 48.169.685/0001-20 --base base.xlsx --data-base 2026-09-30
   ```
   Ou copie o script do `README.md` do fundo e rode-o sozinho (ele não depende desta pasta).

### Saídas

```
_regulamento\
  <CNPJ> - <nome> - REG <id>.pdf    regulamento vigente baixado do Fundos.NET
  _revisar\                         regulamentos dos fundos em REVISÃO HUMANA (movidos pelo ler)
  _antigos\                         versões anteriores substituídas por um regulamento novo
  _indice.csv                       CNPJ, documento, data de entrega e arquivo (com a subpasta) de cada fundo
_script de amostra\
  _regras.xlsx                      tabela com a regra de todos os fundos (abas Regras e Resumo)
  _resumo.csv                       status, método, pendências e n para N = 1.000 de cada fundo
  <CNPJ> - <nome>\README.md         regra, trecho do regulamento e script da amostra
  <CNPJ> - <nome>\regra.json        a mesma regra em formato de dados (usada pelo comando amostra)
```

### Tabela das regras (`_regras.xlsx`)

O `ler` gera uma planilha com uma linha por fundo: status (colorido), método, tamanho da amostra por extenso, os
parâmetros (z, confiança, p, erro, quantidade, Amostra I, percentual, mínimo, máximo, limite para verificar tudo),
população base, categorias verificadas a 100%, maiores obrigatórios ou excluídos, forma de seleção, pendências,
observações e o link do regulamento no Fundos.NET. As colunas **n p/ N = 100 / 1.000 / 10.000** mostram o tamanho
da amostra que a regra do fundo dá para cada população, com o mesmo cálculo do script de amostra. Os itens verificados a
100% não entram no n. A aba **Resumo** conta os fundos por status e por método. Tem filtro em todas as colunas e
cabeçalho congelado. Para refazer só a tabela, sem reler os regulamentos:

```bash
python amostra_regulamento.py tabela
```

### Status

| Status | Significado | O que fazer |
|---|---|---|
| `OK` | Regra identificada sem pendências | Conferir o README por amostragem e usar |
| `CONFERIR` | Regra identificada, mas com algum parâmetro assumido ou ambíguo | Ler as **Pendências** do README e confirmar com o trecho |
| `REVISÃO HUMANA` | O regulamento não traz a regra, ou ela não foi reconhecida | Ler o regulamento e preencher o `regra.json` à mão |
| `SEM REGULAMENTO` | Fundo sem regulamento no Fundos.NET | Conferir o CNPJ (classe x fundo) |

Para registrar uma regra revisada à mão, edite o `regra.json` do fundo e marque `"revisado_manualmente": true`.
O `ler` passa a usar essa regra (e não a sobrescreve) enquanto o regulamento for o mesmo documento. Se o fundo
publicar um regulamento novo, a leitura automática volta a valer e o status mostra a mudança.

#### Pasta `_revisar`

A cada `ler`, o regulamento de cada fundo em `REVISÃO HUMANA` é movido para `_regulamento\_revisar\`, para quem for
revisar achar todos num lugar só. Quando o fundo sai da revisão, o regulamento volta para a raiz de `_regulamento`.
Isso acontece quando o `regra.json` é marcado como revisado ou quando um regulamento novo passa a ser lido
automaticamente. O `_indice.csv` guarda o caminho com a subpasta, e o `buscar` não baixa de novo um regulamento só
porque ele está em `_revisar`. O nome da subpasta fica em `subpastas.revisar` no `config.json`.

## O que a leitura reconhece

A seção é procurada primeiro num **anexo** (ou adendo/apêndice) cujo título fala de verificação de lastro ou
amostragem, ou no anexo que a cláusula de verificação de lastro cita ("na forma do Anexo III"). O sumário é ignorado.
Sem anexo, são usadas as **cláusulas** com mais termos de regra de amostragem (fatores de risco, definições e
obrigações genéricas do prestador ficam de fora).

| Item da regra | Exemplos de texto reconhecido | No script |
|---|---|---|
| Fórmula (população finita) | `n = N·z²·p·(1−p) / [ME²·(N−1) + z²·p·(1−p)]`, `z = 1,96`, `p = 50%`, `ME = 5,8%`, "95% de confiança" | calcula n e arredonda para cima |
| Fórmula n = N/(1+N·E²) | "Eo = erro amostral tolerável entre 5% e 10%" | usa o erro menor (mais conservador) e marca pendência |
| Verificação integral | "de forma individualizada e integral", "100% dos direitos creditórios" | todos os itens |
| Quantidade fixa | "a amostra total compreende 120 itens", com "Amostra (I) de até 36 itens" dos inadimplidos/substituídos | Amostra (I) + Amostra (A) |
| Percentual, mínimo, máximo | "amostra de 10% dos direitos creditórios", "mínimo de 30 itens" | aplica os limites |
| Até N itens, verifica todos | "caso o número de itens seja superior a 100, a amostragem será aplicável" | população pequena = 100% |
| População base | "em aberto (a vencer) e recomprados no trimestre" | filtra a base por situação |
| 100% de categorias | "serão verificados 100% dos inadimplidos e os substituídos" | entram todos, fora da conta do n |
| Maiores por cedente/sacado | "para os 5 cedentes mais representativos… os 3 de maior valor" | obrigatórios, contam dentro do n |
| Maiores fora da base | "serão excluídos os 10 maiores direitos creditórios" | saem da população (aba *Excluídos*) |
| Seleção | "intervalo de retirada (K)… ponto de partida sorteado" / "aleatória" | sistemático ou aleatório, com semente |

O que não for reconhecido vira pendência. A leitura **não substitui** a conferência: cada README traz o trecho do
regulamento e a frase de onde saiu cada parâmetro, para conferir rápido.

### Calibragem (lista de fundos do 3T2026)

Os 196 fundos da lista têm regulamento no Fundos.NET (todos em PDF com texto). Resultado da leitura:

| Método | Fundos |
|---|---:|
| Fórmula (z = 1,96, p = 50%, ME = 5,8% e os 3 maiores dos 5 maiores cedentes: o modelo mais comum) | 72 |
| Fórmula com outros parâmetros (ME de 1,5% a 6,5%, p de 5%, 90% de confiança, "até 100 itens verifica todos") | 12 |
| Quantidade fixa (120 itens: Amostra I até 36 + Amostra A) | 32 |
| Verificação integral | 44 |
| n = N/(1+N·E²) | 1 |
| Não identificado | 35 |

Dos 35 não identificados, 17 não falam em verificação de lastro: na maioria são FIC-FIDC, que compram cotas de outros
FIDCs. Os demais citam amostragem sem trazer o tamanho da amostra (por exemplo, "conforme as diretrizes do Anexo", e o
anexo não existe no documento) ou usam uma regra fora dos modelos acima (por exemplo, grupos por tempo de aquisição).

Na lista `Lastro 2026` (500 fundos), 471 têm regulamento no Fundos.NET: 204 `OK`, 84 `CONFERIR` e 183 `REVISÃO HUMANA`.
A maior parte da revisão humana (113 fundos) é um modelo de regulamento que **não traz a regra**: diz que a verificação
será "individualizada, por amostragem ou com dispensa, conforme as políticas da Gestora, disponíveis no website da
Administradora". Nesses casos o README cita o artigo e indica que o documento deve ser pedido à gestora/administradora.
Em alguns, o sumário lista um anexo "Procedimentos para Verificação de Lastro por Amostragem" que não está no PDF
publicado (o README avisa).

## Base para o comando `amostra`

Uma linha por direito creditório, em `.xlsx` ou `.csv` (`;` ou `,`). As colunas são achadas pelo nome:

| Campo | Nomes aceitos (ignora maiúsculas e acentos) | Obrigatório |
|---|---|---|
| valor | `VALOR_PRESENTE`, `VALOR_NOMINAL`, `VALOR_AQUISICAO`, `VALOR` | sim |
| situação | `SITUACAO_RECEBIVEL`, `SITUACAO`, `STATUS`, `TIPO_MOVIMENTO` | não* |
| vencimento | `DATA_VENCIMENTO`, `VENCIMENTO` | não* |
| cedente / sacado | `NOME_CEDENTE`, `CEDENTE`, `NOME_SACADO`, `SACADO`, `DEVEDOR` | quando a regra usa os maiores por cedente/sacado |
| id | `SEU_NUMERO`, `NU_DOCUMENTO`, `DOCUMENTO`, `ID` | não |

\* A situação é lida por palavras: "recompra" → recomprado, "substitu" → substituído, "vencid/inadimpl/atras" →
vencido, "a vencer/aberto/em dia" → a vencer. Sem coluna de situação, o vencimento antes da `--data-base` vira vencido.
Sem nenhuma das duas, tudo é tratado como a vencer (com aviso). Outros nomes: `--col-valor`, `--col-situacao`,
`--col-cedente`, `--col-sacado`, `--col-vencimento`, `--col-id`.

A saída `amostra_<CNPJ>.xlsx` tem as abas **Amostra** (itens a verificar, com o motivo de cada um), **Resumo**
(N, n, K, ponto de partida, semente e parâmetros) e, se houver, **Excluídos (maiores)**. A semente sai na tela:
rodar de novo com `--semente <número>` gera a mesma amostra.

## Testes

```bash
python -m unittest discover -s tests -v
```

Usam textos e bases fictícios (sem internet). Cobrem a localização da seção (anexo, sumário, cláusulas, anexo citado
que não existe), a interpretação dos modelos de regra, o tamanho da amostra, o sorteio (100%, maiores por cedente,
Amostra I/A, exclusão dos maiores, semente), o script embutido no README rodando sozinho e a escolha do regulamento
vigente no Fundos.NET.

## Limitações

- A leitura é por padrões de texto. Uma regra escrita de um jeito novo pode não ser reconhecida (vai para revisão
  humana) ou ser lida parcialmente (fica em `CONFERIR`). Os parâmetros de cada fundo `OK` também merecem uma olhada no
  trecho citado antes do primeiro uso.
- PDF digitalizado (imagem, sem texto) não é lido: o README avisa.
- A regra é a do regulamento vigente no Fundos.NET. Fundos com mais de uma classe podem ter anexos diferentes por
  classe: hoje é lida a primeira seção de verificação de lastro encontrada.
- O script gera a amostra. Avaliar o resultado (por exemplo, a "Inconsistência Relevante" de alguns regulamentos) é
  manual: quando o regulamento define esse limite, o README mostra o trecho em *Observações*.
