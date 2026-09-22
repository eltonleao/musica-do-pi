"""Versão 5 - a harmonia revista. Pi em 1 min 41 s, em Lá menor harmônico.

Pedido do dono, 21/09/2026, depois de ouvir a v4: "não tô achando muito
harmoniosas as notas, vamos revisar toda a harmonia. estude Villa-Lobos"; "pode
ser 1:41"; e a análise do "Song from π!" do aSongScout. Decisões dele: o
mapeamento do aSongScout (7 e 0 = Sol#) e o espelho só na melodia.

  melodia     o violino I lê 68 dígitos de pi em semínimas a partir do compasso 3;
              o 68º segura o eixo por dois tempos, e depois vem o retrógrado.
              Mapeamento do aSongScout: 0 = Sol#4, 1 a 6 = Lá4 a Fá5, 7 = Sol#5,
              8 e 9 = Lá5 e Si5
  harmonia    um acorde por meio compasso, escolhido para a peça inteira de uma
              vez (programação dinâmica), sempre para a frente, também na volta
              da melodia. Troca de preferência na barra do compasso; descer uma
              quinta rende; a dominante (Mi, Mi7, Sol#°7) só vai para Lá ou Fá.
              A nota da melodia pode ficar fora do acorde, como no aSongScout,
              menos um semitom acima de uma nota dele (a nona menor que arranha)
  vocabulário Lá m, Lá m7, Lá m(9), Ré m, Ré m7, Ré m9, Fá, Fá7M, Dó, Dó7M, Sol,
              Mi, Mi7, Si ø7 e Sol#°7: as sétimas e nonas de Villa-Lobos
              (pesquisas/villa-lobos-harmonia, achado [5]), o VII modal [8]
  piano       o arpejo do aSongScout em semicolcheias, no registro do tenor, para
              ficar sempre abaixo da melodia
  violoncelo  pizzicato, fundamental no tempo 1 e quinta no 3, como o violão
              que os violoncelos imitam na Bachianas nº 5 [4]
  forma       I piano; A entra o violino I; B o violoncelo; C a viola e o
              violino II; D a flauta dobra a melodia uma oitava acima. Depois as
              vozes saem na ordem inversa, e a peça termina como começou: piano
              sozinho, Mi7 e Lá m
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi
from v2 import ORDEM, PROGRAMA, T_TICKS

TEMPOS = 152                  # 38 compassos de 4/4
EIXO = TEMPOS // 2
ENTRA = 8                     # a melodia entra no compasso 3
SAI = TEMPOS - ENTRA          # e termina dois compassos antes do fim
DIGITOS = EIXO - ENTRA        # 68: 67 até o eixo e o que segura o eixo
DURACAO_S = 101.0             # 1 min 41 s
TEMPO_US = round(DURACAO_S * 1e6 / TEMPOS)   # 664.474 µs por semínima, ♩ = 90,3
COMPASSO = 4
MEIOS = TEMPOS // 2           # a janela da harmonia é o meio compasso

MAPEAMENTO = {"0": 68, "1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77,
              "7": 80, "8": 81, "9": 83}

# O arpejo de cada tipo de acorde em oito semicolcheias, em semitons acima da
# fundamental. O mais agudo fica em +19 (ou +26 no Ré m9, que começa em Ré2),
# abaixo do Sol#4 da melodia. Onde o acorde tem um semitom dentro dele (Fá-Mi,
# Dó-Si), a nota de baixo do semitom vai por cima, para virar sétima maior.
ARPEJOS = {"m": [0, 7, 12, 15, 19, 15, 12, 7], "": [0, 7, 12, 16, 19, 16, 12, 7],
           "m7": [0, 7, 10, 15, 19, 15, 10, 7], "7": [0, 7, 10, 16, 19, 16, 10, 7],
           "maj7": [0, 7, 11, 16, 19, 16, 11, 7], "madd9": [0, 3, 7, 14, 19, 14, 7, 3],
           "m9": [0, 7, 15, 22, 26, 22, 15, 7], "m7b5": [0, 6, 10, 15, 18, 15, 10, 6],
           "dim7": [0, 6, 9, 15, 18, 15, 9, 6]}
ACORDES = {"Am": (9, "m"), "Am7": (9, "m7"), "Am(9)": (9, "madd9"),
           "Dm": (2, "m"), "Dm7": (2, "m7"), "Dm9": (2, "m9"),
           "F": (5, ""), "F7M": (5, "maj7"), "C": (0, ""), "C7M": (0, "maj7"),
           "G": (7, ""), "E": (4, ""), "E7": (4, "7"), "Bø7": (11, "m7b5"),
           "G#°7": (8, "dim7")}
BAIXO = {2: 38, 4: 40, 5: 41, 7: 43, 8: 44, 9: 45, 11: 47, 0: 48}   # Ré2 a Dó3
PREFERENCIA = {"Am": 0.3, "Dm": 0.2, "F": 0.2, "C": 0.1, "E": 0.0, "E7": 0.2,
               "Am7": -0.3, "Am(9)": -0.2, "Dm7": 0.0, "Dm9": -0.3, "F7M": 0.0,
               "C7M": -0.4, "G": -0.4, "Bø7": -0.2, "G#°7": -0.4}
FIXOS = {0: "Am", 1: "Am", 72: "E7", 73: "E7", 74: "Am", 75: "Am"}

ACENTO = [6, 0, 0, -2, -3, -4, -3, -2]
SEGURA = [2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]            # o pedal escrito à mão

# Entrada e saída de cada voz, em tempos: quem entra por último sai primeiro.
PRESENCA = {"Piano": (0, TEMPOS), "Violino I": (ENTRA, SAI), "Violoncelo": (40, 112),
            "Viola": (56, 96), "Violino II": (56, 96), "Flauta": (64, 88)}
FAIXA = {"Flauta": (50, 74), "Violino I": (60, 88), "Violino II": (34, 56),
         "Viola": (34, 56), "Violoncelo": (50, 72), "Piano": (48, 70)}
TESSITURA_DO_PAD = {"Viola": (53, 62), "Violino II": (60, 67)}
PROGRAMA_V5 = {**PROGRAMA, "Violoncelo": 45}                 # pizzicato

PAN = {"Flauta": 64, "Violino I": 30, "Violino II": 98,
       "Viola": 46, "Violoncelo": 82, "Piano": 64}

ANDAMENTO = [(0, round(60e6 / TEMPO_US, 2))]
MARCAS = [("I", 0, 8), ("A", 8, 40), ("B", 40, 56), ("C", 56, 64), ("D", 64, 88),
          ("C'", 88, 96), ("B'", 96, 112), ("A'", 112, 144), ("I'", 144, 152)]

Evento = tuple[float, float, int, int]   # (início, duração, altura, velocity) em tempos


def velocity(t: float, voz: str) -> int:
    """Uma volta de cosseno, de p no começo e no fim a mf no eixo."""
    lo, hi = FAIXA[voz]
    return round(lo + (hi - lo) * (1 - math.cos(2 * math.pi * t / TEMPOS)) / 2)


def classes_de(nome: str) -> set[int]:
    r, tipo = ACORDES[nome]
    return {(r + i) % 12 for i in ARPEJOS[tipo]}


def alturas_do_piano(nome: str) -> set[int]:
    r, tipo = ACORDES[nome]
    return {BAIXO[r] + i for i in ARPEJOS[tipo]}


def dominante(nome: str) -> bool:
    return {8, 11} <= classes_de(nome)


def limpo(alturas) -> bool:
    """Nenhuma nota um semitom (ou uma nona menor) acima de outra."""
    return not any((b - a) % 12 == 1 for a in alturas for b in alturas if b > a)


def nota(digitos: str, b: int) -> int | None:
    """A altura do violino I no tempo b: a ida, o eixo (dois tempos) e a volta."""
    if b < ENTRA or b >= SAI:
        return None
    if b < EIXO - 1:
        i = b - ENTRA
    elif b <= EIXO:
        i = DIGITOS - 1
    else:
        i = SAI - 1 - b
    return MAPEAMENTO[digitos[i]]


def encaixe(digitos: str, h: int, nome: str) -> float | None:
    """O quanto o acorde serve à melodia no meio compasso h; None se arranha."""
    cls = classes_de(nome)
    forte, fraco = nota(digitos, 2 * h), nota(digitos, 2 * h + 1)
    ganho = PREFERENCIA[nome]
    for altura, peso_dentro, peso_fora in ((forte, 2.0, -0.5), (fraco, 0.5, 0.0)):
        if altura is None:
            continue
        if (altura - 1) % 12 in cls:
            return None
        ganho += peso_dentro if altura % 12 in cls else peso_fora
    vizinhas = {nota(digitos, b) for b in (2 * h - 1, 2 * h + 2)} - {None}
    if 7 in cls and any(a % 12 == 8 for a in vizinhas):
        ganho -= 1.0                                   # Sol natural encostado no Sol# da melodia
    return ganho


def troca(h: int, antes: str | None, de: str, para: str) -> float | None:
    """O ganho de trocar `de` -> `para` no começo do meio compasso h."""
    if dominante(de) and not dominante(para) and ACORDES[para][0] not in (9, 5):
        return None                                    # a dominante resolve em Lá ou Fá
    ganho = -1.5                                       # toda troca custa: ritmo harmônico lento
    if h % 2 == 1:
        ganho -= 2.5                                   # no meio do compasso, só se valer muito
    r, s = ACORDES[de][0], ACORDES[para][0]
    if (s - r) % 12 == 5:
        ganho += 1.5                                   # a roda: descer uma quinta
    if r == s:
        ganho -= 1.0                                   # só trocar de cor não é progressão
    if para == antes:
        ganho -= 1.0                                   # vai e volta não é roda
    if dominante(de) and s == 9:
        ganho += 0.5                                   # a cadência
    return ganho


def harmonizar(digitos: str) -> list[str]:
    """Um acorde por meio compasso, com a maior soma de ganhos. O estado é o
    acorde anterior, o acorde e há quantos meios compassos ele soa (até 4)."""
    melhor = {(None, "Am", 1): (0.0, ["Am"])}
    for h in range(1, MEIOS):
        opcoes = [FIXOS[h]] if h in FIXOS else list(ACORDES)
        novo = {}
        for (antes, ant, dur), (pontos, caminho) in melhor.items():
            for c in opcoes:
                g = encaixe(digitos, h, c)
                if g is None:
                    continue
                if c == ant:
                    chave, t = (antes, c, min(dur + 1, 4)), (-2.0 if dur >= 4 else 0.0)
                else:
                    t = troca(h, antes, ant, c)
                    if t is None:
                        continue
                    chave = (ant, c, 1)
                if chave not in novo or pontos + g + t > novo[chave][0]:
                    novo[chave] = (pontos + g + t, caminho + [c])
        melhor = novo
    return max(melhor.values())[1]


def juntar(nomes: list[str]) -> list[tuple[float, float, str]]:
    """Acordes por meio compasso -> trechos (início, fim, acorde), em tempos."""
    trechos = []
    for h, nome in enumerate(nomes):
        if trechos and trechos[-1][2] == nome:
            trechos[-1] = (trechos[-1][0], 2.0 * h + 2, nome)
        else:
            trechos.append((2.0 * h, 2.0 * h + 2, nome))
    return trechos


def recortar(trechos, voz: str):
    a, b = PRESENCA[voz]
    return [(max(i, a), min(f, b), n) for i, f, n in trechos if min(f, b) > max(i, a)]


def melodia(digitos: str, voz: str, oitava: int = 0) -> list[Evento]:
    a, b = PRESENCA[voz]
    return [(float(t), 2.0 if t == EIXO - 1 else 1.0, nota(digitos, t) + oitava, velocity(t, voz))
            for t in range(a, b) if t != EIXO and nota(digitos, t) is not None]


def piano(trechos) -> list[Evento]:
    eventos = []
    for ini, fim, nome in trechos:
        r, tipo = ACORDES[nome]
        final = fim == TEMPOS
        if final:                                      # o último acorde, arpejado e segurado
            fim_arpejo = fim - 4
            rolado = sorted(alturas_do_piano(nome) | {BAIXO[r] + 24})
            eventos += [(fim - 4 + k * 0.25, 4 - k * 0.25, a, velocity(fim - 4, "Piano") + 4 - k)
                        for k, a in enumerate(rolado)]
            if fim_arpejo <= ini:
                continue
            fim = fim_arpejo
        ataques = [(ini + k * 0.25, BAIXO[r] + ARPEJOS[tipo][k % 8], k % 8)
                   for k in range(round((fim - ini) * 4))]
        for j, (t, altura, i) in enumerate(ataques):
            proxima = next((t2 for t2, a2, _ in ataques[j + 1:] if a2 == altura), fim)
            eventos.append((t, min(proxima, fim, t + SEGURA[i]) - t, altura,
                            velocity(t, "Piano") + ACENTO[i]))
    return sorted(eventos)


def violoncelo(nomes: list[str]) -> list[Evento]:
    """Pizzicato: a fundamental no tempo 1; no tempo 3, a quinta, ou a fundamental
    do acorde novo quando ele entra no meio do compasso."""
    a, b = PRESENCA["Violoncelo"]
    eventos = []
    for h in range(a // 2, b // 2):
        nome = nomes[h]
        r, tipo = ACORDES[nome]
        novo = h % 2 == 0 or nomes[h - 1] != nome
        quinta = 6 if 6 in ARPEJOS[tipo] else 7
        altura = BAIXO[r] + (0 if novo else quinta)
        eventos.append((2.0 * h, 1.0, altura, velocity(2 * h, "Violoncelo") + (4 if h % 2 == 0 else 0)))
    return eventos


def pad(trechos, digitos: str, voz: str, inicial: int, outra: list[Evento] | None = None) -> list[Evento]:
    """Uma nota longa por trecho: a nota do acorde mais perto da anterior que não
    faz semitom com o piano, com a melodia nem com a outra voz do pad."""
    lo, hi = TESSITURA_DO_PAD[voz]
    eventos, antes = [], inicial
    for ini, fim, nome in recortar(trechos, voz):
        em_volta = alturas_do_piano(nome) | {nota(digitos, b) for b in range(int(ini), int(fim))} - {None}
        if outra:
            em_volta |= {x for i, d, x, _ in outra if i < fim and i + d > ini}
        candidatas = [x for x in range(lo, hi + 1) if x % 12 in classes_de(nome)
                      and all(limpo({x, y}) for y in em_volta)]
        altura = min(candidatas, key=lambda x: (abs(x - antes), x))
        if eventos and eventos[-1][2] == altura and eventos[-1][0] + eventos[-1][1] == ini:
            eventos[-1] = (eventos[-1][0], fim - eventos[-1][0], altura, eventos[-1][3])
        else:
            eventos.append((ini, fim - ini, altura, velocity(ini, voz)))
        antes = altura
    return eventos


def compor(digitos: str):
    nomes = harmonizar(digitos)
    trechos = juntar(nomes)
    viola = pad(trechos, digitos, "Viola", 57)
    partes = {
        "Violino I": melodia(digitos, "Violino I"),
        "Flauta": melodia(digitos, "Flauta", 12),
        "Piano": piano(trechos),
        "Violoncelo": violoncelo(nomes),
        "Viola": viola,
        "Violino II": pad(trechos, digitos, "Violino II", 64, viola),
    }
    return partes, nomes


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
        trilha.append(mido.Message("program_change", channel=canal, program=PROGRAMA_V5[nome], time=0))
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
                    "-b:a", "192k", "-metadata", "title=Música do Pi - a harmonia revista",
                    "-metadata", "artist=Natura", str(midi.with_suffix(".mp3"))], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v5")
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()

    digitos = digitos_de_pi(DIGITOS)
    partes, nomes = compor(digitos)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    midi = saida.with_suffix(".mid")
    escrever_midi(partes, midi)
    saida.with_name(saida.name + "-mapeamento.json").write_text(json.dumps(
        {"mapeamento": MAPEAMENTO, "digitos": DIGITOS, "compasso": f"{COMPASSO}/4",
         "andamento": ANDAMENTO, "formacao": ORDEM,
         "acordes_por_tempo": [n for n in nomes for _ in range(2)],
         "secoes": [{"letra": l, "inicio": i, "fim": f} for l, i, f in MARCAS]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.sem_audio:
        gravar_audio(midi)

    trocas = sum(a != b for a, b in zip(nomes, nomes[1:]))
    print(f"{DIGITOS} dígitos até o eixo, {TEMPOS // COMPASSO} compassos de {COMPASSO}/4, "
          f"{TEMPOS} tempos a {ANDAMENTO[0][1]} bpm = {TEMPOS * TEMPO_US / 1e6:.3f} s; "
          f"{trocas} trocas de acorde em {MEIOS} meios compassos")
    for c in range(0, MEIOS, 8):
        print("  " + " | ".join(f"{nomes[h]:<5}{nomes[h + 1]:<5}" for h in range(c, min(c + 8, MEIOS), 2)))
    for nome in ORDEM:
        print(f"  {nome:<12} {len(partes[nome]):4d} notas")


if __name__ == "__main__":
    main()
