"""Versão 3 - o círculo. Os 314 primeiros dígitos de pi em 3 min 14 s.

Pedido do dono, 21/09/2026: a peça dura 3:14, usa 314 dígitos, e algo nela
lembra um círculo - forma circular, cânone circular e palíndromo, os três.

  palíndromo      a peça inteira é espelhada: a segunda metade é a primeira de
                  trás para frente, nota a nota, em todas as vozes
  cânone          as cordas são uma roda: violino I lê pi em colcheias, e violino
                  II, viola e violoncelo entram com a mesma linha, 40 tempos um
                  depois do outro; a flauta canta a linha quatro vezes mais lenta
  forma circular  o espelho faz a peça acabar no som em que começou, e o
                  arquivo emenda em loop sem costura

A conta que amarra tudo: um dígito por colcheia, 314 dígitos, 157 tempos até o
eixo e 314 tempos no total, tocados em 194 s (97,11 semínimas por minuto). O
314º dígito de pi é 3, o mesmo do primeiro: a linha sai de Dó e chega a Dó no
eixo. Isso não foi escolhido, foi medido.

A dinâmica é a sombra do círculo: velocity = 40 + 55 x (1 - cos θ) / 2, com θ
dando uma volta inteira na peça. Do pp da abertura ao ff no eixo, e de volta.

O que este arquivo NÃO decide: o mapeamento dos dígitos 8, 9 e 0 continua o
provisório da v2 (8 e 9 são Lá e Si uma oitava acima; 0 é pausa). Isso é a P2.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi
from v2 import MAPEAMENTO, ORDEM, PROGRAMA, T_TICKS

SUBTITULO = "sexteto, versão 3 - o círculo"
DIGITOS = 314
PASSO = 0.5                   # colcheia: um dígito por colcheia no violino I
TEMPOS = DIGITOS * PASSO * 2  # 314 tempos: 157 até o eixo, 157 de volta
EIXO = TEMPOS / 2
DURACAO_S = 194.0             # 3 min 14 s
TEMPO_US = round(DURACAO_S * 1e6 / TEMPOS)   # microssegundos por semínima
COMPASSO = 2                  # 2/4: 157 compassos, e o eixo cai no meio do 79º

# A roda: (voz, entrada em tempos, deslocamento de oitava). Violinos em uníssono,
# viola uma oitava abaixo e violoncelo duas, como numa roda cantada.
RODA = [("Violino I", 0.0, 0), ("Violino II", 40.0, 0),
        ("Viola", 80.0, -12), ("Violoncelo", 120.0, -24)]
AUMENTACAO = 4.0              # a flauta canta a mesma linha, quatro vezes mais lenta
OITAVA_FLAUTA = 12

# O sino do piano: Lá menor no grave, tocado a cada entrada da roda e no eixo.
# O espelho faz o sino tocar também em cada saída.
SINOS = [0.0, 40.0, 80.0, 120.0, EIXO - 2]
ACORDE_SINO = (33, 40, 45, 48, 52)   # Lá1, Mi2, Lá2, Dó3, Mi3
DURACAO_SINO = 4.0

PAN = {"Flauta": 64, "Violino I": 30, "Violino II": 98,
       "Viola": 46, "Violoncelo": 82, "Piano": 64}

ANDAMENTO = [(0, round(60e6 / TEMPO_US, 2))]
MARCAS = [("A", 0.0, 40.0), ("B", 40.0, 80.0), ("C", 80.0, 120.0), ("D", 120.0, EIXO),
          ("D'", EIXO, TEMPOS - 120), ("C'", TEMPOS - 120, TEMPOS - 80),
          ("B'", TEMPOS - 80, TEMPOS - 40), ("A'", TEMPOS - 40, TEMPOS)]

Evento = tuple[float, float, int, int]   # (início, duração, altura, velocity) em tempos


def velocity(t: float) -> int:
    """A sombra do círculo: o cosseno de uma volta inteira, de pp a ff e de volta."""
    return round(40 + 55 * (1 - math.cos(2 * math.pi * t / TEMPOS)) / 2)


DINAMICA = [(t, velocity(t)) for t in (0, 40, 80, 120, EIXO, TEMPOS - 120, TEMPOS - 80, TEMPOS - 40)]


def linha(digitos: str, entrada: float, fator: float, oitava: int) -> list[Evento]:
    """A linha de pi a partir de `entrada`, até o eixo. O 0 é pausa e gasta tempo."""
    eventos = []
    for i, d in enumerate(digitos):
        ini = entrada + i * PASSO * fator
        if ini >= EIXO:
            break
        if MAPEAMENTO[d] is not None:
            eventos.append((ini, PASSO * fator, MAPEAMENTO[d] + oitava, velocity(ini)))
    return eventos


def espelhar(eventos: list[Evento]) -> list[Evento]:
    """Primeira metade mais o retrógrado dela. A nota que chega ao eixo vira
    uma nota só, simétrica, que segura o eixo."""
    saida = []
    for ini, dur, altura, vel in eventos:
        fim = ini + dur
        if fim >= EIXO:
            saida.append((ini, 2 * (EIXO - ini), altura, vel))
        else:
            saida += [(ini, dur, altura, vel), (TEMPOS - fim, dur, altura, vel)]
    return sorted(saida)


def compor(digitos: str):
    partes: dict[str, list[Evento]] = {}
    for nome, entrada, oitava in RODA:
        partes[nome] = espelhar(linha(digitos, entrada, 1.0, oitava))
    partes["Flauta"] = espelhar(linha(digitos, 0.0, AUMENTACAO, OITAVA_FLAUTA))
    partes["Piano"] = espelhar([(t, DURACAO_SINO, a, velocity(t)) for t in SINOS for a in ACORDE_SINO])
    acordes = [None] * int(TEMPOS // COMPASSO)   # sem cifra: a harmonia é a roda
    return partes, acordes, MARCAS, TEMPOS


def escrever_midi(partes, caminho: Path) -> None:
    arq = mido.MidiFile(ticks_per_beat=T_TICKS)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=COMPASSO, denominator=4, time=0))
    meta.append(mido.MetaMessage("key_signature", key="Am", time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=TEMPO_US, time=0))
    arq.tracks.append(meta)
    for canal, nome in enumerate(ORDEM):
        trilha = mido.MidiTrack()
        trilha.append(mido.MetaMessage("track_name", name=nome, time=0))
        trilha.append(mido.Message("program_change", channel=canal, program=PROGRAMA[nome], time=0))
        trilha.append(mido.Message("control_change", channel=canal, control=91, value=78, time=0))
        trilha.append(mido.Message("control_change", channel=canal, control=10, value=PAN[nome], time=0))
        pontos = []
        for ini, dur, altura, vel in partes[nome]:
            pontos.append((int(round(ini * T_TICKS)), 1, "note_on", altura, vel))
            pontos.append((int(round((ini + dur) * T_TICKS)), 0, "note_off", altura, 0))
        pontos.sort()
        cursor = 0
        for tick, _, tipo, altura, vel in pontos:
            trilha.append(mido.Message(tipo, channel=canal, note=altura, velocity=vel, time=tick - cursor))
            cursor = tick
        trilha.append(mido.MetaMessage("end_of_track", time=0))
        arq.tracks.append(trilha)
    arq.save(str(caminho))


def gravar_audio(midi: Path) -> None:
    """MIDI -> WAV com a cauda do sintetizador -> corte em 194 s com fade de 0,3 s -> MP3.
    O arquivo dura exatamente a peça, e por isso emenda em loop."""
    from renderizar import midi_para_wav, reverb
    raiz = Path(__file__).resolve().parent.parent
    wav = midi.with_suffix(".wav")
    midi_para_wav(midi, raiz / "assets/soundfonts/FluidR3_GM.sf2", wav)
    reverb(wav)
    cortado = midi.with_suffix(".corte.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-t", f"{DURACAO_S}",
                    "-af", f"afade=t=out:st={DURACAO_S - 0.3}:d=0.3", str(cortado)], check=True)
    cortado.replace(wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
                    "-b:a", "192k", "-metadata", "title=Música do Pi - o círculo",
                    "-metadata", "artist=Natura", str(midi.with_suffix(".mp3"))], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v3")
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()

    digitos = digitos_de_pi(DIGITOS)
    partes, acordes, marcas, tempos = compor(digitos)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    midi = saida.with_suffix(".mid")
    escrever_midi(partes, midi)
    saida.with_name(saida.name + "-mapeamento.json").write_text(json.dumps(
        {"mapeamento": MAPEAMENTO, "digitos": DIGITOS, "compasso": f"{COMPASSO}/4",
         "andamento": ANDAMENTO, "formacao": ORDEM,
         "secoes": [{"letra": l, "inicio": i, "fim": f} for l, i, f in marcas]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.sem_audio:
        gravar_audio(midi)

    print(f"{DIGITOS} dígitos, {len(acordes)} compassos de {COMPASSO}/4, {tempos:.0f} tempos "
          f"a {ANDAMENTO[0][1]} bpm = {tempos * TEMPO_US / 1e6:.3f} s")
    for nome in ORDEM:
        print(f"  {nome:<12} {len(partes[nome]):3d} notas")


if __name__ == "__main__":
    main()
