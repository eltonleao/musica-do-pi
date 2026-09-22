"""Oráculo da versão 4 - o círculo, consonante. Mede um MIDI (e o MP3 ao lado).

Uso: python src/avaliar_v4.py build/v4.mid
Sai 0 se os oito passarem; imprime uma linha por critério com PASS/FAIL e o número.

O pedido do dono, 21/09/2026, depois de ouvir a v3 e o "Song from π!" do
aSongScout: "a progressão do piano dele tá muito mais bonita que a nossa, a
nossa está tensa demais, pode usar a quantidade de notas que quiser, não
precisa mais ser 314, só precisa ter 3:14". Na pergunta seguinte, escolheu tirar
o cânone: ficam o palíndromo e a forma circular, e a roda passa para a harmonia,
andando pelo círculo das quintas.

Os oito critérios (congelados antes de existir o compositor da v4). Os cinco
primeiros vêm da v3 e já passam nela: são guarda, não aceite. O aceite desta
versão são o 6, o 7 e o 8.
 1. dígitos     o violino I, na primeira metade, lê um prefixo de pi sem os
                zeros, com pelo menos 100 notas
 2. duração     igual à v3: 194,00 s no MIDI, 194,0 s no MP3, 184 s de som
 3. palíndromo  igual à v3
 4. circular    igual à v3
 5. tessitura   igual à v3: as seis vozes presentes, toda nota na tessitura
 6. harmonia    em cada tempo, as notas do piano que soam formam exatamente uma
                tríade maior ou menor, em >= 95% dos tempos; e o violino I, onde
                soa, está dentro dessa tríade em >= 95% dos tempos
 7. roda        na primeira metade, >= 30% das trocas de acorde descem uma quinta
                justa (Lá m -> Ré m -> Sol -> Dó -> Fá ...), com >= 5 acordes
                diferentes e >= 20 trocas
 8. consonância no começo de cada tempo, o que soa (todas as vozes) não tem
                segunda menor, sétima maior nem trítono em >= 95% dos tempos; e,
                amostrado a cada 50 ms na peça inteira, o que soa tem segunda
                menor ou sétima maior em no máximo 5% das amostras

A janela é o tempo, não o meio compasso, e isso é consequência do palíndromo:
o retrógrado de uma janela de dois tempos troca os dois tempos de lugar, e a
nota do tempo fraco, que pode ser de passagem, cai no tempo forte da segunda
metade. Com a janela de um tempo, o espelho leva cada tempo inteiro, com o seu
acorde, para um tempo inteiro. "Soar" é sobrepor a janela por mais de 3 ms, e
não atacar nela, porque o espelho transforma o fim de uma nota em ataque.

ANTIORÁCULO - como eu passaria nisto sem fazer o trabalho
---------------------------------------------------------
  o piano num Lá m só, a peça inteira ....... a melodia de pi cai fora do acorde
                                               (critério 6), e a roda exige 20
                                               trocas e 5 acordes (7)
  consonância por silêncio .................. o MP3 precisa de 184 s de som, e o
                                               violino I de 100 notas
  consonância com tudo em uníssono .......... o piano tem de soar uma tríade em
                                               cada tempo
  quintas descendentes só no começo ......... a fração é da primeira metade
                                               inteira, não de um trecho
  tensão escondida entre os tempos .......... a amostra de 50 ms cobre o tempo
                                               todo, não só o começo de cada tempo
  a melodia calada para caber no acorde ..... o critério 1 exige que o violino I
                                               leia pi, e o 6 conta os tempos em
                                               que ele soa

O que este oráculo NÃO mede: se a progressão é tão bonita quanto a do
aSongScout, e se a peça deixou de soar tensa. As duas coisas são do ouvido do
dono e ficam UNKNOWN até ele ouvir. Os critérios 6 a 8 são a régua que dá para
conferir por máquina, não o juízo. Também não mede o som depois da síntese: a
reverberação no WAV prolonga cada acorde sobre o seguinte, e isso não está no MIDI.

Os utilitários e os critérios herdados são importados do avaliar_v3.py, que
está congelado; o hash dele entra junto no congelamento deste.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mido

from avaliar_v3 import (LIDER, MAPEAMENTO, TOL, criterio_circular, criterio_duracao,
                        criterio_palindromo, criterio_tessitura, extremos,
                        primeira_metade, relogio, vozes_de)
from pi_digitos import digitos_de_pi

MINIMO_DE_DIGITOS = 100
PISO_HARMONIA = 0.95
PISO_QUINTAS = 0.30
MINIMO_DE_ACORDES = 5
MINIMO_DE_TROCAS = 20
PISO_TEMPOS = 0.95
TETO_SEGUNDAS = 0.05
AMOSTRA = 0.05             # segundos
ASPERAS_TEMPO = {1, 6}     # segunda menor/sétima maior e trítono
ASPERAS_AMOSTRA = {1}


def tempos(midi: Path, fim: float) -> list[float]:
    """Bordas de cada tempo, em segundos, lidas do andamento do próprio MIDI."""
    arq = mido.MidiFile(str(midi))
    seg = relogio(arq)
    saida, k = [], 0
    while seg(k * arq.ticks_per_beat) < fim - TOL:
        saida.append(seg(k * arq.ticks_per_beat))
        k += 1
    return saida + [fim]


def classes(notas, a: float, b: float) -> set[int]:
    return {n[2] % 12 for n in notas if n[0] < b - TOL and n[1] > a + TOL}


def asperas(alturas: set[int], quais: set[int]) -> bool:
    cls = sorted({a % 12 for a in alturas})
    return any(min((b - a) % 12, (a - b) % 12) in quais for i, a in enumerate(cls) for b in cls[i + 1:])


def triade(cls: set[int]) -> int | None:
    """Fundamental, se as classes de altura forem exatamente uma tríade maior ou menor."""
    if len(cls) != 3:
        return None
    for r in cls:
        if cls in ({r, (r + 4) % 12, (r + 7) % 12}, {r, (r + 3) % 12, (r + 7) % 12}):
            return r
    return None


def soando(vozes, t: float) -> set[int]:
    return {n[2] for ns in vozes.values() for n in ns if n[0] <= t < n[1]}


def acordes(vozes, bordas: list[float]) -> list[int | None]:
    piano = vozes.get("Piano", [])
    return [triade(classes(piano, a, b)) for a, b in zip(bordas, bordas[1:])]


def criterio_digitos(vozes, ini, fim, mp3) -> tuple[bool, str]:
    inverso = {a: d for d, a in MAPEAMENTO.items() if a is not None}
    lidos = "".join(inverso.get(n[2], "?")
                    for n in primeira_metade(vozes.get(LIDER, []), (ini + fim) / 2))
    esperado = digitos_de_pi(max(len(lidos) * 2, 10)).replace("0", "")[:len(lidos)]
    if lidos == esperado and len(lidos) >= MINIMO_DE_DIGITOS:
        return True, f"{len(lidos)} notas lidas, iguais ao começo de pi sem os zeros"
    i = next((k for k, (a, b) in enumerate(zip(lidos, esperado)) if a != b), len(lidos))
    return False, f"{len(lidos)} notas lidas (mínimo {MINIMO_DE_DIGITOS}); divergem de pi na posição {i + 1}"


def criterio_harmonia(vozes, ini, fim, mp3) -> tuple[bool, str]:
    bordas = tempos(mp3.with_suffix(".mid"), fim)
    raizes = acordes(vozes, bordas)
    com_triade = sum(r is not None for r in raizes) / len(raizes)
    lider = vozes.get(LIDER, [])
    dentro = total = 0
    for a, b, r in zip(bordas, bordas[1:], raizes):
        canto = classes(lider, a, b)
        if canto:
            total += 1
            dentro += r is not None and canto <= classes(vozes["Piano"], a, b)
    na_triade = dentro / total if total else 0.0
    ok = com_triade >= PISO_HARMONIA and na_triade >= PISO_HARMONIA
    return ok, (f"tríade no piano em {com_triade:.0%} de {len(raizes)} tempos; "
                f"violino I dentro dela em {na_triade:.0%} de {total}")


def criterio_roda(vozes, ini, fim, mp3) -> tuple[bool, str]:
    bordas = tempos(mp3.with_suffix(".mid"), fim)
    meio = (ini + fim) / 2
    raizes = [r for a, r in zip(bordas, acordes(vozes, bordas)) if a < meio - TOL and r is not None]
    seq = [r for i, r in enumerate(raizes) if i == 0 or r != raizes[i - 1]]
    trocas = list(zip(seq, seq[1:]))
    quintas = sum((b - a) % 12 == 5 for a, b in trocas)
    fracao = quintas / len(trocas) if trocas else 0.0
    ok = fracao >= PISO_QUINTAS and len(set(seq)) >= MINIMO_DE_ACORDES and len(trocas) >= MINIMO_DE_TROCAS
    return ok, f"{quintas} de {len(trocas)} trocas descem uma quinta ({fracao:.0%}); {len(set(seq))} acordes diferentes"


def criterio_consonancia(vozes, ini, fim, mp3) -> tuple[bool, str]:
    bordas = tempos(mp3.with_suffix(".mid"), fim)[:-1]
    limpos = sum(not asperas(soando(vozes, a + 0.01), ASPERAS_TEMPO) for a in bordas) / len(bordas)
    amostras = [ini + k * AMOSTRA for k in range(int((fim - ini) / AMOSTRA))]
    segundas = sum(asperas(soando(vozes, t), ASPERAS_AMOSTRA) for t in amostras) / len(amostras)
    ok = limpos >= PISO_TEMPOS and segundas <= TETO_SEGUNDAS
    return ok, (f"começo do tempo sem segunda nem trítono em {limpos:.0%} de {len(bordas)}; "
                f"segunda menor soando em {segundas:.0%} do tempo")


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: avaliar_v4.py <arquivo.mid>")
        return 2
    midi = Path(sys.argv[1])
    if not midi.exists():
        print(f"ausente: {midi}")
        return 2
    vozes = vozes_de(midi)
    if not vozes:
        print("nenhuma nota audível")
        return 1
    ini, fim = extremos(vozes)
    criterios = [("dígitos", criterio_digitos), ("duração", criterio_duracao),
                 ("palíndromo", criterio_palindromo), ("circular", criterio_circular),
                 ("tessitura", criterio_tessitura), ("harmonia", criterio_harmonia),
                 ("roda", criterio_roda), ("consonância", criterio_consonancia)]
    passou = 0
    for nome, fn in criterios:
        try:
            ok, detalhe = fn(vozes, ini, fim, midi.with_suffix(".mp3"))
        except Exception as e:
            ok, detalhe = False, f"erro: {e}"
        passou += ok
        print(f"{'PASS' if ok else 'FAIL'}  {nome:<12} {detalhe}")
    print(f"{passou}/{len(criterios)} critérios")
    return 0 if passou == len(criterios) else 1


if __name__ == "__main__":
    sys.exit(main())
