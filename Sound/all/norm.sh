#!/usr/bin/env bash
set -e

TARGET_I=-16
TARGET_TP=-1.0
TARGET_LRA=11

for f in *.wav; do
  [ -f "$f" ] || continue

  base="${f%.wav}"
  stats="${base}_stats.txt"
  out="${base}_normalized.wav"

  echo ">>> PASS 1: Analysiere $f"

  # Pass 1: ffmpeg erzeugt JSON unter stderr
  ffmpeg -hide_banner -i "$f" \
    -af "loudnorm=I=$TARGET_I:TP=$TARGET_TP:LRA=$TARGET_LRA:print_format=json" \
    -f null - \
    2> "$stats"

  # JSON ab erstem '{' extrahieren
  json=$(sed -n '/^\s*{/,/}/p' "$stats")

  # JSON testen
  echo "$json" | jq . >/dev/null || {
    echo "!!! Fehler: JSON konnte nicht extrahiert werden"
    echo "Datei: $stats"
    exit 1
  }

  # Werte auslesen
  measured_I=$(echo "$json" | jq -r '.input_i')
  measured_TP=$(echo "$json" | jq -r '.input_tp')
  measured_LRA=$(echo "$json" | jq -r '.input_lra')
  measured_thresh=$(echo "$json" | jq -r '.input_thresh')
  offset=$(echo "$json" | jq -r '.target_offset')

  filter="loudnorm=I=$TARGET_I:TP=$TARGET_TP:LRA=$TARGET_LRA:"
  filter+="measured_I=$measured_I:measured_TP=$measured_TP:"
  filter+="measured_LRA=$measured_LRA:measured_thresh=$measured_thresh:"
  filter+="offset=$offset"

  echo ">>> PASS 2: Normalisiere nach $out"

  # Pass 2: Normalisierung
  ffmpeg -hide_banner -y -i "$f" -af "$filter" "$out"

  echo "✓ Fertig: $out"
done
