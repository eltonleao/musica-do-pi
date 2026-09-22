"""v10 - menor que vira maior: a v9 até o eixo, e Ré maior crescendo dali até o clímax final.

Parte da v9, que fica intacta, e não muda nada em [0, 56): o conjunto (trilha, tick, altura)
dessa metade sai idêntico ao de `build/v9.mid`. O que se compõe é [56, 112), com as decisões
2 a 9 do plano P11:

- **O mapeamento vira maior no eixo.** Até o tempo 56 o mapeamento da v9; de 56 em diante o
  mesmo com dois graus trocados, 3 → 66 (Fá♯) e 6 → 71 (Si). Os outros oito não mudam, porque
  Ré menor e Ré maior compartilham as outras sete notas. O sidecar declara os dois trechos em
  `"mapeamentos"`, e o `conferir-digitos` lê cada ataque no inverso do trecho dele.
- **A harmonia depois do eixo é Ré maior.** Cada acorde da v9 vira o homônimo maior (Dm → D,
  Gm → G) e o Si bemol some: o VI da v9 (Bb) vira Bm, o relativo, que traz o Si natural do modo
  novo. Em [88, 96) entram Bm e F♯m no lugar do Dm parado da v9, para o A' ter para onde subir,
  e a cadência final é G - A7 - D. Nenhuma das classes usadas é 5 (Fá) ou 10 (Si♭).
- **Sem pausa geral e sem sussurro.** O perfil de expressão da v10 leva `"pausa": None`: o eixo
  continua sendo o primeiro pico, alarga em `fator_eixo` de 56 a 58, e a música não para.
- **O A' adensa.** Entre 76 e 104 o piano fecha o arpejo em bloco a partir de 84, os pads passam
  a dobrar a terça e a fundamental, e no fim as 6 trilhas soam juntas em todo compasso.
- **A nota mais aguda da peça está no clímax final.** As oitavas do sidecar levam o 9 do tempo 96
  ao Mi6 e o 3 do tempo 104 ao Fá♯6 - a nota mais alta da peça, e nota do acorde de chegada.
- **O final é Ré maior com Ré no baixo**, e o rit. dos dois últimos compassos alarga sem descer.

Uso: python src/v10.py [--saida build/v10] [--sem-audio]
"""

from __future__ import annotations

import argparse
import copy
import json
from itertools import combinations
from pathlib import Path

import mido

import expressao
from pi_digitos import digitos_de_pi
from v8 import (CC7, COMPASSO, ENTRADA, FIM, MEIOS, TEMPOS, articular, baixos, escrever_midi,
                gravar_audio, harmonizar, melodia, trechos, vel)
from v9 import MAPEAMENTO as MAPEAMENTO_MENOR
from v9 import (EIXO, PIANO, TESSITURA_DO_PAD, TUTTI, TUTTI_PIANO, VEL_TUTTI, melodia_v9)

# O mapeamento de 56 em diante: o mesmo da v9 com o 3 em Fá♯ e o 6 em Si.
MAPEAMENTO_MAIOR = dict(MAPEAMENTO_MENOR, **{"3": 66, "6": 71})
MAPEAMENTOS = [[0, EIXO, MAPEAMENTO_MENOR], [EIXO, TEMPOS, MAPEAMENTO_MAIOR]]

# As oitavas declaradas: o eixo como na v9, e o clímax final subindo até o Fá♯6 do tempo 104.
OITAVA = {str(EIXO): 12, "96": 12, "100": 12, "104": 24}
CLIMAX = 96                   # daqui em diante a melodia está no registro alto

# Os acordes de Ré maior. Nenhuma classe 5 (Fá) nem 10 (Si♭).
ACORDES_MAIOR = {
    "D": (2, {2, 6, 9}), "G": (7, {7, 11, 2}), "A": (9, {9, 1, 4}), "A7": (9, {9, 1, 4, 7}),
    "Bm": (11, {11, 2, 6}), "Em": (4, {4, 7, 11}), "F#m": (6, {6, 9, 1}),
}
# Grau a grau, o que cada acorde da v9 vira depois do eixo. O Bb (VI de Ré menor) vira o Bm,
# relativo de Ré maior: é ele que traz o Si natural e tira o Si bemol da harmonia.
MAIOR_DE = {"Dm": "D", "Gm": "G", "Bb": "Bm", "A": "A", "A7": "A7", "F": "D", "C": "A"}
# Onde o A' foge do paralelo, para a segunda metade ter caminho harmônico até o clímax.
SUBSTITUICOES = {44: "Bm", 45: "F#m", 46: "Bm", 47: "A7", 50: "G", 51: "A7", 52: "D", 53: "D"}
RE_MAIOR = (50, 57, 66, 74)   # Ré, Lá, Fá♯ interno, Ré no alto: o acorde final, Ré no baixo
TETO = 90                     # o Fá♯6 do clímax é o teto da peça

# A densidade do A': de 84 em diante o piano toca o acorde em bloco, e a partir de 92 as cordas
# dobram a fundamental, para as 6 trilhas soarem em cada compasso de [92, 112).
RETRANSICAO = 72              # a dominante que prepara o A': daqui os pads abrem em dupla corda
BLOCO = 84
TUTTI_FINAL = 92
DOBRA_DO_PAD = {"Viola": -12, "Violino II": 0}

# O perfil de expressão da v10: a curva da v9 até o eixo, e sem queda depois dele. Sobe de 76
# ao clímax e alarga no fim sem descer - o rit. dos dois últimos compassos fica, a dinâmica não.
PERFIL: dict = dict(copy.deepcopy(expressao.PERFIL_PADRAO), **{
    "pausa": None,
    "nivel": [
        (0, .18), (4, .28), (8.5, .42), (12, .33), (16.5, .50), (20, .42), (26, .58),
        (32, .50), (36, .36), (39, .34),
        (40, .38), (45, .56), (48, .52), (53, .80), (55, .84), (56, .90), (58, .88),
        (60, .76), (62.5, .74), (64, .76), (66.5, .78), (70, .80),      # B relaxa, não sussurra
        (72, .82), (76, .76), (80.5, .80), (84, .82), (88.5, .89),      # A' adensando
        (92, .92), (96, .97), (100, 1.0), (104, 1.0), (108, 1.0), (112, 1.0),   # clímax final
    ],
    "rampas": [(54.5, 56, 1.0, 0.92), (102, 109.5, 1.0, 0.82)],
    "acento_eixo": 0,
})

Nota = tuple[float, float, int, str]
Evento = tuple[float, float, int, int]


def melodia_v10(dig: str) -> tuple[list[Nota], list[Nota], int, str, str]:
    """A melodia da v9 com o mapeamento maior de 56 em diante e as oitavas do clímax."""
    v9_notas, v8_notas, k, a, b = melodia_v9(dig)
    digito_menor = {alt: c for c, alt in MAPEAMENTO_MENOR.items()}
    oitava_v9 = {str(EIXO): 12}          # a única oitava que a v9 declara
    notas = []
    for t, d, alt, voz in v9_notas:
        if t >= EIXO:
            base = alt - oitava_v9.get(str(int(t)), 0) if t == int(t) else alt
            alt = MAPEAMENTO_MAIOR[digito_menor[base]] + OITAVA.get(str(int(t)), 0)
        if t >= CLIMAX and t + d >= FIM - 2:
            d = FIM - t          # o Fá♯6 final é nota do acorde e segura até o fim, com o tutti
        notas.append((t, d, alt, voz))
    return sorted(notas), v8_notas, k, a, b


def conferir_pi(notas: list[Nota], dig: str) -> str:
    """Lê como o conferir_digitos: oitava desfeita, dobra na trilha dona, dois mapeamentos."""
    inverso = [{alt: c for c, alt in m.items()} for _, _, m in MAPEAMENTOS]
    por_tick: dict[float, list[tuple[int, str]]] = {}
    for t, _, alt, voz in notas:
        base = alt - OITAVA.get(str(int(t)), 0) if t == int(t) else alt
        por_tick.setdefault(t, []).append((base, voz))
    lida = ""
    for t in sorted(por_tick):
        grupo = por_tick[t]
        if len({alt % 12 for alt, _ in grupo}) > 1:
            raise SystemExit(f"classes diferentes no tempo {t}")
        dona = "Flauta" if 40 <= t < 72 else "Violino I"
        alt = next((a for a, voz in grupo if voz == dona), grupo[0][0])
        lida += inverso[1 if t >= EIXO else 0][alt]
    ida = lida[:len(lida) // 2]
    if ida != dig[:len(ida)] or lida != lida[::-1]:
        raise SystemExit(f"a melodia não é pi espelhado:\n  lida {lida}\n  pi   {dig[:len(ida)]}")
    return lida


def harmonia_v10(acordes: list[str]) -> list[str]:
    """Os acordes da v9 até o eixo; de 56 em diante, os homônimos maiores com as substituições."""
    saida = list(acordes[:MEIOS - 2]) + ["D", "D"]
    for h in range(EIXO // 2, MEIOS):
        saida[h] = SUBSTITUICOES.get(h, MAIOR_DE.get(saida[h], saida[h]))
    return saida


def classes(nome: str) -> set[int]:
    from v8 import ACORDES
    return ACORDES_MAIOR[nome][1] if nome in ACORDES_MAIOR else ACORDES[nome][1]


def fundamental(nome: str) -> int:
    from v8 import ACORDES
    return ACORDES_MAIOR[nome][0] if nome in ACORDES_MAIOR else ACORDES[nome][0]


def baixos_v10(acordes: list[str]) -> list[int]:
    """Os graves da v9 até o eixo; depois, a fundamental de cada acorde novo, com pedal de Lá."""
    from v8 import PEDAL
    return [9 if h in PEDAL else fundamental(nome) for h, nome in enumerate(acordes)]


def teto(notas: list[Nota], ini: float, fim: float, padrao: int = TETO) -> int:
    """A nota mais grave da melodia que soa em [ini, fim): o acompanhamento não passa dela."""
    return min([alt for t, d, alt, _ in notas if t < fim and t + d > ini] + [padrao])


def voicings(nome: str, lo: int, hi: int) -> list[tuple[int, ...]]:
    """4 notas do acorde em [lo, hi]; quando a melodia aperta o teto e não cabem 4, cabem 3."""
    cls = classes(nome)
    alturas = [a for a in range(lo, hi + 1) if a % 12 in cls]
    for n in (4, 3):
        cands = [c for c in combinations(alturas, n) if {a % 12 for a in c} == cls]
        if cands:
            return cands
    raise SystemExit(f"sem voicing de {nome} em [{lo}, {hi}]")


def _v9_ate_o_eixo(partes_v9: dict[str, list[Evento]]) -> dict[str, list[Evento]]:
    """Só os ataques anteriores ao eixo: é a metade que não se toca."""
    return {nome: [e for e in ev if e[0] < EIXO] for nome, ev in partes_v9.items()}


def piano(acordes: list[str], graves: list[int], notas: list[Nota],
          antes: list[Evento]) -> list[Evento]:
    """O arpejo da v9 antes do eixo; depois dele o mesmo arpejo, virando bloco a partir de 84."""
    ev: list[Evento] = list(antes)
    anterior = None
    for h in range(MEIOS - 1):
        t, fim = 2 * h, (FIM if h == MEIOS - 2 else 2 * h + 2)
        if t < EIXO:
            continue
        if t == EIXO:
            ev += [(t, 2, alt, VEL_TUTTI["Piano"]) for alt in TUTTI_PIANO]
            continue
        if h == MEIOS - 2:
            v = RE_MAIOR
        else:
            cands = voicings(acordes[h], PIANO[0], min(PIANO[1], teto(notas, t, fim)))

            def custo(c: tuple[int, ...]) -> tuple[float, tuple[int, ...]]:
                perto = abs(sum(c) / len(c) - 57) if anterior is None else \
                    sum(abs(a - b) for a, b in zip(c, anterior)) + 2 * abs(len(c) - len(anterior))
                return perto, c
            v = min(cands, key=custo)
        anterior = v
        if t >= BLOCO and h != MEIOS - 2:
            # bloco: o A' adensa. Do tutti final em diante o bloco repica na segunda semínima,
            # que é o que dobra a contagem de ataques por compasso sem sujar a harmonia.
            ev += [(t, fim - t, alt, vel("Piano", t) + 6) for alt in v]
            if t >= TUTTI_FINAL:
                ev += [(t + 1, fim - t - 1, alt, vel("Piano", t) + 10) for alt in v]
        elif RETRANSICAO <= t < RETRANSICAO + 4:
            # A retransição e a cabeça do A' repicam o arpejo na segunda semínima: o sample de
            # corda já decaiu no meio do meio-compasso, e sem o repique o loudness cava ali.
            ev += [(t + k / 2, fim - t - k / 2, alt, vel("Piano", t) + 4) for k, alt in enumerate(v)]
            ev += [(t + 1 + k / 4, fim - t - 1 - k / 4, alt, vel("Piano", t) + 8)
                   for k, alt in enumerate(v)]
        else:
            ev += [(t + k / 2, fim - t - k / 2, alt, vel("Piano", t)) for k, alt in enumerate(v)]
    for ini, fim, (_, pc) in trechos(list(zip(acordes, graves)), por_compasso=True):
        fim = min(fim, FIM)
        if ini < EIXO or ini == EIXO:
            continue                            # antes do eixo veio da v9; no eixo está no bloco
        grave = next(a for a in range(26, 38) if a % 12 == pc)
        v = min(127, vel("Piano", ini) + (16 if ini >= TUTTI_FINAL else (6 if ini >= BLOCO else 0)))
        if ini >= RETRANSICAO and fim - ini > COMPASSO:
            for p in range(int(ini), int(fim), COMPASSO):
                ev += [(p, fim - p, grave, v), (p, fim - p, grave + 12, v)]
        else:
            ev += [(ini, fim - ini, grave, v), (ini, fim - ini, grave + 12, v)]
        if ini >= TUTTI_FINAL:
            # O clímax final precisa pesar mais que o eixo, e o que pesa no grave é o fundamental
            # dobrado na oitava de baixo, com o baixo repicando a cada semínima.
            ev.append((ini, fim - ini, grave - 12, v))
            ev += [(p, fim - p, grave, v) for p in range(int(ini) + 1, int(fim))]
    return sorted(ev)


def violoncelo(graves: list[int], antes: list[Evento]) -> list[Evento]:
    """O baixo da v9 antes do eixo; depois, a fundamental de Ré maior sem cair no sussurro."""
    ev = list(antes)
    t1 = (29 - ENTRADA["Violoncelo"]) * COMPASSO
    for ini, fim, pc in trechos(graves, por_compasso=True):
        if ini < EIXO or ini >= t1:
            continue
        alt = next(a for a in range(38, 50) if a % 12 == pc)
        if ini == EIXO:
            ev += [(ini, 2, TUTTI["Violoncelo"], VEL_TUTTI["Violoncelo"]),
                   (58, fim - 58, alt, vel("Violoncelo", 58))]
        elif RETRANSICAO <= ini < RETRANSICAO + 4:
            # Na retransição o baixo pulsa por semínima, em crescendo: é a anacruse do A'.
            passos = [p for p in range(int(ini), int(min(fim, RETRANSICAO + 4)))]
            ev += [(p, fim - p, alt, vel("Violoncelo", p) + 4 + 2 * j)
                   for j, p in enumerate(passos)]
        else:
            ev.append((ini, fim - ini, alt, min(127, vel("Violoncelo", ini) + (14 if ini >= TUTTI_FINAL else 0))))
    ev.append((FIM, TEMPOS - FIM, 38, vel("Violoncelo", FIM) + 8))     # o Ré do acorde final
    return sorted(ev)


def pad(voz: str, acordes: list[str], notas: list[Nota], outra: list[Evento],
        antes: list[Evento]) -> list[Evento]:
    """O pad da v9 depois do eixo, sempre abaixo da melodia, dobrando a fundamental no tutti."""
    lo, hi = TESSITURA_DO_PAD[voz]
    t1 = (29 - ENTRADA[voz]) * COMPASSO
    anterior = (lo + hi) // 2
    ev = list(antes)
    # O trecho longo de dominante da v9 atravessa a retransição, e um sample de corda segurado
    # desde o 68 já decaiu no 74: ali o loudness cavava. Quebrar o trecho em RETRANSICAO faz
    # o pad reatacar na dominante, que é onde o A' começa a ser preparado.
    partidos = []
    for ini_h, fim_h, nome in trechos(acordes, por_compasso=False):
        if ini_h < RETRANSICAO < fim_h:
            partidos += [(ini_h, RETRANSICAO, nome), (RETRANSICAO, fim_h, nome)]
        else:
            partidos.append((ini_h, fim_h, nome))
    for ini_h, fim_h, nome in partidos:
        ini, fim = max(ini_h, EIXO), min(fim_h, t1)
        if ini >= fim:
            continue
        if ini == EIXO:
            ev.append((EIXO, 2, TUTTI[voz], VEL_TUTTI[voz]))
            ini = EIXO + 2
            if ini >= fim:
                continue
        cls = classes(nome)
        mel = {alt % 12 for i, d, alt, _ in notas if i < fim and i + d > ini}
        out = {alt % 12 for i, d, alt, _ in outra if i < fim and i + d > ini}
        alto = hi + (7 if ini >= RETRANSICAO else 0)   # o A' sobe com a melodia, sem passar dela
        cands = [a for a in range(lo, min(alto, teto(notas, ini, fim)) + 1) if a % 12 in cls]
        for extra in (mel | out, out, set()):
            boas = [a for a in cands if all((a - q) % 12 not in (1, 11) for q in cls | extra)]
            if boas:
                break
        else:
            boas = cands
        escolhida = min(boas or cands, key=lambda a: (abs(a - anterior), a))
        reforco = 8 if ini >= TUTTI_FINAL else (4 if ini >= BLOCO else 0)
        if ini >= RETRANSICAO and fim - ini > COMPASSO:
            # Renovação de arco por compasso: nota segurada quatro tempos já decaiu no sample,
            # e é isso que cavava a retransição. Cada compasso reataca um degrau mais forte.
            for j, p in enumerate(range(int(ini), int(fim), COMPASSO)):
                ev.append((p, fim - p, escolhida, min(127, vel(voz, p) + reforco + 2 * j)))
        else:
            ev.append((ini, fim - ini, escolhida, vel(voz, ini) + reforco))
        anterior = escolhida
        # A retransição da v9 esvaziava para preparar o sussurro, e a v10 não sussurra: da
        # dominante de 72 em diante cada pad abre em dupla corda, a nota mais alta do acorde
        # que ainda cabe sob a melodia. É o que tira o vale de 30 LU abaixo do eixo.
        if ini >= RETRANSICAO:
            acima = [a for a in cands if a > escolhida]
            if acima:
                for j, p in enumerate(range(int(ini), int(fim), COMPASSO)):
                    ev.append((p, fim - p, max(acima), min(127, vel(voz, p) + reforco + 4 + 2 * j)))
    ev += _cauda_do_pad(voz, acordes, notas, ev)
    return sorted(ev)


def _cauda_do_pad(voz: str, acordes: list[str], notas: list[Nota],
                  ja: list[Evento]) -> list[Evento]:
    """Os pads saem no c25 na v9; aqui eles ficam até o fim, para o tutti do clímax ser de 6."""
    lo, hi = TESSITURA_DO_PAD[voz]
    t1 = (29 - ENTRADA[voz]) * COMPASSO
    ev = []
    anterior = max((e[2] for e in ja), default=(lo + hi) // 2)
    for ini_h, fim_h, nome in trechos(acordes, por_compasso=False):
        ini, fim = max(ini_h, t1), min(fim_h, FIM)
        if ini >= fim:
            continue
        cls = classes(nome)
        cands = [a for a in range(lo, min(hi + 7, teto(notas, ini, fim)) + 1) if a % 12 in cls]
        if not cands:
            continue
        escolhida = min(cands, key=lambda a: (abs(a - anterior), a))
        ev.append((ini, fim - ini, escolhida, vel(voz, ini) + 10))
        acima = [a for a in cands if a > escolhida]
        if acima:
            ev.append((ini, fim - ini, max(acima), vel(voz, ini) + 12))
        anterior = escolhida
    final = next(a for a in range(lo, hi + 1) if a % 12 in classes("D"))
    ev.append((FIM, TEMPOS - FIM, final, vel(voz, FIM) + 10))
    return ev


def compor(dig: str):
    from v9 import compor as compor_v9
    partes_v9, _, _, _, _, _, _ = compor_v9(dig)
    antes = _v9_ate_o_eixo(partes_v9)

    notas, v8_notas, k, a, b = melodia_v10(dig)
    lida = conferir_pi(notas, dig)
    acordes = harmonia_v10(harmonizar(v8_notas))
    graves = baixos_v10(acordes)

    def voz(nome: str) -> list[Evento]:
        depois = articular([n for n in notas if n[3] == nome and n[0] >= EIXO], nome)
        reforco = [(t, d, alt, min(127, v + (10 if t >= TUTTI_FINAL else (5 if t >= BLOCO else 0))))
                   for t, d, alt, v in depois]
        return sorted(antes[nome] + reforco)

    def dobra_da_flauta() -> list[Evento]:
        """No clímax a flauta volta, dobrando a melodia uma oitava abaixo: o tutti é de 6.

        Oitava abaixo, e não acima, porque a linha de pi tem de continuar sendo a nota mais
        aguda (C8); e mesma classe de altura, que o conferir-digitos lê como um dígito só,
        na trilha dona do trecho (o Violino I fora de [40, 72)).
        """
        mel = [n for n in notas if n[3] == "Violino I" and n[0] >= TUTTI_FINAL]
        ev = articular([(t, d, alt - 12, "Flauta") for t, d, alt, _ in mel], "Flauta")
        return [(t, d, alt, min(127, v + 10)) for t, d, alt, v in ev]

    viola = pad("Viola", acordes, notas, [], antes["Viola"])
    partes = {
        "Violino I": voz("Violino I"),
        "Flauta": sorted(voz("Flauta") + dobra_da_flauta()),
        "Viola": viola,
        "Violino II": pad("Violino II", acordes, notas, viola, antes["Violino II"]),
        "Violoncelo": violoncelo(graves, antes["Violoncelo"]),
        "Piano": piano(acordes, graves, notas, antes["Piano"]),
    }
    return partes, acordes, graves, k, a, b, lida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v10")
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
    expressivo = expressao.aplicar(mido.MidiFile(str(midi)), PERFIL)
    expressivo.save(str(midi))
    numeros = expressao.resumo(expressivo, PERFIL)
    Path(f"{saida}-mapeamento.json").write_text(json.dumps({
        "mapeamento": MAPEAMENTO_MENOR, "mapeamentos": MAPEAMENTOS, "oitava": OITAVA,
        "digitos": {"A": a, "B": b, "A'": a[::-1]}, "liquidacao_k": k, "melodia_lida": lida,
        "compasso": f"{COMPASSO}/4", "andamento_bpm": numeros["mediana_bpm"],
        "acordes_por_meio_compasso": acordes, "baixo_por_meio_compasso": graves,
        "secoes": {"A": [2, 9], "B": [11, 18], "A'": [20, 27]}, "cc7": CC7, "tempos": TEMPOS,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"melodia lida: {lida}")
    print(f"pi          : {dig[:len(lida) // 2]}")
    print(json.dumps(numeros, ensure_ascii=False))
    print(f"{midi}: {sum(len(v) for v in partes.values())} notas, melodia "
          f"{len(partes['Violino I']) + len(partes['Flauta'])}")
    if not args.sem_audio:
        gravar_audio(midi)
        print(f"{midi.with_suffix('.mp3')} gravado")


if __name__ == "__main__":
    main()
