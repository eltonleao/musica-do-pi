"""v8 - Ré menor, devagar, e cada nota da melodia é um dígito de pi, sem nota inserida.

Parte da v7 (Lá maior), que fica intacta. Duas mudanças a pedido do dono: o tom vira Ré menor
harmônico, com o mesmo grau para cada dígito (0 e 7 são a sensível, Dó♯), e o motivo deixa de
repetir o primeiro dígito ("a sequencia de notas está exatamente correspondente com pi? nao
parece"). O ritmo do motivo não muda - ♩. ♪ ♩ ♩ | 𝅗𝅥. 𝄽 -, mas agora lê cinco dígitos, um por nota.

Sentença de 8 compassos: ideia (5 dígitos), ideia com os 5 seguintes, dois fragmentos de um
compasso com a cabeça ♩. ♪ 𝅗𝅥 (3 dígitos cada), a liquidação de k dígitos e a nota longa da
cadência, 17 + k dígitos no total. k é escolhido para a cadência cair no acorde de Ré menor.

Forma palíndroma, em compassos: 1 introdução, 2-9 A (violino I), 10 transição, 11-18 B (a cabeça
na flauta, 12 dígitos e o retrógrado deles, eixo no compasso 15), 19 retransição em Lá7, 20-27 A'
(os dígitos de A de trás para a frente, no mesmo ritmo), 28 acorde final. Até o eixo a melodia é
pi em ordem; depois do eixo, pi espelhado. main() confere as duas coisas e aborta se falharem.

Uso: python src/v8.py [--saida build/v8] [--sem-audio]
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

MAPEAMENTO = {"0": 73, "1": 74, "2": 76, "3": 77, "4": 79, "5": 81, "6": 82,
              "7": 85, "8": 86, "9": 88}
SENSIVEL = 1                  # Dó♯: só cabe em Lá e Lá7

IDEIA = [(0, 1.5, 0), (1.5, .5, 1), (2, 1, 2), (3, 1, 3), (4, 3, 4)]    # início, duração, dígito
CABECA = [(0, 1.5, 0), (1.5, .5, 1), (2, 2, 2)]
LIQUIDACAO = {2: [(0, 2), (2, 2)], 3: [(0, 1), (1, 1), (2, 2)],
              4: [(0, 1), (1, 1), (2, 1), (3, 1)], 5: [(0, 1), (1, 1), (2, 1), (3, .5), (3.5, .5)]}
TONICA = {"1", "3", "5", "8"}  # Ré, Fá, Lá, Ré

ACORDES = {                   # nome -> (fundamental, classes)
    "Dm": (2, {2, 5, 9}), "Gm": (7, {7, 10, 2}), "A": (9, {9, 1, 4}), "A7": (9, {9, 1, 4, 7}),
    "Bb": (10, {10, 2, 5}), "F": (5, {5, 9, 0}), "C": (0, {0, 4, 7}),
}
PESO = {"Dm": 0.0, "Gm": 0.15, "A": 0.15, "A7": 0.3, "Bb": 0.3, "F": 0.3, "C": 0.5}
DOMINANTE = {"A", "A7"}
BOAS = {("Dm", "Gm"), ("Dm", "A"), ("Dm", "Bb"), ("Dm", "F"), ("Dm", "C"), ("Gm", "A"), ("Gm", "A7"),
        ("Gm", "Dm"), ("Gm", "C"), ("Bb", "Gm"), ("Bb", "A"), ("Bb", "F"), ("Bb", "C"), ("F", "Bb"),
        ("F", "Gm"), ("F", "C"), ("C", "F"), ("C", "Dm"), ("A", "Dm"), ("A7", "Dm"), ("A", "A7"),
        ("A", "Bb"), ("A7", "Bb")}
FIXOS = {0: ["Dm"], 1: ["Dm"], 16: ["Dm"], 36: ["A7"], 37: ["A7"], 38: ["Dm"],
         52: ["Dm"], 53: ["Dm"], 54: ["Dm"], 55: ["Dm"]}
PEDAL = range(32, 38)         # compassos 17-19, baixo em Lá

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
    """Quantos dígitos a liquidação lê: a cadência no acorde de Ré menor, de preferência na fundamental."""
    return min(LIQUIDACAO, key=lambda k: (dig[16 + k] not in TONICA,
                                          abs(k - 4) + (0 if dig[16 + k] in "18" else .5)))


def sentenca(dig: str, t0: float, k: int, final: float) -> list[tuple[float, float, str]]:
    """Ideia, ideia, cabeça, cabeça, liquidação de k dígitos e a nota da cadência: 17 + k dígitos."""
    out: list[tuple[float, float, str]] = []
    for base, forma, pedaco in ((0, IDEIA, dig[0:5]), (8, IDEIA, dig[5:10]),
                                (16, CABECA, dig[10:13]), (20, CABECA, dig[13:16])):
        out += [(t0 + base + p, d, pedaco[j]) for p, d, j in forma]
    out += [(t0 + 24 + p, d, c) for (p, d), c in zip(LIQUIDACAO[k], dig[16:16 + k])]
    out.append((t0 + 28, final, dig[16 + k]))
    return out


def melodia(dig: str) -> tuple[list[Nota], int, str, str]:
    k = escolher_k(dig)
    a = dig[:17 + k]
    b = dig[17 + k:29 + k]
    notas = [(t, d, c, "Violino I") for t, d, c in sentenca(a, 4, k, 3)]
    ida_e_volta = b + b[::-1]
    for j in range(8):
        notas += [(40 + 4 * j + p, d, ida_e_volta[3 * j + i], "Flauta") for p, d, i in CABECA]
    notas += [(t, d, c, "Violino I") for t, d, c in sentenca(a[::-1], 76, k, FIM - 104)]
    return [(t, d, MAPEAMENTO[c], voz) for t, d, c, voz in notas], k, a, b


def conferir_pi(notas: list[Nota], dig: str) -> str:
    """A melodia, lida em ordem de tempo, é pi até o eixo e o espelho dele depois."""
    digito = {alt: c for c, alt in MAPEAMENTO.items()}
    lida = "".join(digito[alt] for _, _, alt, _ in sorted(notas))
    ida = lida[:len(lida) // 2]
    if ida != dig[:len(ida)] or lida != lida[::-1]:
        raise SystemExit(f"a melodia não é pi espelhado:\n  lida {lida}\n  pi   {dig[:len(ida)]}")
    return lida


def harmonizar(notas: list[Nota]) -> list[str]:
    def soando(h: int) -> list[tuple[float, float, int]]:
        return [(t, d, alt % 12) for t, d, alt, _ in notas if t < 2 * h + 2 and t + d > 2 * h]

    def permitidos(h: int) -> list[str]:
        if h in FIXOS:
            return FIXOS[h]
        if h in PEDAL:
            return ["A", "A7", "Dm", "Gm"]
        return list(ACORDES)

    def cabe(h: int, nome: str) -> bool:
        """A nota que soa no início do meio compasso é do acorde, e todo Dó♯ de semínima também."""
        cls = ACORDES[nome][1]
        return all(pc in cls or not (t <= 2 * h < t + d or (pc == SENSIVEL and d >= 1))
                   for t, d, pc in soando(h))

    def encaixe(h: int, nome: str) -> float:
        cls = ACORDES[nome][1]
        return PESO[nome] + sum(0.4 * d for t, d, pc in soando(h)
                                if pc not in cls and t >= 2 * h and t == int(t))

    def troca(a: str, b: str) -> float:
        if a in DOMINANTE and b not in DOMINANTE and b not in ("Dm", "Bb"):
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
    return [9 if h in PEDAL else ACORDES[nome][0] for h, nome in enumerate(acordes)]


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
    lida = conferir_pi(notas, dig)
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
    return partes, acordes, graves, k, a, b, lida


def escrever_midi(partes, caminho: Path) -> None:
    arq = mido.MidiFile(ticks_per_beat=T_TICKS)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=COMPASSO, denominator=4, time=0))
    meta.append(mido.MetaMessage("key_signature", key="Dm", time=0))
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
                    "-b:a", "192k", "-metadata", "title=Música do Pi - Ré menor",
                    "-metadata", "artist=Natura", str(midi.with_suffix(".mp3"))], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v8")
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()
    dig = digitos_de_pi(50)
    if not dig.startswith("3141592"):
        raise SystemExit(f"dígitos inesperados: {dig[:10]}")
    partes, acordes, graves, k, a, b, lida = compor(dig)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    midi = saida.with_suffix(".mid")
    escrever_midi(partes, midi)
    compassos = [f"{m + 1}:{acordes[2 * m]}/{acordes[2 * m + 1]}" for m in range(TEMPOS // COMPASSO)]
    Path(f"{saida}-mapeamento.json").write_text(json.dumps({
        "mapeamento": MAPEAMENTO, "digitos": {"A": a, "B": b, "A'": a[::-1]}, "liquidacao_k": k,
        "melodia_lida": lida, "compasso": f"{COMPASSO}/4", "andamento_bpm": round(60e6 / TEMPO_US, 2),
        "acordes_por_meio_compasso": acordes, "baixo_por_meio_compasso": graves,
        "secoes": {"A": [2, 9], "B": [11, 18], "A'": [20, 27]}, "cc7": CC7,
    }, ensure_ascii=False, indent=1))
    print(f"melodia lida: {lida}")
    print(f"pi          : {dig[:len(lida) // 2]}")
    print(" ".join(compassos))
    print(f"{midi}: {sum(len(v) for v in partes.values())} notas, melodia "
          f"{len(partes['Violino I']) + len(partes['Flauta'])}")
    if not args.sem_audio:
        gravar_audio(midi)
        print(f"{midi.with_suffix('.mp3')} gravado")


if __name__ == "__main__":
    main()
