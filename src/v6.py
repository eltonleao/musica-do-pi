"""v6 - a Sonata ao Luar e o Bach matemático sobre os dígitos de pi.

Desenho: eltonleao-obsidian/Projects/Música do Pi/analysis/v6-desenho.md.

A (compassos 1-14): frase de 7 dígitos no compasso ímpar e eco no par, figura ♪♪♪♪♪♪♩.
B (15-24): Si♭ com baixo Ré em 15-16, pedal de Mi em 17-24, dígitos 50-61 em semínimas
em 17-19 e o retrógrado deles em 20-22, com a flauta uma oitava acima; 23-24 só a figura.
A' (25-38): o retrógrado exato de A, figura ♩♪♪♪♪♪♪, com o eco sempre no segundo compasso.

Harmonia por programação dinâmica sobre os 76 meios compassos: o dígito do tempo forte
é nota do acorde, todo Sol♯ soa sobre um acorde com Mi, a dominante só sai para Lá menor,
e o eco repete os acordes da frase.

Uso: python src/v6.py [--saida build/v6] [--sem-audio]
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from itertools import combinations
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi
from v2 import ORDEM, PROGRAMA, T_TICKS

TEMPOS = 152                  # 38 compassos de 4/4
EIXO = 76
COMPASSO = 4
MEIOS = TEMPOS // 2
DURACAO_S = 101.0
TEMPO_US = round(DURACAO_S * 1e6 / TEMPOS)

MAPEAMENTO = {"0": 68, "1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77,
              "7": 80, "8": 81, "9": 83}

FIGURA_A = [(0, .5), (.5, .5), (1, .5), (1.5, .5), (2, .5), (2.5, .5), (3, 1)]
ECO = 12                      # o eco soa 12 de velocity abaixo da frase

ACORDES = {                   # nome -> (fundamental, classes)
    "Am": (9, {9, 0, 4}), "Dm": (2, {2, 5, 9}), "E": (4, {4, 8, 11}), "E7": (4, {4, 8, 11, 2}),
    "E7b9": (4, {4, 8, 11, 2, 5}), "F": (5, {5, 9, 0}), "C": (0, {0, 4, 7}), "G": (7, {7, 11, 2}),
    "Bm7b5": (11, {11, 2, 5, 9}), "Bb": (10, {10, 2, 5}),
}
MI = {"E", "E7", "E7b9"}
VOCABULARIO = ["Am", "Dm", "E", "E7", "E7b9", "F", "C", "G", "Bm7b5"]
PESO = {"Am": 0.0, "E": 0.2, "E7": 0.3, "Dm": 0.4, "F": 0.5, "E7b9": 0.6, "Bm7b5": 0.7,
        "C": 0.8, "G": 1.0, "Bb": 0.0}
PREPARA_MI = {"Bm7b5", "F", "Dm"}

PAN = {"Flauta": 64, "Violino I": 30, "Violino II": 98, "Viola": 46, "Violoncelo": 82, "Piano": 64}
CC7 = {"Flauta": 100, "Violino I": 110, "Violino II": 70, "Viola": 70, "Violoncelo": 85, "Piano": 80}
VELOCITY = {"Violino I": (40, 100), "Flauta": (60, 92), "Violino II": (36, 56), "Viola": (36, 56),
            "Violoncelo": (40, 72), "Piano": (40, 76)}
ENTRADA = {"Violoncelo": 8, "Viola": 11, "Violino II": 13}    # entra no compasso k, sai no 39 - k
TESSITURA_DO_PAD = {"Viola": (53, 62), "Violino II": (60, 67)}

Nota = tuple[float, float, int, bool]      # início, duração, altura, é eco
Evento = tuple[float, float, int, int]     # início, duração, altura, velocity


def vel(voz: str, t: float) -> int:
    """Cosseno com o pico no eixo."""
    lo, hi = VELOCITY[voz]
    return max(1, min(127, round(lo + (hi - lo) * (1 - math.cos(2 * math.pi * t / TEMPOS)) / 2)))


def melodia(dig: str) -> list[Nota]:
    a = []
    for f in range(7):
        frase = dig[7 * f: 7 * f + 7]
        for rep in (0, 1):
            base = (2 * f + rep) * COMPASSO
            a += [(base + p, d, MAPEAMENTO[c], rep == 1) for (p, d), c in zip(FIGURA_A, frase)]
    b = [(64 + i, 1, MAPEAMENTO[c], False) for i, c in enumerate(dig[49:61])]
    b += [(TEMPOS - ini - dur, dur, alt, False) for ini, dur, alt, _ in b]
    a_linha = []
    for ini, dur, alt, _ in a:
        novo = TEMPOS - ini - dur
        a_linha.append((novo, dur, alt, (int(novo // COMPASSO) + 1) % 2 == 0))
    return sorted(a + b + a_linha)


def harmonizar(notas: list[Nota]) -> list[str]:
    por_meio: list[list[tuple[float, float, int]]] = [[] for _ in range(MEIOS)]
    for ini, dur, alt, _ in notas:
        por_meio[int(ini // 2)].append((ini, dur, alt % 12))

    def permitidos(h: int) -> list[str]:
        if 28 <= h <= 31:
            return ["Bb"]
        if 44 <= h <= 47:
            return ["E7"]
        if h == 33:                         # o napolitano resolve em Mi
            return sorted(MI)
        if 32 <= h <= 43:
            return ["Am", *sorted(MI)]
        if h in (0, 1, 48, 75):
            return ["Am"]
        return VOCABULARIO

    def cabe(h: int, nome: str) -> bool:
        cls = ACORDES[nome][1]
        return all(not (ini == 2 * h and pc not in cls) and not (pc == 8 and 4 not in cls)
                   for ini, _, pc in por_meio[h])

    def encaixe(h: int, nome: str) -> float:
        cls = ACORDES[nome][1]
        custo = PESO[nome]
        for _, dur, pc in por_meio[h]:
            if pc in cls:
                continue
            custo += 0.15
            if dur >= 1 and (pc - 1) % 12 in cls:     # nona menor
                custo += 3
            if pc == 8 and nome == "C":
                custo += 2
        return custo

    def troca(a: str, b: str) -> float | None:
        if a == b:
            return 0.0
        if a in MI and b not in MI and b != "Am":
            return None
        custo = 0.4 if a in MI and b in MI else 1.0
        if (a in MI and b == "Am") or (b in MI and a in PREPARA_MI) or (a, b) == ("G", "C"):
            custo -= 0.6
        return custo

    def opcoes(h: int) -> list[str]:
        return [n for n in permitidos(h) if cabe(h, n)]

    def par(h0: int) -> list[tuple[str, ...]]:
        xs = [x for x in opcoes(h0) if x in opcoes(h0 + 2)]
        ys = [y for y in opcoes(h0 + 1) if y in opcoes(h0 + 3)]
        return [(x, y, x, y) for x in xs for y in ys]

    unidades = [par(4 * f) for f in range(7)] + [[("Bb",) * 4]]
    unidades += [[(n,) for n in opcoes(h)] for h in range(32, 44)] + [[("E7",) * 4]]
    unidades += [par(48 + 4 * g) for g in range(7)]

    estados: dict[tuple[str | None, int], tuple[float, list[str]]] = {(None, 0): (0.0, [])}
    h0 = 0
    for cands in unidades:
        if not cands:
            raise SystemExit(f"sem acorde possível no compasso {h0 // 2 + 1}")
        novos: dict[tuple[str | None, int], tuple[float, list[str]]] = {}
        for (ultimo, corrida), (c0, caminho) in estados.items():
            for seq in cands:
                custo, u, r = 0.0, ultimo, corrida
                for i, nome in enumerate(seq):
                    if u is not None:
                        t = troca(u, nome)
                        if t is None:
                            break
                        custo += t
                    r = r + 1 if nome == u else 1
                    custo += (0.8 if r > 4 else 0.0) + encaixe(h0 + i, nome)
                    u = nome
                else:
                    chave = (u, min(r, 5))
                    if chave not in novos or c0 + custo < novos[chave][0]:
                        novos[chave] = (c0 + custo, caminho + list(seq))
        if not novos:
            raise SystemExit(f"a harmonia não tem caminho no compasso {h0 // 2 + 1}")
        estados = novos
        h0 += len(cands[0])
    return min(estados.values(), key=lambda v: v[0])[1]


def baixos(acordes: list[str], notas: list[Nota]) -> list[int]:
    """Fundamental, com três exceções: Si♭ sobre Ré, o pedal de Mi e Lá menor sob Sol♯ segurado."""
    segurado = {int(ini // 2) for ini, dur, alt, _ in notas if alt % 12 == 8 and dur >= 1}
    out = []
    for h, nome in enumerate(acordes):
        if 32 <= h <= 47 or (nome == "Am" and h in segurado):
            out.append(4)
        elif nome == "Bb":
            out.append(2)
        else:
            out.append(ACORDES[nome][0])
    return out


def trechos(chaves: list, por_compasso: bool) -> list[tuple[int, int, object]]:
    """Meios compassos consecutivos com a mesma chave viram um trecho, em tempos."""
    out = []
    for h, k in enumerate(chaves):
        if out and out[-1][2] == k and not (por_compasso and h % 2 == 0):
            out[-1] = (out[-1][0], 2 * h + 2, k)
        else:
            out.append((2 * h, 2 * h + 2, k))
    return out


def voicings(nome: str) -> list[tuple[int, ...]]:
    cls = {8, 11, 2, 5} if nome == "E7b9" else ACORDES[nome][1]   # Sol♯°7 sobre o Mi do baixo
    alturas = [a for a in range(52, 68) if a % 12 in cls]
    return [c for c in combinations(alturas, 4) if {a % 12 for a in c} == cls]


def piano(acordes: list[str], graves: list[int]) -> list[Evento]:
    ev: list[Evento] = []
    anterior = None
    for t in range(TEMPOS):
        cands = voicings(acordes[t // 2])
        if anterior is None:
            v = min(cands, key=lambda c: abs(sum(c) / 4 - 60))
        else:
            v = min(cands, key=lambda c: (sum(abs(a - b) for a, b in zip(c, anterior)), c))
        anterior = v
        dim = 1 - 0.25 * (t - 88) / 8 if 88 <= t < 96 else 1.0
        ev += [(t + k / 4, 1 - k / 4, alt, round(vel("Piano", t) * dim)) for k, alt in enumerate(v)]
    for ini, fim, (_, pc) in trechos(list(zip(acordes, graves)), por_compasso=True):
        grave = next(a for a in range(26, 37) if a % 12 == pc)
        ev += [(ini, fim - ini, grave, vel("Piano", ini)), (ini, fim - ini, grave + 12, vel("Piano", ini))]
    return ev


def violoncelo(graves: list[int]) -> list[Evento]:
    t0, t1 = (ENTRADA["Violoncelo"] - 1) * COMPASSO, (39 - ENTRADA["Violoncelo"]) * COMPASSO
    ev = []
    for ini, fim, pc in trechos(graves, por_compasso=True):
        if t0 <= ini < t1:
            ev.append((ini, fim - ini, next(a for a in range(38, 49) if a % 12 == pc), vel("Violoncelo", ini)))
    return ev


def pad(voz: str, acordes: list[str], notas: list[Nota], outra: list[Evento]) -> list[Evento]:
    lo, hi = TESSITURA_DO_PAD[voz]
    t0, t1 = (ENTRADA[voz] - 1) * COMPASSO, (39 - ENTRADA[voz]) * COMPASSO
    anterior = (lo + hi) // 2
    ev = []
    for ini, fim, nome in trechos(acordes, por_compasso=False):
        ini, fim = max(ini, t0), min(fim, t1)
        if ini >= fim:
            continue
        cls = ACORDES[nome][1]
        mel = {alt % 12 for i, d, alt, _ in notas if i < fim and i + d > ini}
        out = {alt % 12 for i, d, alt, _ in outra if i < fim and i + d > ini}
        cands = [a for a in range(lo, hi + 1) if a % 12 in cls]
        for extra in (mel | out, out, set()):
            boas = [a for a in cands if all((a - q) % 12 not in (1, 11) for q in cls | extra)]
            if boas:
                break
        else:
            boas = cands
        escolhida = min(boas, key=lambda a: (abs(a - anterior), a))
        ev.append((ini, fim - ini, escolhida, vel(voz, ini)))
        anterior = escolhida
    return ev


def compor(dig: str):
    notas = melodia(dig)
    acordes = harmonizar(notas)
    graves = baixos(acordes, notas)
    viola = pad("Viola", acordes, notas, [])
    partes = {
        "Violino I": [(i, d, a, vel("Violino I", i) - (ECO if e else 0)) for i, d, a, e in notas],
        "Flauta": [(i, d, a + 12, vel("Flauta", i)) for i, d, a, _ in notas if 64 <= i < 88],
        "Viola": viola,
        "Violino II": pad("Violino II", acordes, notas, viola),
        "Violoncelo": violoncelo(graves),
        "Piano": piano(acordes, graves),
    }
    return partes, acordes, graves


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
        trilha.append(mido.Message("control_change", channel=canal, control=7, value=CC7[nome], time=0))
        trilha.append(mido.Message("control_change", channel=canal, control=91, value=78, time=0))
        trilha.append(mido.Message("control_change", channel=canal, control=10, value=PAN[nome], time=0))
        pontos = []
        for ini, dur, altura, v in partes[nome]:
            pontos.append((int(round(ini * T_TICKS)), 1, "note_on", altura, v))
            pontos.append((int(round((ini + dur) * T_TICKS)), 0, "note_off", altura, 0))
        pontos.sort()
        cursor = 0
        for tick, _, tipo, altura, v in pontos:
            trilha.append(mido.Message(tipo, channel=canal, note=altura, velocity=v, time=tick - cursor))
            cursor = tick
        trilha.append(mido.MetaMessage("end_of_track", time=0))
        arq.tracks.append(trilha)
    arq.save(str(caminho))


def gravar_audio(midi: Path) -> None:
    """MIDI -> WAV com a cauda do sintetizador -> corte em 101 s com fade de 0,3 s -> MP3."""
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
                    "-b:a", "192k", "-metadata", "title=Música do Pi - Luar e Bach",
                    "-metadata", "artist=Natura", str(midi.with_suffix(".mp3"))], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v6")
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()
    dig = digitos_de_pi(70)
    if not dig.startswith("3141592"):
        raise SystemExit(f"dígitos inesperados: {dig[:10]}")
    partes, acordes, graves = compor(dig)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    midi = saida.with_suffix(".mid")
    escrever_midi(partes, midi)
    compassos = [f"{m + 1}:{acordes[2 * m]}/{acordes[2 * m + 1]}" for m in range(TEMPOS // COMPASSO)]
    Path(f"{saida}-mapeamento.json").write_text(json.dumps({
        "mapeamento": MAPEAMENTO, "digitos": {"A": dig[:49], "B": dig[49:61]},
        "compasso": f"{COMPASSO}/4", "andamento_bpm": round(60e6 / TEMPO_US, 2),
        "acordes_por_meio_compasso": acordes, "baixo_por_meio_compasso": graves,
        "secoes": {"A": [1, 14], "B": [15, 24], "A'": [25, 38]}, "cc7": CC7,
    }, ensure_ascii=False, indent=1))
    print(" ".join(compassos))
    print(f"{midi}: {sum(len(v) for v in partes.values())} notas, violino I {len(partes['Violino I'])}")
    if not args.sem_audio:
        gravar_audio(midi)
        print(f"{midi.with_suffix('.mp3')} gravado")


if __name__ == "__main__":
    main()
