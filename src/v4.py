"""Versão 4 - o círculo, consonante. Pi em 3 min 14 s, sem o cânone.

Pedido do dono, 21/09/2026, depois de ouvir a v3 e o "Song from π!" do
aSongScout: a progressão do piano dele é mais bonita, a nossa está tensa demais;
a peça pode ter quantos dígitos quiser, desde que dure 3:14. E o cânone sai:
ficam o palíndromo e a forma circular, e a roda passa para a harmonia.

  melodia     o violino I lê pi em semínimas, um dígito por tempo, 144 dígitos
              até o eixo e o retrógrado deles depois; 288 tempos em 194 s
  harmonia    um acorde por tempo, sempre contendo a nota da melodia, escolhido
              para a primeira metade inteira de uma vez (programação dinâmica):
              trocar no meio do meio compasso custa, descer uma quinta rende.
              A roda é o círculo das quintas: Lá m, Ré m, Sol, Dó, Fá, e Mi, Lá m
  piano       o arpejo do aSongScout: fundamental, 5ª, 8ª, 10ª, 12ª, 15ª, 12ª,
              10ª em semicolcheias, cada nota segurada até a próxima igual ou o
              fim do acorde, que é o pedal escrito à mão
  palíndromo  a primeira metade mais o retrógrado dela, como na v3. O acorde é
              por tempo, e não por meio compasso, porque o retrógrado de dois
              tempos troca os dois de lugar e põe a nota de passagem no tempo
              forte; o espelho de um tempo com o seu acorde é um tempo com o
              mesmo acorde. Nenhuma nota passa do fim do seu acorde, pela mesma
              razão: o espelho transforma o fim de uma nota em ataque
  forma       A violino I e piano; B entra o violoncelo; C entram violino II e
              viola; D a flauta dobra a melodia. Depois o espelho: D' C' B' A'

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

TEMPOS = 288                  # 72 compassos de 4/4
EIXO = TEMPOS / 2
DIGITOS = int(EIXO)           # um dígito por tempo até o eixo
DURACAO_S = 194.0             # 3 min 14 s
TEMPO_US = round(DURACAO_S * 1e6 / TEMPOS)   # 673.611 µs por semínima, ♩ = 89,07
COMPASSO = 4
PASSO_CIFRA = 1               # a grade escreve uma cifra por tempo, onde o acorde muda

# (fundamental, terça): a tríade é fundamental, fundamental + terça e fundamental + 7.
ACORDES = {"Am": (9, 3), "Dm": (2, 3), "G": (7, 4), "C": (0, 4),
           "F": (5, 4), "Em": (4, 3), "E": (4, 4)}
BAIXO = {0: 36, 2: 38, 4: 40, 5: 41, 7: 43, 9: 45, 11: 47}   # a fundamental do piano, Dó2 a Si2
ARPEJO = [0, 7, 12, None, 19, 24, 19, None]                 # None é a terça, uma oitava acima
ACENTO = [6, 0, 0, -2, -3, -4, -3, -2]
SEGURA = [2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]            # o pedal: quanto cada nota pode durar

ENTRADAS = {"Violino I": 0.0, "Piano": 0.0, "Violoncelo": 36.0,
            "Viola": 72.0, "Violino II": 72.0, "Flauta": 108.0}
FAIXA = {"Flauta": (50, 76), "Violino I": (58, 86), "Violino II": (30, 54),
         "Viola": (30, 54), "Violoncelo": (34, 58), "Piano": (46, 70)}
TESSITURA_DO_PAD = {"Viola": (55, 67), "Violino II": (64, 76)}

PAN = {"Flauta": 64, "Violino I": 30, "Violino II": 98,
       "Viola": 46, "Violoncelo": 82, "Piano": 64}

ANDAMENTO = [(0, round(60e6 / TEMPO_US, 2))]
MARCAS = [("A", 0.0, 36.0), ("B", 36.0, 72.0), ("C", 72.0, 108.0), ("D", 108.0, EIXO),
          ("D'", EIXO, TEMPOS - 108), ("C'", TEMPOS - 108, TEMPOS - 72),
          ("B'", TEMPOS - 72, TEMPOS - 36), ("A'", TEMPOS - 36, TEMPOS)]

Evento = tuple[float, float, int, int]   # (início, duração, altura, velocity) em tempos


def velocity(t: float, voz: str = "Violino I") -> int:
    """A sombra do círculo, mais suave que na v3: uma volta de cosseno, de p a mf."""
    lo, hi = FAIXA[voz]
    return round(lo + (hi - lo) * (1 - math.cos(2 * math.pi * t / TEMPOS)) / 2)


DINAMICA = [(ini, velocity(ini)) for _, ini, _ in MARCAS]


def classes_de(nome: str) -> set[int]:
    r, terca = ACORDES[nome]
    return {r, (r + terca) % 12, (r + 7) % 12}


def transicao(b: int, antes: str | None, de: str, para: str) -> float:
    """O ganho de trocar `de` -> `para` no tempo b. O ritmo harmônico do aSongScout
    é o meio compasso; aqui a troca no tempo fraco só acontece quando a melodia obriga."""
    ganho = {0: 0.5, 2: -0.5}.get(b % 4, -4.0)
    if (ACORDES[para][0] - ACORDES[de][0]) % 12 == 5:
        ganho += 2.0                                  # a roda: descer uma quinta
    if para == antes:
        ganho -= 1.5                                  # vai e volta (Ré m, Sol, Ré m) não é roda
    if de == "E":
        ganho += 0.5 if para == "Am" else -1.0        # a dominante resolve na tônica
    if {de, para} == {"E", "Em"}:
        ganho -= 3.0
    return ganho


def harmonizar(classes: list[int | None]) -> list[str]:
    """Um acorde por tempo que contém a nota da melodia, com a maior soma de ganhos.
    O estado é o acorde anterior, o acorde e há quantos tempos ele soa (até 4):
    ficar parado mais que um compasso custa um pouco, para a roda não emperrar."""
    melhor = {(None, "Am", 1): (0.0, ["Am"])}
    for b in range(1, len(classes)):
        pc, novo = classes[b], {}
        for (antes, ant, dur), (pontos, caminho) in melhor.items():
            for c in ACORDES:
                if pc is not None and pc not in classes_de(c):
                    continue
                if c == ant:
                    chave, ganho = (antes, c, min(dur + 1, 4)), (-0.5 if b % 2 == 0 and dur >= 4 else 0.0)
                else:
                    chave, ganho = (ant, c, 1), transicao(b, antes, ant, c)
                if chave not in novo or pontos + ganho > novo[chave][0]:
                    novo[chave] = (pontos + ganho, caminho + [c])
        melhor = novo
    return max(melhor.values())[1]


def juntar(nomes: list[str]) -> list[tuple[float, float, str]]:
    """Acordes por tempo -> trechos (início, fim, acorde) sem repetição."""
    trechos = []
    for b, nome in enumerate(nomes):
        if trechos and trechos[-1][2] == nome:
            trechos[-1] = (trechos[-1][0], b + 1.0, nome)
        else:
            trechos.append((float(b), b + 1.0, nome))
    return trechos


def melodia(digitos: str, voz: str) -> list[Evento]:
    return [(float(b), 1.0, MAPEAMENTO[d], velocity(b, voz)) for b, d in enumerate(digitos)
            if MAPEAMENTO[d] is not None and ENTRADAS[voz] <= b < EIXO]


def piano(trechos) -> list[Evento]:
    eventos = []
    for ini, fim, nome in trechos:
        r, terca = ACORDES[nome]
        ataques = [(ini + k * 0.25, BAIXO[r] + (terca + 12 if ARPEJO[k % 8] is None else ARPEJO[k % 8]), k % 8)
                   for k in range(round((fim - ini) * 4))]
        for j, (t, altura, i) in enumerate(ataques):
            proxima = next((t2 for t2, a2, _ in ataques[j + 1:] if a2 == altura), fim)
            eventos.append((t, min(proxima, fim, t + SEGURA[i]) - t, altura,
                            velocity(t, "Piano") + ACENTO[i]))
    return eventos


def sustentar(trechos, voz: str, escolher) -> list[Evento]:
    """Uma nota longa por trecho, a partir da entrada da voz; nota comum com o
    trecho anterior não é reatacada."""
    eventos, antes = [], None
    for ini, fim, nome in trechos:
        ini = max(ini, ENTRADAS[voz])
        if ini >= fim:
            continue
        altura = escolher(ini, nome, antes)
        if eventos and eventos[-1][2] == altura and eventos[-1][0] + eventos[-1][1] == ini:
            eventos[-1] = (eventos[-1][0], fim - eventos[-1][0], altura, eventos[-1][3])
        else:
            eventos.append((ini, fim - ini, altura, velocity(ini, voz)))
        antes = altura
    return eventos


def mais_perto(voz: str, inicial: int, evita=None):
    lo, hi = TESSITURA_DO_PAD[voz]

    def escolher(t, nome, antes):
        alvo = inicial if antes is None else antes
        tirar = evita(t) if evita else None
        notas = [a for a in range(lo, hi + 1) if a % 12 in classes_de(nome)]
        return min(notas, key=lambda a: (tirar is not None and a % 12 == tirar % 12, abs(a - alvo), a))
    return escolher


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
    digitos = digitos[:DIGITOS]
    nomes = harmonizar([None if MAPEAMENTO[d] is None else MAPEAMENTO[d] % 12 for d in digitos])
    trechos = juntar(nomes)
    raiz = {nome: ACORDES[nome][0] for nome in ACORDES}
    violoncelo = lambda t, nome, antes: BAIXO[raiz[nome]] + (12 if BAIXO[raiz[nome]] < 43 else 0)
    viola = sustentar(trechos, "Viola", mais_perto("Viola", 60))
    na_viola = lambda t: next(a for i, d, a, _ in viola if i <= t < i + d)
    partes = {
        "Violino I": melodia(digitos, "Violino I"),
        "Flauta": melodia(digitos, "Flauta"),
        "Piano": piano(trechos),
        "Violoncelo": sustentar(trechos, "Violoncelo", violoncelo),
        "Viola": viola,
        "Violino II": sustentar(trechos, "Violino II", mais_perto("Violino II", 69, na_viola)),
    }
    partes = {nome: espelhar(ev) for nome, ev in partes.items()}
    acordes = nomes + nomes[::-1]    # um por tempo, a peça inteira
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
    """MIDI -> WAV com a cauda do sintetizador -> corte em 194 s com fade de 0,3 s -> MP3."""
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
                    "-b:a", "192k", "-metadata", "title=Música do Pi - o círculo, consonante",
                    "-metadata", "artist=Natura", str(midi.with_suffix(".mp3"))], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v4")
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
         "andamento": ANDAMENTO, "formacao": ORDEM, "acordes_por_tempo": acordes[:DIGITOS],
         "secoes": [{"letra": l, "inicio": i, "fim": f} for l, i, f in marcas]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.sem_audio:
        gravar_audio(midi)

    trocas = sum(a != b for a, b in zip(acordes[:DIGITOS], acordes[1:DIGITOS]))
    print(f"{DIGITOS} dígitos até o eixo, {tempos // COMPASSO} compassos de {COMPASSO}/4, "
          f"{tempos} tempos a {ANDAMENTO[0][1]} bpm = {tempos * TEMPO_US / 1e6:.3f} s; "
          f"{trocas} trocas de acorde na primeira metade")
    for nome in ORDEM:
        print(f"  {nome:<12} {len(partes[nome]):4d} notas")


if __name__ == "__main__":
    main()
