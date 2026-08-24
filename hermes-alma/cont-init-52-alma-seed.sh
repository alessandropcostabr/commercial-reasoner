#!/command/with-contenv sh
# Seeda a alma (SOUL.md + skill vendas) do bind /seed para /opt/data.
# Roda APOS 01-hermes-setup (que so cria SOUL.md se ausente) -> sobrescreve.
# Estrutura correta do Hermes: /opt/data/skills/<categoria>/<nome>/SKILL.md
if [ -f /seed/SOUL.md ]; then
  install -o hermes -g hermes -m 644 /seed/SOUL.md /opt/data/SOUL.md 2>/dev/null && echo "[52-alma] SOUL.md seeded" || echo "[52-alma] WARN SOUL.md"
else
  echo "[52-alma] WARN: /seed/SOUL.md ausente"
fi
if [ -f /seed/skills/vendas/SKILL.md ]; then
  mkdir -p /opt/data/skills/sales/vendas
  install -o hermes -g hermes -m 644 /seed/skills/vendas/SKILL.md /opt/data/skills/sales/vendas/SKILL.md 2>/dev/null && echo "[52-alma] skill vendas seeded" || echo "[52-alma] WARN skill"
  chown -R hermes:hermes /opt/data/skills/sales 2>/dev/null
else
  echo "[52-alma] WARN: skill ausente"
fi
