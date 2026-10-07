"""Música do Fibonacci, versão 1: só violino I, uma nota por termo.

Uso: python src/fibonacci/fib1.py --termos 20 --saida build/fibonacci/mid/fib1

A ideia é a mesma da v1 do pi: extração crua, sem harmonia, sem ritmo
variado, sem outras vozes - só a linha, pra ouvir e ir decidindo o que
incrementar depois.

Mapeamento: cada termo de Fibonacci, módulo 12, é um semitom a partir de Dó4
(altura MIDI 60). É aritmética modular pura, sem escolha de escala - os
termos crescem sem limite, e o resto por 12 é o que os prende a uma oitava.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mido

from fibonacci_digitos import fibonacci

TONICA = 60   # Dó4
T_TICKS = 480
DURACAO_TEMPOS = 1.0   # uma semínima por termo


def linha_de_fibonacci(termos: list[int]) -> list[int]:
    return [TONICA + (t % 12) for t in termos]


def escrever_midi(alturas: list[int], caminho: Path) -> None:
    arq = mido.MidiFile(ticks_per_beat=T_TICKS)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(90), time=0))
    arq.tracks.append(meta)

    trilha = mido.MidiTrack()
    trilha.append(mido.MetaMessage("track_name", name="Violino I", time=0))
    trilha.append(mido.Message("program_change", channel=0, program=40, time=0))
    dur_ticks = int(DURACAO_TEMPOS * T_TICKS)
    for altura in alturas:
        trilha.append(mido.Message("note_on", channel=0, note=altura, velocity=90, time=0))
        trilha.append(mido.Message("note_off", channel=0, note=altura, velocity=0, time=dur_ticks))
    trilha.append(mido.MetaMessage("end_of_track", time=T_TICKS))
    arq.tracks.append(trilha)
    arq.save(str(caminho))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--termos", type=int, default=20)
    ap.add_argument("--saida", default="build/fibonacci/mid/fib1")
    args = ap.parse_args()

    termos = fibonacci(args.termos)
    alturas = linha_de_fibonacci(termos)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    escrever_midi(alturas, saida.with_suffix(".mid"))
    saida.with_name(saida.name + "-mapeamento.json").write_text(json.dumps(
        {"termos": termos, "alturas": alturas, "tonica": TONICA, "compasso": "4/4"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{args.termos} termos: {termos}")
    print(f"alturas MIDI: {alturas}")


if __name__ == "__main__":
    main()
