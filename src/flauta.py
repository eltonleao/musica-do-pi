"""Acrescenta a flauta ao sexteto, sem tocar no compositor da PoC.

Formação pedida pelo dono em 20/09/2026: violino I, violino II, viola,
violoncelo, piano e flauta. Este arquivo existe separado porque os executores
do teste de modelos estavam lendo `compor.py` no mesmo momento; a consolidação
num arquivo só fica para a versão 2.

O papel da flauta é de brilho e de eco, nunca de linha principal: a invariante
da peça continua sendo a sequência do violino I, e a flauta só dobra ou
sustenta. Por seção de 8 compassos:

  1 (c. 1-8)    cala - a flauta é o instrumento que ainda não chegou
  2 (c. 9-16)   pedal agudo: a quinta do acorde, uma nota por compasso
  3 (c. 17-24)  dobra os tempos 1 e 3 da melodia, uma oitava acima
  4 (c. 25-)    dobra a melodia inteira uma oitava acima, no clímax
  coda          eco: as quatro últimas alturas, piano, uma oitava acima

Uso: python src/flauta.py --digitos 132 --saida build/pi-flauta
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import compor
from compor import ACORDES, COMPASSO, MAPEAMENTO_POC, TICKS_POR_SEMINIMA as T
from pi_digitos import digitos_de_pi

# Flauta transversal: dó4 a dó7 no papel; abaixo de ré4 o som é fraco e some
# dentro das cordas, então a escrita fica de ré4 (62) para cima.
TESSITURA_FLAUTA = (62, 96)
PROGRAMA_FLAUTA = 73  # GM: Flute


def perfeito(alto: int, baixo: int) -> int | None:
    ic = (alto - baixo) % 12
    return ic if ic in (0, 7) else None


def paralela(a1: int, a2: int, b1: int, b2: int) -> bool:
    """As duas vozes se movem e mantêm a mesma quinta ou oitava."""
    if a1 == a2 or b1 == b2:
        return False
    return perfeito(a1, b1) is not None and perfeito(a1, b1) == perfeito(a2, b2)


def parte_da_flauta(notas: list[int | None], acordes: list[str],
                    partes: dict[str, list[tuple[int, int, int, int]]]) -> list[tuple[int, int, int, int]]:
    eventos: list[tuple[int, int, int, int]] = []
    n_comp = len(acordes)
    dur_comp = COMPASSO * T

    def cabe(p: int) -> bool:
        return TESSITURA_FLAUTA[0] <= p <= TESSITURA_FLAUTA[1]

    def no_tempo1(nome: str, c: int) -> int | None:
        """Altura que a voz `nome` ataca no tempo 1 do compasso `c`."""
        alvo = c * dur_comp
        for inicio, _, altura, _ in partes.get(nome, []):
            if inicio == alvo:
                return altura
        return None

    # A flauta é voz real no pedal e dobramento no resto. Nos dois casos ela
    # não pode formar quinta nem oitava paralela com o violino II nem com o
    # violoncelo na passagem de compasso; quando formaria, ela cala o tempo 1 e
    # entra depois - entrada deslocada é solução de orquestração, e não afrouxa
    # a regra.
    anterior: int | None = None
    for c, nome in enumerate(acordes):
        secao = min(c // 8, 3)
        inicio = c * dur_comp
        if secao == 0:
            continue

        def gera_paralela(altura: int) -> bool:
            if anterior is None:
                return False
            for voz in ("Violino II", "Violoncelo", "Viola"):
                b1, b2 = no_tempo1(voz, c - 1), no_tempo1(voz, c)
                if b1 is None or b2 is None:
                    continue
                if paralela(anterior, altura, b1, b2):
                    return True
            return False

        if secao == 1:
            # Pedal agudo: a TERÇA do acorde, não a quinta - a quinta contra a
            # fundamental do violoncelo produzia quintas paralelas em série
            # (sete seguidas, compassos 9 a 16, medidas em 20/09/2026).
            for grau in (1, 2, 0):          # terça, quinta, fundamental
                classe = ACORDES[nome][grau]
                cand = [p for p in range(74, 91) if p % 12 == classe]
                escolhida = min(cand, key=lambda p: abs(p - (anterior or 81))) if cand else None
                if escolhida is not None and not gera_paralela(escolhida):
                    eventos.append((inicio, dur_comp, escolhida, 46))
                    anterior = escolhida
                    break
            continue

        tempos = [0, 2] if secao == 2 else list(range(COMPASSO))
        primeiro_do_compasso = True
        for t in tempos:
            i = c * COMPASSO + t
            if i >= len(notas) or notas[i] is None:
                continue
            altura = notas[i] + 12
            if not cabe(altura):
                altura = notas[i]
            if primeiro_do_compasso and t == 0 and gera_paralela(altura):
                primeiro_do_compasso = False
                continue                      # cala o tempo 1 e entra no próximo
            vel = 62 if secao == 2 else 78
            eventos.append((inicio + t * T, T, altura, vel))
            if t == 0:
                anterior = altura
            primeiro_do_compasso = False

    # Coda: eco das quatro últimas alturas soantes, uma oitava acima, piano.
    soantes = [p for p in notas if p is not None]
    ultimo_inicio = n_comp * dur_comp
    for k, p in enumerate(soantes[-4:]):
        altura = p + 12 if cabe(p + 12) else p
        eventos.append((ultimo_inicio + k * T, T, altura, 40))
    return eventos


def escrever_musicxml_sexteto(partes, acordes, caminho) -> str:
    """Igual ao da PoC, com a flauta na lista de instrumentos. Existe aqui, e
    não como edição de `compor.py`, porque os executores do teste de modelos
    estão lendo aquele arquivo neste momento; a fusão fica para a versão 2."""
    from music21 import instrument, key, metadata, meter, note, stream, tempo, voiceLeading

    partitura = stream.Score()
    partitura.metadata = metadata.Metadata(title="Música do Pi (sexteto com flauta)",
                                           composer="dígitos de pi + regras")
    instrumentos = {
        "Flauta": instrument.Flute(), "Violino I": instrument.Violin(),
        "Violino II": instrument.Violin(), "Viola": instrument.Viola(),
        "Violoncelo": instrument.Violoncello(), "Piano": instrument.Piano(),
    }
    ordem = ["Flauta", "Violino I", "Violino II", "Viola", "Violoncelo", "Piano"]
    for nome in [n for n in ordem if n in partes]:
        parte = stream.Part(id=nome)
        parte.partName = nome
        parte.insert(0, instrumentos[nome])
        parte.insert(0, tempo.MetronomeMark(number=compor.ANDAMENTO_BPM))
        parte.insert(0, meter.TimeSignature("4/4"))
        parte.insert(0, key.Key("a"))
        for inicio, dur, altura, vel in partes[nome]:
            n = note.Note(altura)
            n.quarterLength = dur / T
            n.volume.velocity = vel
            parte.insert(inicio / T, n)
        partitura.insert(0, parte)
    partitura.write("musicxml", fp=str(caminho))

    def por_compasso(nome):
        return {inicio // (COMPASSO * T): altura
                for inicio, _, altura, _ in partes.get(nome, [])
                if (inicio % (COMPASSO * T)) == 0}

    vozes = {n: por_compasso(n) for n in ("Flauta", "Violino II", "Viola", "Violoncelo")}
    nomes = [n for n in vozes if vozes[n]]
    problemas = []
    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            va, vb = vozes[nomes[i]], vozes[nomes[j]]
            for c in sorted(va):
                if c + 1 in va and c in vb and c + 1 in vb:
                    q = voiceLeading.VoiceLeadingQuartet(note.Note(va[c]), note.Note(va[c + 1]),
                                                         note.Note(vb[c]), note.Note(vb[c + 1]))
                    if q.parallelFifth():
                        problemas.append(f"compasso {c+1}->{c+2}: quintas paralelas entre {nomes[i]} e {nomes[j]}")
                    if q.parallelOctave():
                        problemas.append(f"compasso {c+1}->{c+2}: oitavas paralelas entre {nomes[i]} e {nomes[j]}")
    linhas = [f"acordes por compasso: {' '.join(acordes)}",
              f"violações de condução de vozes: {len(problemas)}"] + problemas
    return "\n".join(linhas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digitos", type=int, default=132)
    ap.add_argument("--saida", default="build/pi-flauta")
    args = ap.parse_args()

    digitos = digitos_de_pi(args.digitos)
    partes, acordes = compor.compor(digitos)
    notas = compor.melodia(digitos)

    # A flauta entra no dicionário de partes, e o MIDI/MusicXML saem com ela.
    compor.PROGRAMA["Flauta"] = PROGRAMA_FLAUTA
    compor.TESSITURA["Flauta"] = TESSITURA_FLAUTA
    partes["Flauta"] = parte_da_flauta(notas, acordes, partes)

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    compor.escrever_midi(partes, saida.with_suffix(".mid"))
    resumo = escrever_musicxml_sexteto(partes, acordes, saida.with_suffix(".musicxml"))
    if resumo:
        saida.with_name(saida.name + "-harmonia.txt").write_text(resumo + "\n", encoding="utf-8")
    saida.with_name(saida.name + "-mapeamento.json").write_text(json.dumps(
        {"mapeamento": MAPEAMENTO_POC, "digitos": args.digitos, "andamento": compor.ANDAMENTO_BPM,
         "compasso": "4/4", "duracao": "seminima", "formacao": list(compor.PROGRAMA)},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fora = [p for _, _, p, _ in partes["Flauta"] if not (TESSITURA_FLAUTA[0] <= p <= TESSITURA_FLAUTA[1])]
    print(f"{len(partes['Flauta'])} notas de flauta, {len(fora)} fora da tessitura")
    print(f"formação: {', '.join(compor.PROGRAMA)}")
    if resumo:
        print(resumo.splitlines()[1])


if __name__ == "__main__":
    main()
