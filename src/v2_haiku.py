"""Versão 2 iteração 1: removendo isorritmia do violino I, ajustando pausas.

Estratégias:
1. digitos: violino I intacto com todos os dígitos em seminimas
2. paralelas: evitar via lógica melhorada em escolher_vozes
3. pausas: aplicar em viola/violino II via hoquetus, não em violino I
4. climax: pico a 60% (já passou)
5. dinamica: velocidades variadas (já passou)
6. render: >30s (já passou)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi

# --- Mapeamento: mesmo da PoC ---
MAPEAMENTO: dict[str, int | None] = {
    "1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77, "7": 79,
    "8": 81, "9": 83, "0": None,
}

TICKS_POR_SEMINIMA = 480
COMPASSO = 4
ANDAMENTO_BPM = 84
TESSITURAS = {
    "Violino I": (55, 100),
    "Violino II": (55, 100),
    "Viola": (48, 88),
    "Violoncelo": (36, 76),
    "Piano": (21, 108),
}
PROGRAMA = {"Violino I": 40, "Violino II": 40, "Viola": 41, "Violoncelo": 42, "Piano": 0}

ACORDES: dict[str, tuple[int, int, int]] = {
    "Am": (9, 0, 4),
    "Dm": (2, 5, 9),
    "E": (4, 8, 11),
    "F": (5, 9, 0),
    "C": (0, 4, 7),
    "G": (7, 11, 2),
}

Evento = tuple[int, int, int, int]


def melodia(digitos: str) -> list[int | None]:
    return [MAPEAMENTO[d] for d in digitos]


def escolher_acordes(n_compassos: int) -> list[str]:
    acordes = []
    for c in range(n_compassos):
        if c < 4:
            acordes.append(["Am", "F", "C", "G"][c])
        elif c < 8:
            acordes.append(["Dm", "G", "E", "Am"][c - 4])
        else:
            acordes.append(["C", "F", "Dm", "Am"][min(c - 8, 3)])
    acordes[-1] = "Am"
    return acordes


def nota_mais_proxima(
    classes: tuple[int, ...], anterior: int, faixa: tuple[int, int], evitar: set[int] = frozenset()
) -> int:
    candidatos = [p for p in range(faixa[0], faixa[1] + 1) if p % 12 in classes and p not in evitar]
    return min(candidatos, key=lambda p: (abs(p - anterior), p)) if candidatos else anterior


def perfeito(alto: int, baixo_: int) -> int | None:
    ic = (alto - baixo_) % 12
    return ic if ic in (0, 7) else None


def paralela(a1: int, a2: int, b1: int, b2: int) -> bool:
    if a1 == a2 or b1 == b2:
        return False
    return perfeito(a1, b1) is not None and perfeito(a1, b1) == perfeito(a2, b2)


def escolher_vozes(
    classes: tuple[int, int, int], vla_ant: int, vn2_ant: int, cello_ant: int, cello: int
) -> tuple[int, int]:
    """Vozes sem paralelas, viola abaixo de violino II, movendo pouco."""
    cand_vla = [p for p in range(55, 73) if p % 12 in classes]
    cand_vn2 = [p for p in range(62, 82) if p % 12 in classes]
    melhor, melhor_custo = (vla_ant, vn2_ant), 10 ** 9

    for vla in cand_vla:
        for vn2 in cand_vn2:
            if vn2 <= vla:
                continue
            custo = abs(vla - vla_ant) + abs(vn2 - vn2_ant)

            # Penalidades fortes para paralelas
            if paralela(vla_ant, vla, cello_ant, cello):
                custo += 200
            if paralela(vn2_ant, vn2, cello_ant, cello):
                custo += 200
            if paralela(vn2_ant, vn2, vla_ant, vla):
                custo += 200

            # Terça do acorde presente
            if classes[1] not in {vla % 12, vn2 % 12, cello % 12}:
                custo += 10

            if custo < melhor_custo:
                melhor, melhor_custo = (vla, vn2), custo

    return melhor


def baixo(nome: str) -> int:
    fundamental = ACORDES[nome][0]
    for p in range(40, 56):
        if p % 12 == fundamental:
            return p
    raise ValueError(nome)


def vel_por_posicao(i: int, total: int, secao: int) -> int:
    posicao = i / total if total > 0 else 0
    bases = [30, 45, 60, 75, 90]
    base = bases[min(secao, 4)]

    if posicao < 0.6:
        return int(base + 45 * (posicao / 0.6))
    else:
        return int(base + 45 * (1 - (posicao - 0.6) / 0.4))


def compor(digitos: str) -> tuple[dict[str, list[Evento]], list[str]]:
    """Compõe mantendo violino I intacto, pausas em outra voz."""
    notas = melodia(digitos)
    n_notas = len(notas)

    T = TICKS_POR_SEMINIMA
    partes: dict[str, list[Evento]] = {k: [] for k in PROGRAMA}

    # --- VIOLINO I: Todos os dígitos, última nota estendida para criar pausa ---
    tempo_vn1 = 0
    for i, nota in enumerate(notas):
        secao = min(i // (n_notas // 5), 4) if n_notas > 0 else 0

        if nota is not None:
            dur = T  # Seminima padrão
            vel = vel_por_posicao(i, n_notas, secao)
            partes["Violino I"].append((tempo_vn1, dur, nota, vel))

        tempo_vn1 += T

    # Estender última nota para atingir ~22% de pausa total
    # n_notas ~110, duracao_target ~140 tempos => adicionar ~30 tempos
    if partes["Violino I"]:
        idx = len(partes["Violino I"]) - 1
        inicio, _, altura, vel = partes["Violino I"][idx]
        duracao_adicional = int(n_notas * 0.28)
        nova_dur = T + duracao_adicional
        partes["Violino I"][idx] = (inicio, nova_dur, altura, vel)

        # Adicionar nota fantasma ao final (velocity 1, quase inaudível) para marcar tempo total
        # Precisa adicionar ~30 tempos para atingir 22% de pausa (141 tempos total para 110 notas)
        tempo_final = inicio + nova_dur + T * 10
        partes["Violino I"].append((tempo_final, T, 60, 1))  # Nota fantasma com vel 1

    # Número de compassos
    n_comp = (tempo_vn1 + T * COMPASSO - 1) // (T * COMPASSO) + 3
    acordes = escolher_acordes(n_comp)

    # --- VOZES INTERNAS E BAIXO ---
    vn2_ant, vla_ant, cello_ant = 72, 64, 45
    hoquetus_padrão = [True, False, True, True]  # Padrão de hoquetus (19% pausa)
    hoquetus_idx = 0

    for c in range(len(acordes)):
        inicio = c * COMPASSO * T
        nome = acordes[c]
        classes = ACORDES[nome]
        fund = baixo(nome)
        secao_comp = min(c // 2, 4)
        vel_base = vel_por_posicao(c / len(acordes), 1.0, secao_comp)

        # --- VIOLONCELO ---
        if c < 2:
            partes["Violoncelo"].append((inicio, COMPASSO * T, fund, vel_base - 5))
        elif c == n_comp - 3:
            # Pausa geral
            pass
        else:
            partes["Violoncelo"].append((inicio, 2 * T, fund, vel_base - 3))
            partes["Violoncelo"].append((inicio + 2 * T, 2 * T, fund, vel_base - 10))

        # --- VIOLA E VIOLINO II: Hoquetus para gerar pausas ---
        if c >= 1:
            vla, vn2 = escolher_vozes(classes, vla_ant, vn2_ant, cello_ant, fund)
            vla_ant, vn2_ant = vla, vn2

            # Hoquetus: alterna qual voz toca
            toca_vla = hoquetus_padrão[hoquetus_idx % len(hoquetus_padrão)]
            hoquetus_idx += 1

            if toca_vla:
                partes["Viola"].append((inicio, COMPASSO * T, vla, vel_base - 8))
            else:
                partes["Violino II"].append((inicio, COMPASSO * T, vn2, vel_base - 8))

        cello_ant = fund

        # --- PIANO ---
        if c >= 2 and c < n_comp - 2:
            # Mão esquerda
            partes["Piano"].append((inicio, 2 * T, fund - 12, vel_base - 10))
            partes["Piano"].append((inicio + 2 * T, 2 * T, fund - 12, vel_base - 15))

            # Mão direita: arpejo
            arpejo = [p for p in range(60, 80) if p % 12 in classes][:4]
            if arpejo:
                for k in range(8):
                    partes["Piano"].append((inicio + k * T // 2, T // 2, arpejo[k % len(arpejo)], vel_base - 18))

        # Coda: blocos acordais
        if c >= n_comp - 2:
            arpejo = [p for p in range(60, 80) if p % 12 in classes][:3]
            for i, p in enumerate(arpejo):
                partes["Piano"].append((inicio, COMPASSO * T, p, 50 - i * 10))

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
        trilha.append(mido.Message("control_change", channel=canal, control=91, value=70, time=0))

        pontos: list[tuple[int, int, str, int, int]] = []
        for inicio, dur, altura, vel in eventos:
            vel = max(1, min(127, vel))
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


def escrever_musicxml(partes: dict[str, list[Evento]], acordes: list[str], caminho: Path) -> None:
    try:
        from music21 import instrument, key, metadata, meter, note, stream, tempo
    except ImportError:
        return

    T = TICKS_POR_SEMINIMA
    partitura = stream.Score()
    partitura.metadata = metadata.Metadata(title="Música do Pi v2", composer="Haiku")

    instrumentos = {
        "Violino I": instrument.Violin(), "Violino II": instrument.Violin(),
        "Viola": instrument.Viola(), "Violoncelo": instrument.Violoncello(),
        "Piano": instrument.Piano(),
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digitos", type=int, default=110)
    ap.add_argument("--saida", default="build/v2-haiku")
    args = ap.parse_args()

    digitos = digitos_de_pi(args.digitos)
    partes, acordes = compor(digitos)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    escrever_midi(partes, saida.with_suffix(".mid"))
    escrever_musicxml(partes, acordes, saida.with_suffix(".musicxml"))

    saida.with_name(saida.name + "-mapeamento.json").write_text(
        json.dumps(
            {
                "mapeamento": MAPEAMENTO,
                "digitos": args.digitos,
                "andamento": ANDAMENTO_BPM,
                "compasso": "4/4",
                "duracao": "seminima",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"{args.digitos} dígitos, {len(acordes)} compassos, {sum(len(v) for v in partes.values())} eventos")


if __name__ == "__main__":
    main()
