#!/usr/bin/env bash
# Hook post_tool_call -> CAPTURE. Persiste a chamada de ferramenta como uma
# observacao no cmem (POST /v1/memories). Fire-and-forget: nunca bloqueia.
#
# Contrato /v1/memories: obrigatorios projectId + content; opcionais
# serverSessionId, kind, metadata. teamId vem da api-key (nao do body).
set -uo pipefail

W="${CMEM_URL:-http://cmem:37877}"
PROJ="${CMEM_PROJECT:-agent}"
KEY="${CMEM_API_KEY:-}"

payload="$(cat)"
[ -z "$KEY" ] && { echo '{}'; exit 0; }

tn="$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null)"
[ -z "$tn" ] && { echo '{}'; exit 0; }
ti="$(printf '%s' "$payload" | jq -c '.tool_input // {}' 2>/dev/null)"
tr="$(printf '%s' "$payload" | jq -r '.extra.result // .extra.tool_response // empty' 2>/dev/null)"
sid="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)"

# Recupera o serverSessionId mapeado em on_session_start (se houver).
ssid=""
if [ -n "$sid" ] && [ -f "/tmp/cmem-sess-$sid" ]; then
  ssid="$(cat "/tmp/cmem-sess-$sid" 2>/dev/null)"
fi

content="[tool:$tn] input=$ti"
[ -n "$tr" ] && content="$content result=$tr"

if [ -n "$ssid" ]; then
  body="$(jq -nc --arg p "$PROJ" --arg c "$content" --arg s "$ssid" \
    '{projectId:$p, content:$c, kind:"tool", serverSessionId:$s, metadata:{source:"hook"}}')"
else
  body="$(jq -nc --arg p "$PROJ" --arg c "$content" \
    '{projectId:$p, content:$c, kind:"tool", metadata:{source:"hook"}}')"
fi

curl -sS --max-time 3 -X POST "$W/v1/memories" \
  -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d "$body" >/dev/null 2>&1 &

echo '{}'
