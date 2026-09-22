"""v7 - Lá maior e devagar: o motivo como Beethoven fazia, sobre os dígitos de pi.

Pesquisa: eltonleao-obsidian/pesquisas/motivo-de-beethoven-para-a-musica-do-pi/relatorio.md.
A v6 fica intacta. A v7 troca três coisas a pedido do dono ("rápido demais e dramático
demais, vamos tentar um tom maior"): Lá maior no lugar de Lá menor (Dó♯ e Fá♯ no mapeamento),
66,5 bpm com o piano em colcheias no lugar de 90 bpm em semicolcheias, e o motivo.

O motivo é um ritmo, não uma frase de dígitos: quatro dígitos em dois compassos, o primeiro
repetido em pontuado (♩. ♪), dois em semínima e o último longo, com pausa de respiração. A
sentença de 8 compassos é ideia, ideia com os dígitos seguintes no mesmo ritmo, dois fragmentos
de um compasso com a cabeça (♩. ♪ 𝅗𝅥), a liquidação e a nota longa da cadência. O que se
escolhe é quantos dígitos a liquidação lê: o bastante para a cadência cair no acorde de Lá.

Forma palíndroma, em compassos: 1 introdução, 2-9 A (a sentença, violino I), 10 transição,
11-18 B (a cabeça do motivo na flauta, 8 dígitos e o retrógrado deles, eixo no compasso 15),
19 retransição em Mi7, 20-27 A' (os dígitos de A de trás para a frente, no mesmo ritmo),
28 acorde final. As alturas lidas formam um palíndromo; o ritmo anda sempre para a frente,
porque é ele que identifica o motivo.

Uso: python src/v7.py [--saida build/v7] [--sem-audio]
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

TEMPOS = 112                  # 28 compassos de 4/4
COMPASSO = 4
MEIOS = TEMPOS // 2
DURACAO_S = 101.0
TEMPO_US = round(DURACAO_S * 1e6 / TEMPOS)
FIM = 110                     # tudo solta aqui; o resto é reverberação

MAPEAMENTO = {"0": 68, "1": 69, "2": 71, "3": 73, "4": 74, "5": 76, "6": 78,
              "7": 80, "8": 81, "9": 83}

IDEIA = [(0, 1.5, 0), (1.5, .5, 0), (2, 1, 1), (3, 1, 2), (4, 3, 3)]    # início, duração, dígito
CABECA = [(0, 1.5, 0), (1.5, .5, 0), (2, 2, 1)]
LIQUIDACAO = {2: [(0, 2), (2, 2)], 3: [(0, 1), (1, 1), (2, 2)],
              4: [(0, 1), (1, 1), (2, 1), (3, 1)], 5: [(0, 1), (1, 1), (2, 1), (3, .5), (3.5, .5)]}
TONICA = {"1", "3", "5", "8"}  # Lá, Dó♯, Mi, Lá

ACORDES = {                   # nome -> (fundamental, classes)
    "A": (9, {9, 1, 4}), "D": (2, {2, 6, 9}), "E": (4, {4, 8, 11}), "E7": (4, {4, 8, 11, 2}),
    "F#m": (6, {6, 9, 1}), "Bm": (11, {11, 2, 6}), "C#m": (1, {1, 4, 8}),
}
PESO = {"A": 0.0, "D": 0.15, "E": 0.15, "E7": 0.3, "F#m": 0.4, "Bm": 0.4, "C#m": 0.8}
DOMINANTE = {"E", "E7"}
BOAS = {("A", "D"), ("A", "E"), ("A", "F#m"), ("A", "Bm"), ("D", "E"), ("D", "E7"), ("D", "A"),
        ("Bm", "E"), ("Bm", "E7"), ("E", "A"), ("E7", "A"), ("E", "E7"), ("E", "F#m"),
        ("E7", "F#m"), ("F#m", "Bm"), ("F#m", "D"), ("C#m", "F#m"), ("C#m", "D")}
FIXOS = {0: ["A"], 1: ["A"], 16: ["A"], 36: ["E7"], 37: ["E7"], 38: ["A"],
         52: ["A"], 53: ["A"], 54: ["A"], 55: ["A"]}
PEDAL = range(32, 38)         # compassos 17-19, baixo em Mi

PAN = {"Flauta": 64, "Violino I": 30, "Violino II": 98, "Viola": 46, "Violoncelo": 82, "Piano": 64}
CC7 = {"Flauta": 105, "Violino I": 110, "Violino II": 64, "Viola": 64, "Violoncelo": 80, "Piano": 80}
VELOCITY = {"Violino I": (58, 80), "Flauta": (62, 80), "Violino II": (32, 46), "Viola": (32, 46),
            "Violoncelo": (40, 58), "Piano": (36, 56)}
ENTRADA = {"Violoncelo": 2, "Viola": 4, "Violino II": 6}      # entra no compasso k, sai no 29 - k
TESSITURA_DO_PAD = {"Viola": (53, 62), "Violino II": (60, 67)}

Nota = tuple[float, float, int, str]       # início, duração, altura, voz
Evento = tuple[float, float, int, int]     # início, duração, altura, velocity


def vel(voz: str, t: float) -> int:
    """Cosseno com o pico no eixo."""
    lo, hi = VELOCITY[voz]
    return max(1, min(127, round(lo + (hi - lo) * (1 - math.cos(2 * math.pi * t / TEMPOS)) / 2)))


def escolher_k(dig: str) -> int:
    """Quantos dígitos a liquidação lê: a cadência no acorde de Lá, de preferência na fundamental."""
    return min(LIQUIDACAO, key=lambda k: (dig[12 + k] not in TONICA,
                                          abs(k - 4) + (0 if dig[12 + k] in "18" else .5)))


def sentenca(dig: str, t0: float, k: int, final: float) -> list[tuple[float, float, str]]:
    """Ideia, ideia, cabeça, cabeça, liquidação de k dígitos e a nota da cadência: 13 + k dígitos."""
    out: list[tuple[float, float, str]] = []
    for base, forma, pedaco in ((0, IDEIA, dig[0:4]), (8, IDEIA, dig[4:8]),
                                (16, CABECA, dig[8:10]), (20, CABECA, dig[10:12])):
        out += [(t0 + base + p, d, pedaco[j]) for p, d, j in forma]
    out += [(t0 + 24 + p, d, c) for (p, d), c in zip(LIQUIDACAO[k], dig[12:12 + k])]
    out.append((t0 + 28, final, dig[12 + k]))
    return out


def melodia(dig: str) -> tuple[list[Nota], int, str, str]:
    k = escolher_k(dig)
    a = dig[:13 + k]
    b = dig[13 + k:21 + k]
    notas = [(t, d, c, "Violino I") for t, d, c in sentenca(a, 4, k, 3)]
    ida_e_volta = b + b[::-1]
    for j in range(8):
        notas += [(40 + 4 * j + p, d, ida_e_volta[2 * j + i], "Flauta") for p, d, i in CABECA]
    notas += [(t, d, c, "Violino I") for t, d, c in sentenca(a[::-1], 76, k, FIM - 104)]
    return [(t, d, MAPEAMENTO[c], voz) for t, d, c, voz in notas], k, a, b


def harmonizar(notas: list[Nota]) -> list[str]:
    def soando(h: int) -> list[tuple[float, float, int]]:
        return [(t, d, alt % 12) for t, d, alt, _ in notas if t < 2 * h + 2 and t + d > 2 * h]

    def permitidos(h: int) -> list[str]:
        if h in FIXOS:
            return FIXOS[h]
        if h in PEDAL:
            return ["E", "E7", "A", "D"]
        return list(ACORDES)

    def cabe(h: int, nome: str) -> bool:
        """A nota que soa no início do meio compasso é do acorde, e todo Sol♯ de semínima também."""
        cls = ACORDES[nome][1]
        return all(pc in cls or not (t <= 2 * h < t + d or (pc == 8 and d >= 1))
                   for t, d, pc in soando(h))

    def encaixe(h: int, nome: str) -> float:
        cls = ACORDES[nome][1]
        return PESO[nome] + sum(0.4 * d for t, d, pc in soando(h)
                                if pc not in cls and t >= 2 * h and t == int(t))

    def troca(a: str, b: str) -> float:
        if a in DOMINANTE and b not in DOMINANTE and b not in ("A", "F#m"):
            return 2.0
        return 0.5 if (a, b) in BOAS else 1.0

    estados: dict[tuple[str | None, int], tuple[float, list[str]]] = {(None, 0): (0.0, [])}
    for h in range(MEIOS):
        opcoes = [n for n in permitidos(h) if cabe(h, n)]
        if not opcoes:
            raise SystemExit(f"sem acorde possível no compasso {h // 2 + 1}")
        novos: dict[tuple[str | None, int], tuple[float, list[str]]] = {}
        for (u, r), (c0, caminho) in estados.items():
            for n in opcoes:
                custo = encaixe(h, n)
                if u is not None and n != u:
                    custo += troca(u, n) + (0.3 if h % 2 else 0.0)
                r2 = r + 1 if n == u else 1
                custo += 0.3 if r2 > 4 else 0.0
                chave = (n, min(r2, 5))
                if chave not in novos or c0 + custo < novos[chave][0]:
                    novos[chave] = (c0 + custo, caminho + [n])
        estados = novos
    return min(estados.values(), key=lambda v: v[0])[1]


def baixos(acordes: list[str]) -> list[int]:
    return [4 if h in PEDAL else ACORDES[nome][0] for h, nome in enumerate(acordes)]


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
    cls = ACORDES[nome][1]
    alturas = [a for a in range(52, 68) if a % 12 in cls]
    return [c for c in combinations(alturas, 4) if {a % 12 for a in c} == cls]


def piano(acordes: list[str], graves: list[int]) -> list[Evento]:
    """Arpejo subindo em colcheias, cada nota segurada até o fim do meio compasso."""
    ev: list[Evento] = []
    anterior = None
    for h in range(MEIOS - 1):
        cands = voicings(acordes[h])
        if anterior is None:
            v = min(cands, key=lambda c: abs(sum(c) / 4 - 60))
        else:
            v = min(cands, key=lambda c: (sum(abs(a - b) for a, b in zip(c, anterior)), c))
        anterior = v
        t, fim = 2 * h, (FIM if h == MEIOS - 2 else 2 * h + 2)
        ev += [(t + k / 2, fim - t - k / 2, alt, vel("Piano", t)) for k, alt in enumerate(v)]
    for ini, fim, (_, pc) in trechos(list(zip(acordes, graves)), por_compasso=True):
        fim = min(fim, FIM)
        grave = next(a for a in range(26, 38) if a % 12 == pc)
        ev += [(ini, fim - ini, grave, vel("Piano", ini)), (ini, fim - ini, grave + 12, vel("Piano", ini))]
    return ev


def violoncelo(graves: list[int]) -> list[Evento]:
    t0, t1 = (ENTRADA["Violoncelo"] - 1) * COMPASSO, (29 - ENTRADA["Violoncelo"]) * COMPASSO
    return [(ini, fim - ini, next(a for a in range(38, 50) if a % 12 == pc), vel("Violoncelo", ini))
            for ini, fim, pc in trechos(graves, por_compasso=True) if t0 <= ini < t1]


def pad(voz: str, acordes: list[str], notas: list[Nota], outra: list[Evento]) -> list[Evento]:
    lo, hi = TESSITURA_DO_PAD[voz]
    t0, t1 = (ENTRADA[voz] - 1) * COMPASSO, (29 - ENTRADA[voz]) * COMPASSO
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


def articular(notas: list[Nota], voz: str) -> list[Evento]:
    """A colcheia do pontuado sai mais leve; nota repetida ganha um respiro para ser ouvida."""
    out = []
    for j, (t, d, alt, _) in enumerate(notas):
        v = vel(voz, t) - (8 if d <= 0.5 else 0)
        seguinte = notas[j + 1] if j + 1 < len(notas) else None
        if seguinte and seguinte[2] == alt and abs(seguinte[0] - t - d) < 1e-9:
            d -= 0.08
        out.append((t, d, alt, v))
    return out


def compor(dig: str):
    notas, k, a, b = melodia(dig)
    acordes = harmonizar(notas)
    graves = baixos(acordes)
    viola = pad("Viola", acordes, notas, [])
    partes = {
        "Violino I": articular([n for n in notas if n[3] == "Violino I"], "Violino I"),
        "Flauta": articular([n for n in notas if n[3] == "Flauta"], "Flauta"),
        "Viola": viola,
        "Violino II": pad("Violino II", acordes, notas, viola),
        "Violoncelo": violoncelo(graves),
        "Piano": piano(acordes, graves),
    }
    return partes, acordes, graves, k, a, b


def escrever_midi(partes, caminho: Path) -> None:
    arq = mido.MidiFile(ticks_per_beat=T_TICKS)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=COMPASSO, denominator=4, time=0))
    meta.append(mido.MetaMessage("key_signature", key="A", time=0))
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
                    "-b:a", "192k", "-metadata", "title=Música do Pi - Lá maior",
                    "-metadata", "artist=Natura", str(midi.with_suffix(".mp3"))], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v7")
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()
    dig = digitos_de_pi(40)
    if not dig.startswith("3141592"):
        raise SystemExit(f"dígitos inesperados: {dig[:10]}")
    partes, acordes, graves, k, a, b = compor(dig)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    midi = saida.with_suffix(".mid")
    escrever_midi(partes, midi)
    compassos = [f"{m + 1}:{acordes[2 * m]}/{acordes[2 * m + 1]}" for m in range(TEMPOS // COMPASSO)]
    Path(f"{saida}-mapeamento.json").write_text(json.dumps({
        "mapeamento": MAPEAMENTO, "digitos": {"A": a, "B": b, "A'": a[::-1]}, "liquidacao_k": k,
        "compasso": f"{COMPASSO}/4", "andamento_bpm": round(60e6 / TEMPO_US, 2),
        "acordes_por_meio_compasso": acordes, "baixo_por_meio_compasso": graves,
        "secoes": {"A": [2, 9], "B": [11, 18], "A'": [20, 27]}, "cc7": CC7,
    }, ensure_ascii=False, indent=1))
    print(f"A = {a} (k={k}), B = {b} + {b[::-1]}, A' = {a[::-1]}")
    print(" ".join(compassos))
    print(f"{midi}: {sum(len(v) for v in partes.values())} notas, melodia "
          f"{len(partes['Violino I']) + len(partes['Flauta'])}")
    if not args.sem_audio:
        gravar_audio(midi)
        print(f"{midi.with_suffix('.mp3')} gravado")


if __name__ == "__main__":
    main()
