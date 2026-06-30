#!/usr/bin/env bash
# Reavalia todas as companies com BUG_MARKER em ordem de prioridade.
# Para limpo ao primeiro spend limit (o script python já faz o break).
# Stone é ignorada (Alberto não quer candidatar lá).
set -euo pipefail

SCRIPT="python scripts/reevaluate_bug_victims.py --title-only --concurrency 5"
LOG="$HOME/.gauntler/reevaluate_all.log"

echo "=============================" | tee -a "$LOG"
echo "Início: $(date)" | tee -a "$LOG"
echo "=============================" | tee -a "$LOG"

COMPANIES=(
  # Engenharia-heavy primeiro — mais chance de achar vagas relevantes
  gitlab grafanalabs cloudflare anthropic figma vercel stripe planetscale
  # BR restantes (menos signal, mas completar)
  ifood quintoandar gympass nubank c6bank
  # stone: IGNORADA (Alberto não quer candidatar lá)
)

for company in "${COMPANIES[@]}"; do
  echo "" | tee -a "$LOG"
  echo "--- $company ---" | tee -a "$LOG"
  # O script retorna exit 0 mesmo em spend limit (para com break interno).
  # Se ele imprimiu "COTA ATINGIDA", a linha abaixo vai detectar e parar.
  output=$($SCRIPT --company "$company" 2>/dev/null)
  echo "$output" | tee -a "$LOG"
  if echo "$output" | grep -q "COTA ATINGIDA"; then
    echo "" | tee -a "$LOG"
    echo "Spend limit atingido em $company — parando." | tee -a "$LOG"
    break
  fi
done

echo "" | tee -a "$LOG"
echo "Fim: $(date)" | tee -a "$LOG"
