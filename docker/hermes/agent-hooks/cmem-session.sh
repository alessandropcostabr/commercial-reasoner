#!/usr/bin/env bash
# Hook de ciclo de sessao. Trata varios eventos do Hermes:
#   on_session_start -> POST /v1/sessions/start (cria sessao, guarda o id)
#   subagent_stop / on_session_end -> POST /v1/sessions/<id>/end (finaliza)
#
# A sessao do cmem e idempotente em (projectId, externalSessionId), onde
# externalSessionId = session_id do Hermes. O id interno retornado e mapeado
# em /tmp/cmem-sess-<session_id> para o cmem-capture usar como serverSessionId
# e para o end localizar a sessao.
#
# Fail-open: nunca bloqueia o agente.
set -uo pipefail

W="${CMEM_URL:-http://cmem:37877}"
PROJ="${CMEM_PROJECT:-agent}"
KEY="${CMEM_API_KEY:-}"

payload="$(cat)"
[ -z "$KEY" ] && { echo '{}'; exit 0; }

event="$(printf '%s' "$payload" | jq -r '.hook_event_name // empty' 2>/dev/null)"
sid="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$sid" ] && { echo '{}'; exit 0; }

case "$event" in
  on_session_start)
    body="$(jq -nc --arg p "$PROJ" --arg e "$sid" \
      '{projectId:$p, externalSessionId:$e, agentType:"hermes", platformSource:"hook"}')"
    resp="$(curl -sS --max-time 3 -X POST "$W/v1/sessions/start" \
      -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
      -d "$body" 2>/dev/null)" || { echo '{}'; exit 0; }
    iid="$(printf '%s' "$resp" | jq -r '.session.id // empty' 2>/dev/null)"
    [ -n "$iid" ] && printf '%s' "$iid" > "/tmp/cmem-sess-$sid" 2>/dev/null
    ;;
  subagent_stop|on_session_end)
    if [ -f "/tmp/cmem-sess-$sid" ]; then
      iid="$(cat "/tmp/cmem-sess-$sid" 2>/dev/null)"
      [ -n "$iid" ] && curl -sS --max-time 3 -X POST "$W/v1/sessions/$iid/end" \
        -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
        -d '{}' >/dev/null 2>&1 &
    fi
    ;;
esac

echo '{}'
