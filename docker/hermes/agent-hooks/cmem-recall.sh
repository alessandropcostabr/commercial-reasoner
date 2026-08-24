#!/usr/bin/env bash
# Hook pre_llm_call -> RECALL. Le a mensagem do usuario do stdin (JSON do
# Hermes), busca contexto no cmem (POST /v1/context) e devolve no stdout
# {"context": "..."} para o Hermes injetar no turno.
#
# Fail-open: qualquer erro (cmem fora, sem key, timeout) -> stdout "{}" e
# nunca aborta o loop do agente.
set -uo pipefail

W="${CMEM_URL:-http://cmem:37877}"
PROJ="${CMEM_PROJECT:-agent}"
KEY="${CMEM_API_KEY:-}"

payload="$(cat)"
[ -z "$KEY" ] && { echo '{}'; exit 0; }

# A mensagem do usuario chega em extra.user_message (tool_name/tool_input sao
# null em pre_llm_call).
query="$(printf '%s' "$payload" | jq -r '.extra.user_message // empty' 2>/dev/null)"
[ -z "$query" ] && { echo '{}'; exit 0; }

body="$(jq -nc --arg p "$PROJ" --arg q "$query" '{projectId:$p, query:$q, limit:10}')"
resp="$(curl -sS --max-time 3 -X POST "$W/v1/context" \
  -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d "$body" 2>/dev/null)" || { echo '{}'; exit 0; }

ctx="$(printf '%s' "$resp" | jq -r '.context // empty' 2>/dev/null)"

# Capture fire-and-forget da mensagem do usuario DEPOIS do recall (para a query
# atual nao casar consigo mesma). Assim cada turno de conversa vira memoria e o
# proximo turno recupera o anterior, mesmo sem uso de ferramenta.
sid="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)"
ssid=""
[ -n "$sid" ] && [ -f "/tmp/cmem-sess-$sid" ] && ssid="$(cat "/tmp/cmem-sess-$sid" 2>/dev/null)"
if [ -n "$ssid" ]; then
  cap="$(jq -nc --arg p "$PROJ" --arg c "usuario: $query" --arg s "$ssid" '{projectId:$p,content:$c,kind:"user_message",serverSessionId:$s,metadata:{source:"hook"}}')"
else
  cap="$(jq -nc --arg p "$PROJ" --arg c "usuario: $query" '{projectId:$p,content:$c,kind:"user_message",metadata:{source:"hook"}}')"
fi
curl -s --max-time 3 -X POST "$W/v1/memories" -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d "$cap" >/dev/null 2>&1 &

if [ -n "$ctx" ]; then
  jq -nc --arg c "$ctx" '{context:$c}'
else
  echo '{}'
fi
