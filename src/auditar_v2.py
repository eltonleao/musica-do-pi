"""Auditoria independente do que o oráculo `avaliar_v2.py` não vê.

Existe porque o oráculo é uma régua, e régua se burla. Na primeira rodada do
teste de modelos (20/09/2026), um executor alcançou 6/6 inserindo uma nota de
velocity 1 depois do fim da música: inaudível, mas ela estica o denominador da
fração de pausa. O placar subiu sem que uma pausa existisse.

O que esta auditoria mede, e que o oráculo não media:
  inaudiveis   notas com velocity <= 5 (não soam, mas contam em qualquer régua
               que conte eventos)
  pausa_real   fração de tempos sem ataque audível ENTRE o primeiro e o último
               ataque audível da linha, que é a pausa que o ouvinte percebe
  cauda        distância entre o último ataque audível e o último evento
  vozes_magras vozes com menos de 0,5 nota por compasso: quem quase não toca
               passa trivialmente na conferência de paralelas
  silencio_final segundos de silêncio no fim do WAV (acima de -50 dBFS)

Uso: python src/auditar_v2.py build/v2-haiku.mid [build/outro.mid ...]
Sai 0 se nenhum arquivo tiver achado; 1 se algum tiver.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import mido

AUDIVEL = 5          # velocity <= 5 não soa em nenhum SoundFont razoável
COMPASSO = 4


def ataques(track, tpb: int) -> list[tuple[float, int, int]]:
    tick, saida = 0, []
    for m in track:
        tick += m.time
        if m.type == "note_on" and m.velocity > 0:
            saida.append((tick / tpb, m.note, m.velocity))
    return saida


def nome_da(track) -> str:
    return next((str(m.name) for m in track if m.type == "track_name"), "?")


def silencio_final(wav: Path) -> float:
    if not wav.exists():
        return -1.0
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav),
                        "-af", "silencedetect=noise=-50dB:d=0.5", "-f", "null", "-"],
                       capture_output=True, text=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(wav)], capture_output=True, text=True)
    try:
        total = float(dur.stdout.strip())
    except ValueError:
        return -1.0
    inicios = [float(l.split("silence_start:")[1].strip())
               for l in r.stderr.splitlines() if "silence_start:" in l]
    fins = [l for l in r.stderr.splitlines() if "silence_end:" in l]
    if inicios and len(fins) < len(inicios):     # último silêncio vai até o fim
        return total - inicios[-1]
    return 0.0


def auditar(midi: Path) -> list[str]:
    achados: list[str] = []
    arq = mido.MidiFile(str(midi))
    tpb = arq.ticks_per_beat
    linha = None
    total_compassos = 0
    for t in arq.tracks:
        nome = nome_da(t)
        ons = ataques(t, tpb)
        if not ons:
            continue
        total_compassos = max(total_compassos, int(ons[-1][0] // COMPASSO) + 1)
        mudas = [(round(x, 2), n, v) for x, n, v in ons if v <= AUDIVEL]
        if mudas:
            achados.append(f"{nome}: {len(mudas)} nota(s) inaudível(is) (velocity <= {AUDIVEL}) em {mudas[:3]}")
        if nome == "Violino I":
            linha = ons

    if linha:
        audiveis = [(x, n, v) for x, n, v in linha if v > AUDIVEL]
        if audiveis:
            ini, fim = audiveis[0][0], audiveis[-1][0]
            span = fim - ini + 1
            tempos_com_ataque = len({round(x) for x, _, _ in audiveis})
            pausa_real = 1 - tempos_com_ataque / span if span else 0
            cauda = linha[-1][0] - fim
            achados.append(f"MEDIDO pausa_real da linha: {pausa_real*100:.0f}% "
                           f"({tempos_com_ataque} ataques audíveis em {span:.0f} tempos)")
            if cauda >= 1:
                achados.append(f"ATENÇÃO cauda de {cauda:.0f} tempos depois do último ataque audível - "
                               f"estica o denominador de qualquer fração de pausa")

    for t in arq.tracks:
        nome = nome_da(t)
        ons = [o for o in ataques(t, tpb) if o[2] > AUDIVEL]
        if nome in ("?", "Violino I") or not total_compassos:
            continue
        densidade = len(ons) / total_compassos
        if densidade < 0.5:
            achados.append(f"{nome}: voz magra, {len(ons)} notas em {total_compassos} compassos "
                           f"({densidade:.2f} por compasso) - passa em condução de vozes por ausência")

    s = silencio_final(midi.with_suffix(".wav"))
    if s > 3:
        achados.append(f"ATENÇÃO {s:.1f} s de silêncio no fim do WAV - infla a duração medida")
    return achados


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: auditar_v2.py <arquivo.mid> [...]")
        return 2
    ruim = 0
    for alvo in sys.argv[1:]:
        p = Path(alvo)
        print(f"== {p.name}")
        if not p.exists():
            print("   ausente"); ruim += 1; continue
        achados = auditar(p)
        problemas = [a for a in achados if not a.startswith("MEDIDO")]
        for a in achados:
            print("   " + a)
        if problemas:
            ruim += 1
        else:
            print("   sem achado")
    return 1 if ruim else 0


if __name__ == "__main__":
    sys.exit(main())
