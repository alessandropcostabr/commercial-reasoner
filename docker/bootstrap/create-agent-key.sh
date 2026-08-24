#!/usr/bin/env bash
# Agente Fase 1 - bootstrap POS-BOOT do cmem.
# Cria o team+project "agent" no pg-agent e emite uma api-key com escopo
# memories:read,memories:write para os hooks do Hermes. Imprime a key e a
# linha pronta para colar no .env (CMEM_API_KEY=...).
#
# Pre-requisito: `docker compose up -d pg-agent valkey cmem` e o cmem healthy
# (o schema das tabelas e bootstrapado pelo server-beta no boot).
#
# Uso (no 192.0.2.10, dentro de docker/):  ./bootstrap/create-agent-key.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."   # docker/

# shellcheck disable=SC1091
[ -f .env ] && set -a && . ./.env && set +a

PROJ="${CMEM_PROJECT:-agent}"
TEAM="${CMEM_TEAM:-agent-team}"

echo "[bootstrap] criando team '$TEAM' + project '$PROJ' no pg-agent..." >&2
docker compose exec -T pg-agent psql -U "${PGAGENT_USER:-agent}" -d "${PGAGENT_DB:-agent}" \
  -v ON_ERROR_STOP=1 <<SQL
INSERT INTO teams (id, name, metadata)
VALUES ('$TEAM', 'agent', '{}'::jsonb)
ON CONFLICT (id) DO NOTHING;
INSERT INTO projects (id, team_id, name, metadata)
VALUES ('$PROJ', '$TEAM', 'agent', '{}'::jsonb)
ON CONFLICT (id) DO NOTHING;
SQL

echo "[bootstrap] emitindo api-key (memories:read,write) para o project '$PROJ'..." >&2
# node, nao bun: a CPU do 192.0.2.10 (CPU antiga, sem SSE4.2) da SIGILL no bun.
out="$(docker compose exec -T cmem \
  node /opt/claude-mem/scripts/server-beta-service.cjs server api-key create \
  --scope memories:read,memories:write \
  --team "$TEAM" --project "$PROJ" --name agent-hooks)"

# python3 (o host 192.0.2.10 nao tem jq); extrai .key do objeto JSON (do 1o { ao
# ultimo }) caso haja linhas de log antes/depois no stdout.
key="$(printf '%s' "$out" | python3 -c 'import sys,json
s=sys.stdin.read(); i=s.find("{"); j=s.rfind("}")
try:
    print(json.loads(s[i:j+1]).get("key","") if i>=0 and j>i else "")
except Exception:
    pass')"
if [ -z "$key" ]; then
  echo "[bootstrap] ERRO: nao consegui extrair a key. Saida bruta:" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi

echo "" >&2
echo "[bootstrap] OK. Adicione ao docker/.env e recrie o hermes:" >&2
echo "CMEM_API_KEY=$key"
