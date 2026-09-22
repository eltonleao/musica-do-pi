"""Compõe a Música do Pi: os dígitos viram a linha do violino I, e o resto
(harmonia, vozes internas, baixo, piano) é derivado por regra simples.

Invariante da peça: a sequência de alturas do violino I é a sequência dos
dígitos de pi pelo mapeamento, uma nota (ou pausa) por tempo. Ritmo, harmonia
e orquestração são livres e não entram no oráculo de dígitos.

Uso: python src/compor.py --digitos 128 --saida build/pi-poc
Gera build/pi-poc.mid, build/pi-poc.musicxml e build/pi-poc-harmonia.txt.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi

# --- Mapeamento provisório da PoC (a decisão final é do P2, no vault) ------
# 1 = Lá4 ... 7 = Sol5; 8 e 9 continuam a escala para cima; 0 = pausa.
MAPEAMENTO_POC: dict[str, int | None] = {
    "1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77, "7": 79,
    "8": 81, "9": 83, "0": None,
}

TICKS_POR_SEMINIMA = 480
COMPASSO = 4  # tempos por compasso, 4/4
ANDAMENTO_BPM = 112

# Tessituras práticas (MIDI), usadas pelo conferidor de tessitura e pela
# escolha de oitava das vozes.
TESSITURA = {
    "Violino I": (55, 100),
    "Violino II": (55, 100),
    "Viola": (48, 88),
    "Violoncelo": (36, 76),
    "Piano": (21, 108),
}

# Programas General MIDI.
PROGRAMA = {"Violino I": 40, "Violino II": 40, "Viola": 41, "Violoncelo": 42, "Piano": 0}

# Acordes diatônicos de Lá menor (classes de altura), com o V maior para
# a cadência. Ordem = preferência em caso de empate.
ACORDES: dict[str, tuple[int, int, int]] = {
    "Am": (9, 0, 4),
    "Dm": (2, 5, 9),
    "E": (4, 8, 11),
    "F": (5, 9, 0),
    "C": (0, 4, 7),
    "G": (7, 11, 2),
    "Em": (4, 7, 11),
}


def melodia(digitos: str) -> list[int | None]:
    """Uma altura (ou None = pausa) por dígito."""
    return [MAPEAMENTO_POC[d] for d in digitos]


def compassos_de(notas: list[int | None]) -> list[list[int | None]]:
    return [notas[i:i + COMPASSO] for i in range(0, len(notas), COMPASSO)]


def escolher_acordes(compassos: list[list[int | None]]) -> list[str]:
    """Um acorde por compasso: o que mais casa com as notas do compasso,
    tempos 1 e 3 valendo dobrado, com empurrão para cadência a cada 8 e
    penalidade para repetir o acorde anterior."""
    escolha: list[str] = []
    total = len(compassos)
    for i, compasso in enumerate(compassos):
        melhor, melhor_pontos = "Am", -99.0
        fim_de_frase = (i + 1) % 8 == 0 and i + 1 < total
        ultimo = i + 1 == total
        for nome, classes in ACORDES.items():
            pontos = 0.0
            for t, nota in enumerate(compasso):
                if nota is None:
                    continue
                peso = 2.0 if t in (0, 2) else 1.0
                if nota % 12 in classes:
                    pontos += peso
                elif nome == "E" and nota % 12 == 7:  # sol natural contra sol#
                    pontos -= 1.5
            if escolha and escolha[-1] == nome:
                pontos -= 0.75
            if fim_de_frase and nome == "E":
                pontos += 1.5
            if (i == 0 or ultimo) and nome == "Am":
                pontos += 2.0
            if pontos > melhor_pontos:
                melhor, melhor_pontos = nome, pontos
        escolha.append(melhor)
    escolha[-1] = "Am"  # a peça termina na tônica, sempre
    return escolha


def nota_mais_proxima(classes: tuple[int, ...], anterior: int, faixa: tuple[int, int],
                      evitar: set[int] = frozenset()) -> int:
    """A nota do acorde mais perto da anterior dentro da faixa, evitando
    alturas já ocupadas por outra voz."""
    candidatos = [p for p in range(faixa[0], faixa[1] + 1)
                  if p % 12 in classes and p not in evitar]
    return min(candidatos, key=lambda p: (abs(p - anterior), p))


def perfeito(alto: int, baixo_: int) -> int | None:
    """Classe do intervalo se for perfeito: 0 (oitava/uníssono) ou 7 (quinta)."""
    ic = (alto - baixo_) % 12
    return ic if ic in (0, 7) else None


def paralela(a1: int, a2: int, b1: int, b2: int) -> bool:
    """Duas vozes movem (as duas) e mantêm a mesma quinta ou oitava."""
    if a1 == a2 or b1 == b2:
        return False
    return perfeito(a1, b1) is not None and perfeito(a1, b1) == perfeito(a2, b2)


def escolher_vozes(classes: tuple[int, int, int], vla_ant: int, vn2_ant: int,
                   cello_ant: int, cello: int) -> tuple[int, int]:
    """Par (viola, violino II) que menos se move, sem uníssono, viola abaixo,
    sem quinta nem oitava paralela com o violoncelo nem entre si, e com a
    terça do acorde presente em alguma das três vozes quando possível."""
    cand_vla = [p for p in range(55, 73) if p % 12 in classes]
    cand_vn2 = [p for p in range(62, 82) if p % 12 in classes]
    melhor, melhor_custo = (vla_ant, vn2_ant), 10 ** 9
    for vla in cand_vla:
        for vn2 in cand_vn2:
            if vn2 <= vla:
                continue
            custo = abs(vla - vla_ant) + abs(vn2 - vn2_ant)
            if paralela(vla_ant, vla, cello_ant, cello) or paralela(vn2_ant, vn2, cello_ant, cello) \
                    or paralela(vn2_ant, vn2, vla_ant, vla):
                custo += 100
            if classes[1] not in {vla % 12, vn2 % 12, cello % 12}:
                custo += 6
            if vn2 - vla > 12:
                custo += 4
            if custo < melhor_custo:
                melhor, melhor_custo = (vla, vn2), custo
    return melhor


def baixo(nome: str) -> int:
    """Fundamental do acorde no registro do violoncelo (Mi2 a Sol3)."""
    fundamental = ACORDES[nome][0]
    for p in range(40, 56):
        if p % 12 == fundamental:
            return p
    raise ValueError(nome)


Evento = tuple[int, int, int, int]  # (tick de início, duração em ticks, altura, velocidade)


def compor(digitos: str) -> tuple[dict[str, list[Evento]], list[str]]:
    notas = melodia(digitos)
    compassos = compassos_de(notas)
    acordes = escolher_acordes(compassos)
    n_comp = len(compassos)
    partes: dict[str, list[Evento]] = {k: [] for k in PROGRAMA}
    T = TICKS_POR_SEMINIMA

    # Violino I: um dígito por tempo; a última nota segura o compasso.
    for i, nota in enumerate(notas):
        if nota is None:
            continue
        dur = T
        if i == len(notas) - 1:
            dur = T * COMPASSO
        vel = 84 if i < 32 else (92 if i < 96 else 100)
        partes["Violino I"].append((i * T, dur, nota, vel))

    # Seções: 0-7 melodia e violoncelo; 8-15 entram viola e violino II;
    # 16-23 entra o piano; 24-fim tudo, com o piano em colcheias.
    vn2_ant, vla_ant, cello_ant = 72, 64, 45
    for c, nome in enumerate(acordes):
        inicio = c * COMPASSO * T
        classes = ACORDES[nome]
        secao = min(c // 8, 3)
        ultimo = c == n_comp - 1
        dur_comp = COMPASSO * T

        # Violoncelo: fundamental; semibreve nas seções 0-1, mínimas depois.
        fund = baixo(nome)
        vel = 58 + 8 * secao
        if secao < 2 or ultimo:
            partes["Violoncelo"].append((inicio, dur_comp, fund, vel))
        else:
            partes["Violoncelo"].append((inicio, 2 * T, fund, vel))
            partes["Violoncelo"].append((inicio + 2 * T, 2 * T, fund, vel - 6))

        # Viola e violino II: nota do acorde mais perto da anterior, sem
        # uníssono entre elas, viola abaixo do violino II.
        if secao >= 1:
            vla, vn2 = escolher_vozes(classes, vla_ant, vn2_ant, cello_ant, fund)
            vla_ant, vn2_ant = vla, vn2
            vel = 52 + 8 * secao
            partes["Viola"].append((inicio, dur_comp, vla, vel))
            partes["Violino II"].append((inicio, dur_comp, vn2, vel))

        cello_ant = fund

        # Piano: mão esquerda em oitavas, mão direita em arpejo.
        if secao >= 2:
            vel = 56 + 6 * secao
            partes["Piano"].append((inicio, 2 * T, fund - 12, vel))
            partes["Piano"].append((inicio, 2 * T, fund, vel - 8))
            partes["Piano"].append((inicio + 2 * T, 2 * T, fund - 12, vel - 4))
            partes["Piano"].append((inicio + 2 * T, 2 * T, fund, vel - 12))
            arpejo = [p for p in range(60, 80) if p % 12 in classes][:5]
            padrao = [arpejo[0], arpejo[1], arpejo[2], arpejo[1]] if len(arpejo) >= 3 else arpejo
            passo = T // 2 if secao == 3 else T
            n_notas = dur_comp // passo
            if ultimo:
                partes["Piano"].append((inicio, dur_comp, arpejo[0], vel))
                partes["Piano"].append((inicio, dur_comp, arpejo[1], vel - 6))
                partes["Piano"].append((inicio, dur_comp, arpejo[2], vel - 6))
            else:
                for k in range(n_notas):
                    partes["Piano"].append((inicio + k * passo, passo, padrao[k % len(padrao)], vel - 10))

    return partes, acordes


def escrever_midi(partes: dict[str, list[Evento]], caminho: Path) -> None:
    arq = mido.MidiFile(ticks_per_beat=TICKS_POR_SEMINIMA)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(ANDAMENTO_BPM), time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("key_signature", key="Am", time=0))
    arq.tracks.append(meta)
    for canal, (nome, eventos) in enumerate(partes.items()):
        trilha = mido.MidiTrack()
        trilha.append(mido.MetaMessage("track_name", name=nome, time=0))
        trilha.append(mido.Message("program_change", channel=canal, program=PROGRAMA[nome], time=0))
        # Reverb e chorus leves via controladores GM.
        trilha.append(mido.Message("control_change", channel=canal, control=91, value=70, time=0))
        pontos: list[tuple[int, int, str, int, int]] = []
        for inicio, dur, altura, vel in eventos:
            pontos.append((inicio, 1, "note_on", altura, vel))
            pontos.append((inicio + dur, 0, "note_off", altura, 0))
        pontos.sort()
        cursor = 0
        for tick, _, tipo, altura, vel in pontos:
            trilha.append(mido.Message(tipo, channel=canal, note=altura, velocity=vel, time=tick - cursor))
            cursor = tick
        trilha.append(mido.MetaMessage("end_of_track", time=TICKS_POR_SEMINIMA))
        arq.tracks.append(trilha)
    arq.save(str(caminho))


def escrever_musicxml(partes: dict[str, list[Evento]], acordes: list[str], caminho: Path) -> str | None:
    """MusicXML pela music21, para a partitura do P5 e o oráculo de harmonia
    do P4. Devolve o resumo da conferência de condução de vozes."""
    try:
        from music21 import instrument, key, metadata, meter, note, stream, tempo, voiceLeading
    except ImportError:
        return None
    T = TICKS_POR_SEMINIMA
    partitura = stream.Score()
    partitura.metadata = metadata.Metadata(title="Música do Pi (PoC)", composer="dígitos de pi + regras")
    instrumentos = {
        "Violino I": instrument.Violin(), "Violino II": instrument.Violin(), "Viola": instrument.Viola(),
        "Violoncelo": instrument.Violoncello(), "Piano": instrument.Piano(),
    }
    for nome, eventos in partes.items():
        parte = stream.Part(id=nome)
        parte.partName = nome
        parte.insert(0, instrumentos[nome])
        parte.insert(0, tempo.MetronomeMark(number=ANDAMENTO_BPM))
        parte.insert(0, meter.TimeSignature("4/4"))
        parte.insert(0, key.Key("a"))
        for inicio, dur, altura, vel in eventos:
            n = note.Note(altura)
            n.quarterLength = dur / T
            n.volume.velocity = vel
            parte.insert(inicio / T, n)
        partitura.insert(0, parte)
    partitura.write("musicxml", fp=str(caminho))

    # Conferência de condução de vozes entre as três vozes sustentadas, por
    # transição de compasso: quintas e oitavas paralelas.
    def por_compasso(nome: str) -> dict[int, int]:
        return {inicio // (COMPASSO * T): altura for inicio, _, altura, _ in partes[nome]
                if (inicio % (COMPASSO * T)) == 0}
    vozes = {n: por_compasso(n) for n in ("Violino II", "Viola", "Violoncelo")}
    problemas: list[str] = []
    nomes = list(vozes)
    for a in range(len(nomes)):
        for b in range(a + 1, len(nomes)):
            va, vb = vozes[nomes[a]], vozes[nomes[b]]
            for c in sorted(va):
                if c + 1 in va and c in vb and c + 1 in vb:
                    q = voiceLeading.VoiceLeadingQuartet(note.Note(va[c]), note.Note(va[c + 1]),
                                                         note.Note(vb[c]), note.Note(vb[c + 1]))
                    if q.parallelFifth():
                        problemas.append(f"compasso {c + 1}->{c + 2}: quintas paralelas entre {nomes[a]} e {nomes[b]}")
                    if q.parallelOctave():
                        problemas.append(f"compasso {c + 1}->{c + 2}: oitavas paralelas entre {nomes[a]} e {nomes[b]}")
    linhas = [f"acordes por compasso: {' '.join(acordes)}", f"violações de condução de vozes: {len(problemas)}"]
    linhas += problemas
    return "\n".join(linhas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digitos", type=int, default=128)
    ap.add_argument("--saida", default="build/pi-poc")
    args = ap.parse_args()
    digitos = digitos_de_pi(args.digitos)
    partes, acordes = compor(digitos)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    escrever_midi(partes, saida.with_suffix(".mid"))
    resumo = escrever_musicxml(partes, acordes, saida.with_suffix(".musicxml"))
    if resumo:
        saida.with_name(saida.name + "-harmonia.txt").write_text(resumo + "\n", encoding="utf-8")
    saida.with_name(saida.name + "-mapeamento.json").write_text(
        json.dumps({"mapeamento": MAPEAMENTO_POC, "digitos": args.digitos, "andamento": ANDAMENTO_BPM,
                    "compasso": "4/4", "duracao": "seminima"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"{args.digitos} dígitos, {len(acordes)} compassos, {sum(len(v) for v in partes.values())} notas")
    print(f"acordes: {' '.join(acordes)}")
    if resumo:
        print(resumo.splitlines()[1])


if __name__ == "__main__":
    main()
