# Handoff: como e por que o leitor lê e classifica os regulamentos

Este documento é para quem vai manter ou mudar o Leitor de regulamentos. O `README.md` explica como **usar** a
ferramenta. Aqui está **como** a leitura e a classificação funcionam por dentro, **por que** cada regra é assim e o
que já foi decidido. Antes de mexer em `secao.py` ou `regra.py`, leia as seções 4, 5 e 9.

## 1. O problema

A Resolução CVM 175 permite verificar o lastro dos direitos creditórios (DCs) por amostragem, mas cada FIDC escreve
no **regulamento** como a amostra é montada: uma fórmula estatística, uma quantidade fixa, 100% da carteira, os
maiores de cada cedente, os inadimplidos e substituídos a 100%, e assim por diante. Não há um padrão: o mesmo
conteúdo aparece num anexo, num capítulo ou espalhado em cláusulas, com redações diferentes.

O leitor faz três coisas: acha o trecho do regulamento que define a amostra, transforma esse trecho em parâmetros
(a **regra**) e classifica o fundo (**status**) para separar o que pode ser usado direto do que precisa de uma
pessoa.

**Princípio que orienta todo o código:** errar para o lado da revisão. Uma regra lida errada gera uma amostra errada
sem ninguém perceber; uma regra não reconhecida só gera trabalho manual. Por isso:

- o que não é reconhecido com segurança vira **pendência**, e o fundo vai para `CONFERIR` ou `REVISÃO HUMANA`;
- todo parâmetro lido guarda a frase do regulamento de onde saiu (`evidencias`), para conferir sem abrir o PDF;
- nenhum número é inventado: quando o leitor assume um valor (z = 1,96, p = 50%), ele diz isso na pendência.

## 2. O fluxo

```
lista de fundos ─► fundosnet.py ─► _regulamento\*.pdf ─► leitura.py ─► secao.py ─► regra.py ─► status
 (CNPJ)            (busca/baixa)                         (texto)       (trecho)    (parâmetros)    │
                                                                                                    ▼
                    _script de amostra\<fundo>\README.md + regra.json ◄── readme_fundo.py / tabela.py
                    (o script embutido é o motor_amostra.py com a REGRA do fundo)
```

| Módulo | Papel |
|---|---|
| `amostra_regulamento.py` | linha de comando (`buscar`, `ler`, `tudo`, `tabela`, `amostra`), lista de fundos, índice, pastas por status |
| `fundosnet.py` | API do Fundos.NET: lista documentos por CNPJ, escolhe o regulamento vigente, baixa |
| `leitura.py` | extrai o texto (PDF, DOCX, ZIP) e normaliza em parágrafos |
| `secao.py` | localiza o trecho da regra e reconhece FIC FIDC |
| `regra.py` | interpreta o trecho e monta a `Regra` (parâmetros, pendências, evidências) |
| `readme_fundo.py` | status, README de cada fundo e o script embutido |
| `motor_amostra.py` | gera a amostra a partir da base analítica e da `Regra` |
| `tabela.py` | `_regras.xlsx` com a regra de todos os fundos |

## 3. Busca e download (`fundosnet.py`)

- **Fonte:** a mesma API JSON da tela pública do Fundos.NET (`pesquisarGerenciadorDocumentosDados`), filtrada pelo
  CNPJ e pela categoria **5 = Regulamento**. O download é `downloadDocumento?id=`. Só usa a biblioteca padrão.
- **Qual regulamento:** o **ativo** ("Ativo com visualização") entregue por último. Os cancelados e inativos são
  ignorados. *Por quê:* um fundo tem várias versões publicadas, e só a vigente vale.
- **Sem regulamento na categoria 5:** usa o último "Instrumento Particular de Alteração do Regulamento" (categoria
  11), que costuma trazer o regulamento consolidado.
- **Só baixa o que mudou:** o `_indice.csv` guarda o documento de cada fundo. Se o id é o mesmo e o arquivo existe,
  pula. Uma versão nova vai para a raiz e a anterior para `_antigos\`.
- **O índice guarda o caminho com a subpasta** (`_revisar/...`, `_FIC FIDC/...`), então o `buscar` não baixa de novo
  um regulamento que foi movido. Se alguém mover o PDF à mão, o `ler` procura nas subpastas.

## 4. Do PDF ao trecho da regra (`leitura.py` e `secao.py`)

### 4.1 Normalização do texto

O PDF quebra o texto em linhas visuais. `normalizar()` remonta os parágrafos:

- **junta** as linhas até o fim da frase (`.`, `;`, `:`) ou até começar um item (`(a)`, `i)`, `9.2.1`, `Artigo 15`,
  `Cláusula`, `§`, `ANEXO III`, `CAPÍTULO`);
- **remove** os números de página soltos e os cabeçalhos/rodapés repetidos (linha de 16 a 199 caracteres que aparece 8
  vezes ou mais, desde que não fale de lastro ou amostragem);
- **cola** de volta os itens que ficaram sozinhos numa linha (`(a)` numa linha e o texto na seguinte).

*Por quê:* a localização trabalha por parágrafo. Sem isso, uma cláusula vira dez pedaços que pontuam pouco cada um.

### 4.2 Onde está a regra: quatro tentativas, nesta ordem

A ordem vai do sinal mais forte para o mais fraco. A primeira que funciona decide.

1. **Anexo** (`origem: anexo`). Um anexo, adendo ou apêndice cujo título fala de lastro ou amostragem, ou o anexo
   que a cláusula de lastro cita ("na forma do **Anexo III**"). Os anexos candidatos são pontuados (seção 4.3) e o
   tema no título vale +6. O melhor precisa somar 10 ou mais. O trecho vai até "ESTE ANEXO É PARTE INTEGRANTE DO
   REGULAMENTO" ou até 15 mil caracteres.
   - Linhas de **sumário** são ignoradas: pontilhado, sublinhado ou número de página no fim. *Por quê:* o título do
     anexo aparece primeiro no sumário, e o leitor pegava o sumário inteiro.
   - Citação no meio de uma frase ("ANEXO III deste Regulamento, ...") não é título.
   - Anexos de cobrança e modelos de apêndice são descartados, a menos que o título fale de lastro.
2. **Capítulo** (`origem: capitulo`). Um título numa linha só, como "IX – DA VERIFICAÇÃO DE LASTRO", "CAPÍTULO V –
   VERIFICAÇÃO DO LASTRO", ou "10." numa linha e "DA VERIFICAÇÃO DE LASTRO" na seguinte. O capítulo é lido **inteiro**,
   até o próximo título de capítulo (inclusive "11." / "DAS TAXAS") ou até 12 mil caracteres.
   *Por quê:* antes o leitor escolhia cláusulas soltas e perdia a do custodiante (100% dos substituídos e vencidos),
   como no FIDC NDMP.
3. **Cláusulas** (`origem: clausulas`). Cada parágrafo que fala de lastro, documentos comprobatórios ou amostragem é
   pontuado. Entram os que somam 5 ou mais (até 6, mais os subitens `(a)`, `(b)` logo abaixo). As 3 seguintes vão
   para as `mencoes`. Parágrafos logo abaixo de um subtítulo curto ("Verificação do Lastro dos Direitos
   Creditórios") ganham +3.
4. **Última tentativa** (também `clausulas`). Se nada somou 5, aceita os parágrafos que falam de **verificação do
   lastro** junto com amostragem, verificação individualizada ou integral, substituição, inadimplência ou vencidos.
   *Por quê:* em alguns PDFs o título fica grudado no texto ("SEÇÃO II VERIFICAÇÃO DE LASTRO Artigo 66º … por
   amostragem") e a cláusula sozinha pontua pouco. Sem isso, o fundo saía como "não traz regra", o que era falso.

Se nada é encontrado, `origem: nenhuma`, e o fundo vai para revisão com a pendência "o regulamento não traz regra de
verificação de lastro".

### 4.3 A pontuação

`pontos()` soma o peso de cada termo presente no trecho (cada termo conta uma vez):

| Peso | Termos |
|---:|---|
| 4 | tamanho da amostra · nível de confiança · margem de erro / erro médio, amostral, tolerável, máximo · verificação integral ("de forma individualizada e integral", "integralmente", "100% dos direitos creditórios") |
| 3 | intervalo de retirada · ponto de partida · fórmula · `z =` |
| 2 | `n =` · população · amostra · aleatório / sorteio · estratificação · itens · modelo estatístico · dispensa · website / políticas da gestora |
| 1 | maiores · inadimplidos · substituídos · recomprados · lastro · documentos comprobatórios · individualizada |

**Penalidade de −6** para o que fala do tema, mas não é a regra:
- **fator de risco** ("Risco da Verificação do Lastro por Amostragem…", "poderá conter", "poderá obstar");
- **definição** ("significa");
- **obrigação genérica do prestador** ("verificação da existência, integridade e titularidade…, **podendo contratar
  terceiros**", "despesas com verificação", "guarda da documentação").

*Por quê:* essas frases estão em quase todo regulamento, têm várias palavras do tema e enganavam o leitor.
"Integralidade e titularidade" **não** conta como verificação integral, porque é a fórmula padrão das obrigações do
gestor.

### 4.4 Avisos que a localização gera

Os avisos não mudam a regra, mas entram nas pendências do README:

- o regulamento cita o Anexo X para a verificação de lastro, mas o Anexo X **não está no documento** ou **trata de
  outro assunto**;
- o **sumário** lista "Procedimentos para Verificação de Lastro por Amostragem", mas o anexo não está no PDF publicado
  (no sumário aparece "Erro! Indicador não definido.");
- o regulamento define "Parâmetros de Amostragem", mas o anexo correspondente não foi encontrado;
- o PDF quase não tem texto (digitalizado).

## 5. Do trecho à regra (`regra.py`)

`interpretar()` lê o trecho (mais as `mencoes`) e preenche a `Regra`. Antes de ler, troca os símbolos matemáticos
(`𝑁`, `𝑧²`, `𝑀𝐸`) por letras comuns (NFKC) e padroniza aspas e traços.

### 5.1 Parâmetros

| Campo | O que reconhece | Cuidados |
|---|---|---|
| `z` | `z = 1,96`, `z = Critical score = 1,96`, `Z (…) = 1,645` | |
| `confianca` | "95% de nível de confiança", "intervalo de confiança de 95%" | sem `z` no texto, o `z` vem da tabela (90% → 1,645; 95% → 1,96; 99% → 2,576…) |
| `p` | `p = 50%`, "proporção a ser estimada = 50%" | |
| `erro` | `ME = 5,8%`, "erro médio", "margem de erro", "erro amostral (tolerável)" | as siglas `ME`, `E`, `E0`, `Eo` só valem **em maiúscula** e seguidas de `=`, `:` ou `(`. *Por quê:* o "e" de "Cotas Seniores **e** 75%" virava erro de 75% |
| `erro_faixa` | "erro tolerável entre 5% e 10%" | usa o menor (mais conservador) e marca pendência |
| `quantidade` | "amostra de 120 itens", "a amostra total (N) compreende 120 itens" | "amostra de **até** X" não é quantidade fixa |
| `subamostra_i_max` | "Amostra (I)… até 36 itens" + "Amostra (A)… a vencer" | modelo 120 = I + A |
| `percentual`, `minimo`, `maximo` | "amostra de 10% dos direitos creditórios", "mínimo de 30 itens", "máximo de / limitado a" | |
| `limite_integral` | "superior a 100 itens, a amostragem será aplicável", "inferior a 50… totalidade" | população até o limite: verifica tudo |

### 5.2 Método

Decidido nesta ordem:

1. **`formula_yamane`** (n = N / (1 + N·E²)): a fórmula aparece no texto e há erro.
2. **`formula_cochran`** (população finita: n = N·z²·p·(1−p) / [E²·(N−1) + z²·p·(1−p)]): a fórmula com `z²` e
   `(N − 1)` aparece, ou há um erro definido. Faltando `z` ou `p`, usa 1,96 e 50% **com pendência**.
3. Faixa de erro sem `z`: `formula_yamane`, com pendência de que a fórmula não foi reconhecida.
4. **`quantidade_fixa`**, depois **`percentual`**.
5. **`integral`**: o texto diz que a verificação é integral. Se diz também "por amostragem", vira pendência ("confira
   qual vale"). Se o 100% é só "**poderá** ser de 100%" (faculdade da gestora), o método fica `nao_identificado`.
6. **`nao_identificado`**: nenhum dos anteriores. A pendência diz o motivo:
   - prevê amostragem, mas não define o tamanho;
   - remete às políticas da gestora / website da administradora (marca `regra_externa`);
   - fala de lastro sem dizer se é integral nem o tamanho.

### 5.3 População, 100%, maiores e seleção

- **População base (`populacao`):** lida da frase "a população base… compreenderá…", "universo de amostragem…" ou
  "N = …". Reconhece a vencer / em aberto / carteira, vencidos, recomprados, substituídos e adquiridos no período.
  Sem frase, usa a vencer, com pendência (exceto no método integral).
- **Verificados a 100% (`integral_categorias`):** "100% / totalidade / cem por cento / individualmente" seguido, na
  mesma frase, de inadimplidos ou vencidos, substituídos ou recomprados.
  - A janela é de **200** caracteres, e de **400** só para "**totalidade do lastro**". Esse é o texto padrão "Considerando
    a totalidade do lastro… o Custodiante deve verificar… os que ingressaram a título de substituição, assim como
    os vencidos e não pagos", em que a categoria vem longe.
  - "**N = totalidade de direitos creditórios adquiridos**" **não** conta. *Por quê:* essa definição vem logo antes da
    população base, que cita os recomprados, e o leitor marcava os recomprados como 100% em cerca de 70 fundos.
  - Os recomprados ficam fora quando a frase fala em "selecionados" (é seleção, não 100%).
- **Maiores (`maiores_por_grupo`):** "para os **5** cedentes (sacados, devedores, endossantes…) mais representativos…
  os **3** de maior valor". A frase decide as bases: "em aberto" e/ou "recomprados". Também reconhece os N maiores
  da carteira como obrigatórios (`maiores_incluir`) e os N (ou X%) maiores **excluídos** da base (`maiores_excluir`).
- **Seleção:** sistemática (intervalo K, ponto de partida sorteado), que é o padrão, ou aleatória simples.
- **Só informativo** (`observacoes`): "Inconsistência Relevante", dispensa para DCs registrados, dispensa por valor
  médio baixo. Estratificação vira pendência.

## 6. A classificação (status) e as pastas

O status de cada fundo sai em `amostra_regulamento.processar_fundo` e `readme_fundo.status`. Vale o primeiro que se
aplica:

| Ordem | Status | Quando | Pasta do regulamento |
|---:|---|---|---|
| 1 | `FIC FIDC` | o **regulamento** é de fundo de investimento em cotas de FIDC (seção 6.1) | `_regulamento\_FIC FIDC\` |
| 2 | `REVISADO MANUALMENTE` | o `regra.json` do fundo foi marcado `"revisado_manualmente": true` e o regulamento é o mesmo documento | raiz |
| 3 | `PROCEDIMENTOS PRÉ-ACORDADOS` | método não identificado e o regulamento remete às políticas da gestora / website da administradora | `_regulamento\_Procedimentos pré acordados\` |
| 4 | `REVISÃO HUMANA` | método não identificado (qualquer outro motivo) | `_regulamento\_revisar\` |
| 5 | `CONFERIR` | regra identificada, mas com pendência ou aviso | raiz |
| 6 | `OK` | regra identificada, sem pendências | raiz |
| — | `SEM REGULAMENTO` | o Fundos.NET não tem regulamento ativo para o CNPJ | (sem arquivo) |

A cada `ler`, o PDF vai para a pasta do status. Se o status muda, o PDF muda de pasta.

### 6.1 Como o FIC FIDC é reconhecido

**Só pela leitura do regulamento, nunca pelo nome na lista de fundos.** *Por quê:* decisão sua, para a ferramenta
continuar certa se a lista mudar. Na prática isso achou FICs que o nome não indicava (BLESS ALLOCATION, INVICTO 22,
SIG VI e SIG VII) e tirou um "FIC" da lista cujo regulamento é de FIDC comum (BYX).

- **Título:** o texto logo após "REGULAMENTO DO/DA", até "CNPJ" ou "DEFINIÇÕES", diz "FUNDO DE INVESTIMENTO (ou FI) EM
  COTAS DE FUNDO(S) DE INVESTIMENTO EM DIREITOS CREDITÓRIOS", "EM COTAS DE FIDC" ou "FIC FIDC". O padrão tolera
  palavras grudadas pelo PDF ("FUNDO **DEINVESTIMENTO**").
- **Ou a política:** "a Classe investe preponderantemente / majoritariamente / exclusivamente / no mínimo X% em cotas
  de (outros) FIDCs".
- Procurar "FIC FIDC" no texto inteiro **não** serve: as assinaturas eletrônicas no topo do PDF citam cotistas que são
  FIC (caso AMALFI e VIA PRIME).

### 6.2 Decisões tomadas (com o porquê)

| Decisão | Motivo |
|---|---|
| FIC FIDC vai para `_FIC FIDC` **mesmo quando tem regra identificada** (14 casos na lista 3T2026) | pedido seu: "todos lá". O README e o `regra.json` desses fundos continuam com a regra e o script |
| FIC tem prioridade sobre procedimentos pré-acordados | um FIC que remete às políticas da gestora é, antes de tudo, um FIC |
| Regulamento que diz só "por amostragem", sem tamanho, **fica em revisão humana** | decisão sua. O README mostra o que o regulamento define (quem verifica, prazo, 100% de substituídos e vencidos) e a pendência diz que falta o tamanho |
| Remissão às políticas da gestora vira status próprio (procedimentos pré-acordados) | a regra existe, mas fora do regulamento. A ação é pedir o documento à gestora, não reler o regulamento |
| Na dúvida entre ler e não ler um parâmetro, não lê e marca pendência | princípio da seção 1 |

### 6.3 Revisão manual

Para registrar uma regra decidida por uma pessoa: edite o `regra.json` do fundo, ajuste o bloco `regra` e marque
`"revisado_manualmente": true`. O `ler` passa a usar essa regra e não a sobrescreve enquanto o `doc_id` for o mesmo.
Se o fundo publicar um regulamento novo, a leitura automática volta a valer.

## 7. Da regra à amostra (`motor_amostra.py`)

O mesmo código roda pelo comando `amostra` e no script embutido em cada README. Ordem:

1. **Classifica** cada linha da base: pela coluna de situação (recompra → recomprados; substitu → substituídos;
   vencid / inadimpl / atras → vencidos; a vencer / aberto / em dia → a vencer) ou, sem ela, pelo vencimento contra
   a `--data-base`.
2. **100%:** as categorias de `integral_categorias` entram todas e **não contam no n**. No modelo Amostra (I) + (A),
   até X delas também formam a Amostra (I).
3. **População (N):** as categorias de `populacao`, sem os itens a 100% e sem os maiores excluídos.
4. **n:** pela fórmula, quantidade ou percentual, com limite integral, mínimo e máximo; arredonda para cima.
5. **Maiores obrigatórios:** contam **dentro** do n (o regulamento diz "adicionalmente, os demais itens para
   completar a amostra").
6. **Sorteio do restante:** sistemático (K = N/n, ponto de partida sorteado, na ordem do arquivo) ou aleatório, com
   semente registrada para reproduzir.

## 8. Números de referência

**Lista 3T2026** (500 fundos, `Lastro_2026_1794335185.xlsx`): 194 OK · 80 CONFERIR · 46 FIC FIDC · 103 procedimentos
pré-acordados · 48 revisão humana · 29 sem regulamento.

**Lista 2T2026 Planner** (222 fundos, `Lastro_2026_1794412100.xlsx`): 146 OK · 27 CONFERIR · 3 FIC FIDC · 1
procedimentos pré-acordados · 38 revisão humana · 7 sem regulamento.

**O que aparece nos 684 regulamentos baixados:** fórmula de população finita 378 (o modelo z = 1,96, p = 50%,
E = 5,8% e "3 maiores dos 5 maiores cedentes" é o mais comum) · integral 67 · quantidade fixa 13 (23 com Amostra I/A) ·
n = N/(1+N·E²) 3 · não identificado 223 · 100% de inadimplidos e de substituídos cerca de 180 cada · maiores por
cedente 323.

Ainda **sem caso real** (o código reconhece, testado só com texto fictício): exclusão dos maiores, maiores da carteira
como obrigatórios, percentual da carteira, mínimo e máximo, recomprados a 100%.

## 9. Como mudar a leitura com segurança

Uma mudança que conserta um fundo pode estragar outros: cada padrão novo roda em todos os regulamentos. Já aconteceu
duas vezes (o "e" lido como erro de 75%, e os recomprados marcados como 100%). O procedimento:

1. **Reproduza** o caso: rode a leitura no regulamento (veja o README e o `regra.json` do fundo) e ache no texto
   normalizado a frase que o leitor perdeu ou leu errado.
2. **Mude o padrão** no lugar certo: localização em `secao.py`, parâmetro em `regra.py`, status em
   `readme_fundo.status`.
3. **Escreva um teste** em `tests/test_amostra.py` com a frase real, anonimizada se for o caso. Inclua um teste do que
   **não** deve casar.
4. **Rode os testes:** `python -m unittest discover -s tests`.
5. **Compare com a versão anterior em todos os regulamentos** (`scripts/comparar_versoes.py`, instruções no topo do
   arquivo). Ele lista cada fundo cuja regra ou status mudou. Confira cada diferença no texto: as esperadas confirmam
   a mudança; as inesperadas são regressão.
6. Rode `python amostra_regulamento.py ler --fundos <lista>` para regerar os READMEs, faça o commit e, se o mod
   `leitor-regulamentos` estiver em uso, atualize a cópia do código dentro dele (pasta `ferramenta/`).

## 10. Limitações conhecidas

- **Leitura por padrões de texto:** uma redação nova pode não ser reconhecida (cai em revisão) ou ser lida em parte
  (cai em `CONFERIR`). Os fundos `OK` merecem uma olhada no trecho citado antes do primeiro uso.
- **PDF digitalizado** (sem texto) não é lido.
- **Fundos com várias classes:** é lida a primeira seção de verificação de lastro encontrada.
- **Amostra dividida em grupos** fora do modelo I/A (por exemplo, grupos por tempo de aquisição) vira pendência.
- **"Inconsistência Relevante":** o script gera a amostra; julgar o resultado é manual.
- **Ordem da base:** o sorteio sistemático percorre a base na ordem do arquivo, então a mesma semente com a base em
  outra ordem dá outra amostra.
