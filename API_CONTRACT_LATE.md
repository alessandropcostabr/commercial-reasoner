# Contrato de API LATE ↔ Commercial Reasoner (engine)

**Data:** 2026-08-27
**Lado:** especificação escrita pelo LATE (consumidor). É o **gate bloqueante** da integração:
enquanto a engine não expuser este contrato, o módulo LATE não pode ser codado (plano-sobre-plano).
**Fonte de verdade:** a especificação completa vive no repositório privado do LATE; este documento é
o recorte do contrato que a engine precisa implementar.

Hoje a engine só fala **Telegram via Hermes**. Esta integração exige um **contrato HTTP estável**,
*request-response assíncrono* (o LATE chama; a engine responde por webhook). O LATE nunca bloqueia
thread esperando o LLM: ele pausa a conversa e retoma quando o callback chega.

---

## 1. Fluxo

```
LATE  ──POST /reason──►  engine        (LATE manda contexto + correlation_token; a run pausa)
LATE  ◄──POST webhook──  engine        (engine devolve resposta + metadados + echo do token)
```

- O LATE gera um `correlation_token` opaco por chamada e pausa a run aguardando o callback.
- A engine processa e chama o **webhook do LATE** com a resposta e o **echo do token**.
- O LATE casa o callback à run pelo token, aplica guardrails e entrega ao cliente.

---

## 2. Request — `POST /reason` (LATE → engine)

Corpo JSON:

| Campo | Tipo | Obrigatório | Nota |
|---|---|---|---|
| `correlation_token` | string (opaco) | sim | o LATE casa o callback por ele; a engine só ecoa |
| `message` | string | sim | mensagem atual do cliente |
| `history` | array de `{ role: "user"\|"bot", text }` | sim | **com proveniência**; ver §6 (a fala do bot NÃO é fonte de fato) |
| `grounded_facts` | objeto tipado (ver abaixo) | sim | fatos verdadeiros da conta+setor injetados por chamada |
| `rapport` | objeto/número/`null` | sim | estado de rapport acumulado |
| `stage` | string livre | sim | estágio de venda atual; a engine ECOA no response, não valida contra FSM (o LATE é dono da FSM) |

> **Medido (`contract.py::ReasonRequest`):** a engine aceita `history`/`grounded_facts`/`rapport`
> AUSENTES (defaults `[]` / vazio / `null`) - a obrigatoriedade acima é do lado do LATE, que sempre
> envia. Só `correlation_token`, `message` e `stage` não têm default na engine.

> **Forma EXATA de `grounded_facts` (`contract.py::GroundedFacts`, Codex #9):** a engine só lê duas
> chaves e **ignora silenciosamente qualquer outra** (Pydantic descarta extras). Um objeto genérico
> tipo `{"preco": 1200}` resulta em fatos VAZIOS e a engine raciocina sem grounding. Enviar exatamente:
> ```json
> {
>   "prices": [{ "modality": "string", "value": 0.0, "description": "string (opcional)" }],
>   "other_numbers": [0.0]
> }
> ```
> `prices[].modality` e `prices[].value` são obrigatórios (payload malformado = 422). "Vagas, datas,
> condições" do texto antigo NÃO têm campo próprio hoje: modelar como `prices`/`other_numbers` ou
> estender a engine antes de usar.

**Regra de ouro (já implementada na engine):** a engine responde usando **só** `grounded_facts` +
o que o cliente disse. Nunca inventa número/preço/data. `history` é contexto conversacional, **não**
fonte de fato.

---

## 3. Response — webhook (engine → LATE)

Corpo JSON. **Validação estrita no LATE ANTES de qualquer efeito** — campo faltando ou fora de
domínio = envelope rejeitado por inteiro + escalonamento humano (não é "categoria outro").

| Campo | Tipo | Obrigatório | Domínio / nota |
|---|---|---|---|
| `event_id` | string | sim | **globalmente único e PREFIXADO** `commercial-reasoner:<uuid>` (ver §4) |
| `timestamp` | string ISO-8601 | sim | assinado no HMAC; janela de replay do LATE = 5 min |
| `correlation_token` | string | sim | **echo** exato do token do request (§2) |
| `response_text` | string | sim | texto a enviar ao cliente |
| `technique` | string (enum) | sim | `VOSS`\|`CHALLENGER`\|`CIALDINI`\|`SPIN` |
| `rapport` | objeto/número/`null` | sim (campo presente) | rapport atualizado; `null` é válido (sem rapport) |
| `stage` | string livre | sim | **echo** de `req.stage`; a engine não valida contra FSM - o LATE valida por IGUALDADE com o stage enviado |
| `bant` | objeto/`null` | sim (campo presente, valor nullable) | present-with-`null` quando ausente; a engine NÃO enforça a forma `{budget,authority,need,timeline}` 0-10 (dict livre) - o LATE valida a forma se precisar |
| `commitment_category` | enum/`null` | sim (campo presente) | `null`\|`preco`\|`prazo`\|`forma_pagamento`\|`desconto`\|`frete`\|`outro` (§5) |
| `outcome` | enum | sim | `continue`\|`close`\|`escalate` |

Grafia, obrigatoriedade, tipo e domínio de **cada** campo têm de ser fixados contra o envelope real
(a validação estrita do LATE rejeita o que divergir).

> **Medido (`contract.py::ResponseEnvelope`):** a engine implementa o schema de forma mais PERMISSIVA
> que o ideal - `stage` string livre (echo), `rapport`/`bant`/`commitment_category` nullable e sempre
> presentes, forma de `bant` não enforçada. A validação estrita é responsabilidade do LATE (Fase 5):
> valida `stage` por igualdade com o request, tolera os campos present-with-`null`, e checa a forma de
> `bant` do seu lado.

---

## 4. Idempotência e assinatura (o que mais quebra)

- **`event_id` prefixado global.** O LATE deduplica callbacks num ledger de chave **GLOBAL**
  (compartilhado com webhooks de finanças/telefonia). Um id único só na origem da engine **colide** e
  o callback comercial volta como duplicata sem processar. Por isso o prefixo `commercial-reasoner:`.
- **`timestamp` assinado obrigatório.** O middleware do LATE rejeita (400) callback sem timestamp
  válido; janela de 5 min.
- **HMAC — regra de canonicalização (crítica).** A engine assina os **bytes crus (UTF-8) do corpo
  JSON** enviado; o LATE verifica sobre **o corpo cru recebido** (não sobre um `JSON.stringify`
  re-serializado). Sem essa regra explícita, diferenças de whitespace/ordem de chaves fazem TODO
  callback válido ser rejeitado com 401. Header: `x-webhook-signature: <base64(hmac-sha256(rawBody,
  secret))>`. Secret compartilhado via variável de ambiente (nunca hardcodado).
  *(Nota p/ o LATE: o verificador de assinatura deve computar o HMAC sobre o rawBody recebido, nunca
  sobre um JSON re-serializado.)*
- **Idempotência do lado da engine.** O LATE pode **re-enviar o mesmo request** (retry pós-crash do
  worker). A engine deve tratar requests com o **mesmo `correlation_token` de forma idempotente** —
  não refazer trabalho nem gerar callbacks divergentes. (Alternativa aceita pelo LATE: o LATE trata o
  request como at-least-once do seu lado, mas idempotência remota por token é mais barata e segura.)

---

## 5. Gate financeiro — quem faz o quê (evitar duplicação)

**Decisão do LATE:** o gate de aprovação humana para compromisso financeiro é **enforçado no LATE**,
não na engine. A engine **classifica**; o LATE **trava**.

- A engine devolve `commitment_category` estruturada (não infere do texto).
- O LATE, se a categoria ∈ conjunto-que-exige-aprovação (configurável por conta), **segura a resposta
  num estado não-despachável** até um humano aprovar — antes de enviar ao cliente.
- **Não construir um segundo gate humano dentro da engine** (o roadmap da engine previa um) — seria
  duplicação e dois donos do mesmo compromisso. A responsabilidade da engine é só **classificar com
  precisão**; classificar errado (`null`/`outro` quando havia compromisso) é o modo de falha a evitar
  (o LATE tem uma rede numérica de fail-safe, mas ela não pega "boleto"/"frete grátis"/"prazo 30 dias").

---

## 6. Grounding e memória — alinhamentos com o design LATE

- **Config por conta + SETOR, não só conta.** O `grounded_facts` do request vem escopado por
  `account_id` **e** `sector_id` da conversa. Um loader por conta apenas (`load_config_for_account`)
  vaza catálogo/preço de outro setor numa conta multi-setor. Escopar por conta+setor.
- **A fala do bot nunca é fonte de fato — nem por `prior_memory`, nem por `history`.** A engine já
  barra replay bruto via `prior_memory`; estender: no `history` do request, a `role: "bot"` é
  **contexto conversacional**, nunca verdade factual. Só `grounded_facts` (e o que o cliente disse)
  são autoritativos. Isso fecha o bug da Miah por completo (cotação alucinada não volta como fato nem
  pela história).

---

## 7. Gate da Fase 0 (o que provar antes de codar o conector LATE)

> **Status:** Gate medido em 2026-08-28 contra este repo @ master 2ef8106; 5/6 itens provados, o de autenticação HMAC pende do ajuste do verificador no consumidor.

- [x] `POST /reason` e o webhook existem e trafegam o schema das §§2-3 (envelope real capturado).
- [x] Schema COMPLETO da resposta medido: grafia/obrigatoriedade/tipo/domínio de cada campo. As §§2-3 foram ALINHADAS à implementação `contract.py` (Codex #9): `stage` echo/livre, `rapport`/`bant`/`commitment_category` nullable e presentes, engine permissiva + LATE valida estrito.
- [x] `commitment_category` estruturada é emitida (não inferida do texto), confirmado com modelo real (Qwen).
- [x] `event_id` prefixado global + `timestamp` assinado + echo do `correlation_token` no callback.
- [ ] Um callback assinado real **autentica** pelo middleware do LATE. **PENDENTE do fix do consumidor**: a REGRA de canonicalização foi provada (o verificador deve computar HMAC-SHA256 sobre o rawBody e comparar em base64; a assinatura real da engine bate), mas a autenticação ponta a ponta só passa após o consumidor ajustar seu verificador. A engine já assina corretamente: `base64(HMAC-SHA256(rawBody))`.
- [x] Idempotência remota por `correlation_token`: a engine deriva `event_id` determinístico (uuid5 do token), o mesmo token produz o mesmo `event_id` (dedup de callback no ledger do consumidor). NOTA: é idempotência de CALLBACK, não de trabalho (a engine re-executa o reasoning no retry); o consumidor trata seu lado como at-least-once.

Enquanto estes itens não forem provados contra a engine REAL, o módulo LATE não abre — é o gate.

---

*Este documento é a fonte de verdade do CONTRATO entre os repos. O roadmap interno da engine
(`ROADMAP_NEXT_STEPS.md`) é ortogonal: loader de config, BANT e grounding prompt são melhorias da
engine; este contrato é o que o LATE precisa que a engine EXPONHA.*
