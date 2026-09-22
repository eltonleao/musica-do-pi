"""v9 - o arrepio no eixo: a v8 uma oitava abaixo, e o Mi6 soando uma vez só, no tempo 56.

Parte da v8, que fica intacta, e muda o registro e a textura, não a harmonia (plano P10):

- A melodia desce uma oitava (MAPEAMENTO da v8 menos 12). Só o ataque do tempo 56 fica no alto:
  o 9 do tempo 54 soa Mi5 e o 9 do tempo 56 salta para o Mi6, na cabeça do c15.
- Os pads e o piano descem junto, e em todo ataque da melodia o acompanhamento fica abaixo dela.
- No c10 o Violino I sustenta o Ré da cadência de A até a flauta entrar, para a textura não cair.
- O c14 esvazia: só a Flauta e o Violoncelo, no pedal de Lá.
- No tempo 56 os 6 atacam juntos (o Violino I dobra o Mi da flauta uma oitava abaixo), o
  expressao.py corta tudo em 57,25 e abre a pausa geral, e a peça recomeça em sussurro: a flauta
  sozinha em 57,5, o violoncelo em 58, e o resto só no c16.
- O último acorde é Ré maior, com o Fá♯ numa voz interna do piano; o Fá da melodia solta antes.

A harmonia sai do harmonizar() da v8 aplicado à melodia da v8, e por isso os acordes e o baixo
são os mesmos. Depois de compor, aplica o expressao.py (PERFIL_PADRAO, o mesmo da v8 expressiva).

Uso: python src/v9.py [--saida build/v9] [--sem-audio]
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import mido

import expressao
from pi_digitos import digitos_de_pi
from v8 import (ACORDES, CC7, COMPASSO, ENTRADA, FIM, MEIOS, TEMPOS, articular, baixos,
                escrever_midi, gravar_audio, harmonizar, melodia, trechos, vel)

MAPEAMENTO = {"0": 61, "1": 62, "2": 64, "3": 65, "4": 67, "5": 69, "6": 70,
              "7": 73, "8": 74, "9": 76}
EIXO = 56
OITAVA = {str(EIXO): 12}      # o ataque do eixo soa uma oitava acima do mapeamento
TETO = 76                     # nada acima disto fora do eixo
TESSITURA_DO_PAD = {"Viola": (48, 57), "Violino II": (55, 64)}
PIANO = (50, 64)              # arpejo; abaixo de 50 moram as oitavas do baixo
C14 = (52, 56)                # só Flauta e Violoncelo
RETOMA = 60                   # c16: piano e pads voltam depois do sussurro

# O tutti do eixo, sobre Lá: baixo em oitavas, o arpejo do piano vira bloco, e a série sobe até
# o Mi6 da flauta com os intervalos abrindo embaixo e o Dó♯ uma vez só nas cordas.
TUTTI = {"Violino I": 76, "Violino II": 69, "Viola": 61, "Violoncelo": 45}
TUTTI_PIANO = (33, 45, 52, 57, 61, 64)
VEL_TUTTI = {"Violino II": 64, "Viola": 64, "Violoncelo": 70, "Piano": 72}
SUSSURRO = 0.75               # velocity de quem volta entre a pausa e o c16
RE_MAIOR = (50, 57, 66, 74)   # Ré, Lá, Fá♯ interno, Ré no alto; o arpejo sobe até o Ré5

Nota = tuple[float, float, int, str]
Evento = tuple[float, float, int, int]


def melodia_v9(dig: str) -> tuple[list[Nota], list[Nota], int, str, str]:
    """A melodia da v9 e a da v8 (a da v8 alimenta o harmonizar, para os acordes não mudarem)."""
    v8, k, a, b = melodia(dig)
    notas = []
    for t, d, alt, voz in v8:
        alt -= 12
        if t == EIXO:
            alt += OITAVA[str(EIXO)]
        if voz == "Violino I" and t == 32:
            d = 40 - t                          # c10: o Ré da cadência segura até a flauta
        if voz == "Violino I" and t + d >= FIM:
            d = TEMPOS - 4 - t                  # o Fá final solta antes do Ré maior
        notas.append((t, d, alt, voz))
    notas.append((EIXO, 1.5, TUTTI["Violino I"], "Violino I"))
    return sorted(notas), v8, k, a, b


def conferir_pi(notas: list[Nota], dig: str) -> str:
    """Lida como o conferir_digitos: oitava do eixo desfeita, dobra lida na dona, pi espelhado."""
    digito = {alt: c for c, alt in MAPEAMENTO.items()}
    por_tick: dict[float, list[tuple[int, str]]] = {}
    for t, _, alt, voz in notas:
        por_tick.setdefault(t, []).append((alt - OITAVA.get(str(int(t)), 0) if t == int(t) else alt, voz))
    lida = ""
    for t in sorted(por_tick):
        grupo = por_tick[t]
        if len({alt % 12 for alt, _ in grupo}) > 1:
            raise SystemExit(f"classes diferentes no tempo {t}")
        dona = "Flauta" if 40 <= t < 72 else "Violino I"
        lida += digito[next((alt for alt, voz in grupo if voz == dona), grupo[0][0])]
    ida = lida[:len(lida) // 2]
    if ida != dig[:len(ida)] or lida != lida[::-1]:
        raise SystemExit(f"a melodia não é pi espelhado:\n  lida {lida}\n  pi   {dig[:len(ida)]}")
    return lida


def teto(notas: list[Nota], ini: float, fim: float, padrao: int = TETO) -> int:
    """A nota mais grave da melodia que soa em [ini, fim): o acompanhamento não passa dela."""
    return min([alt for t, d, alt, _ in notas if t < fim and t + d > ini] + [padrao])


def fora_do_silencio(ini: float, fim: float, t0: float = C14[0], t1: float = RETOMA) -> list[tuple[float, float]]:
    """O trecho [ini, fim) sem o c14, o eixo e o sussurro, que têm escrita própria."""
    return [(a, b) for a, b in ((ini, min(fim, t0)), (max(ini, t1), fim)) if a < b]


def voicings(nome: str, lo: int, hi: int) -> list[tuple[int, ...]]:
    """4 notas do acorde em [lo, hi]; quando a melodia aperta o teto e não cabem 4, cabem 3."""
    cls = ACORDES[nome][1]
    alturas = [a for a in range(lo, hi + 1) if a % 12 in cls]
    for n in (4, 3):
        cands = [c for c in combinations(alturas, n) if {a % 12 for a in c} == cls]
        if cands:
            return cands
    raise SystemExit(f"sem voicing de {nome} em [{lo}, {hi}]")


def piano(acordes: list[str], graves: list[int], notas: list[Nota]) -> list[Evento]:
    """O arpejo da v8 abaixo da melodia, calado no c14 e no sussurro, em bloco no eixo."""
    ev: list[Evento] = []
    anterior = None
    for h in range(MEIOS - 1):
        t, fim = 2 * h, (FIM if h == MEIOS - 2 else 2 * h + 2)
        if t == EIXO:
            ev += [(t, 2, alt, VEL_TUTTI["Piano"]) for alt in TUTTI_PIANO]
            continue
        if not fora_do_silencio(t, fim):
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
        ev += [(t + k / 2, fim - t - k / 2, alt, vel("Piano", t)) for k, alt in enumerate(v)]
    for ini, fim, (_, pc) in trechos(list(zip(acordes, graves)), por_compasso=True):
        fim = min(fim, FIM)
        if ini == EIXO:
            continue                            # o baixo do eixo está no bloco
        grave = next(a for a in range(26, 38) if a % 12 == pc)
        for a, b in fora_do_silencio(ini, fim):
            ev += [(a, b - a, grave, vel("Piano", a)), (a, b - a, grave + 12, vel("Piano", a))]
    return ev


def violoncelo(graves: list[int]) -> list[Evento]:
    """O baixo da v8. No c14 ele fica sozinho com a flauta, e volta em sussurro no 58."""
    t0, t1 = (ENTRADA["Violoncelo"] - 1) * COMPASSO, (29 - ENTRADA["Violoncelo"]) * COMPASSO
    ev = []
    for ini, fim, pc in trechos(graves, por_compasso=True):
        if not t0 <= ini < t1:
            continue
        alt = next(a for a in range(38, 50) if a % 12 == pc)
        if ini == EIXO:
            ev += [(ini, 1.5, TUTTI["Violoncelo"], VEL_TUTTI["Violoncelo"]),
                   (58, fim - 58, alt, round(SUSSURRO * vel("Violoncelo", 58)))]
        else:
            ev.append((ini, fim - ini, alt, vel("Violoncelo", ini)))
    return ev


def pad(voz: str, acordes: list[str], notas: list[Nota], outra: list[Evento]) -> list[Evento]:
    """O pad da v8, uma quinta mais grave e sempre abaixo da melodia, com a nota do tutti no eixo."""
    lo, hi = TESSITURA_DO_PAD[voz]
    t0, t1 = (ENTRADA[voz] - 1) * COMPASSO, (29 - ENTRADA[voz]) * COMPASSO
    anterior = (lo + hi) // 2
    ev = []
    for ini_h, fim_h, nome in trechos(acordes, por_compasso=False):
        for ini, fim in fora_do_silencio(max(ini_h, t0), min(fim_h, t1)):
            cls = ACORDES[nome][1]
            mel = {alt % 12 for i, d, alt, _ in notas if i < fim and i + d > ini}
            out = {alt % 12 for i, d, alt, _ in outra if i < fim and i + d > ini}
            cands = [a for a in range(lo, min(hi, teto(notas, ini, fim)) + 1) if a % 12 in cls]
            for extra in (mel | out, out, set()):
                boas = [a for a in cands if all((a - q) % 12 not in (1, 11) for q in cls | extra)]
                if boas:
                    break
            else:
                boas = cands
            escolhida = min(boas, key=lambda a: (abs(a - anterior), a))
            ev.append((ini, fim - ini, escolhida, vel(voz, ini)))
            anterior = escolhida
    ev.append((EIXO, 1.5, TUTTI[voz], VEL_TUTTI[voz]))
    return sorted(ev)


def compor(dig: str):
    notas, v8, k, a, b = melodia_v9(dig)
    lida = conferir_pi(notas, dig)
    acordes = harmonizar(v8)
    graves = baixos(acordes)
    viola = pad("Viola", acordes, notas, [])

    def voz(nome: str) -> list[Evento]:
        ev = articular([n for n in notas if n[3] == nome], nome)
        return [(t, d, alt, round(SUSSURRO * v) if EIXO < t < RETOMA else v) for t, d, alt, v in ev]

    partes = {
        "Violino I": voz("Violino I"),
        "Flauta": voz("Flauta"),
        "Viola": viola,
        "Violino II": pad("Violino II", acordes, notas, viola),
        "Violoncelo": violoncelo(graves),
        "Piano": piano(acordes, graves, notas),
    }
    return partes, acordes, graves, k, a, b, lida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="build/v9")
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
    expressivo = expressao.aplicar(mido.MidiFile(str(midi)))
    expressivo.save(str(midi))
    numeros = expressao.resumo(expressivo)
    Path(f"{saida}-mapeamento.json").write_text(json.dumps({
        "mapeamento": MAPEAMENTO, "oitava": OITAVA, "digitos": {"A": a, "B": b, "A'": a[::-1]},
        "liquidacao_k": k, "melodia_lida": lida, "compasso": f"{COMPASSO}/4",
        "andamento_bpm": numeros["mediana_bpm"],
        "acordes_por_meio_compasso": acordes[:MEIOS - 2] + ["D", "D"], "baixo_por_meio_compasso": graves,
        "secoes": {"A": [2, 9], "B": [11, 18], "A'": [20, 27]}, "cc7": CC7,
    }, ensure_ascii=False, indent=1))
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
