#!/command/with-contenv sh
# Instala honcho-ai na venv do Hermes ANTES do gateway subir (uid root no cont-init).
# Idempotente: pula se já instalado.
# Usa uv (gerenciador da venv) em vez de pip (não disponível na venv).
VENV_PY=/opt/hermes/.venv/bin/python
if "$VENV_PY" -c "import honcho" 2>/dev/null || "$VENV_PY" -c "import honcho_ai" 2>/dev/null; then
  echo "[50-honcho-ai] já instalado"
else
  echo "[50-honcho-ai] instalando honcho-ai via uv"
  uv pip install --python "$VENV_PY" --no-cache-dir honcho-ai 2>&1 | tail -3
fi
