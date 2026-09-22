"""Oráculo da versão 5 - a harmonia revista. Mede um MIDI (e o MP3 ao lado).

Uso: python src/avaliar_v5.py build/v5.mid
Sai 0 se os dez passarem; imprime uma linha por critério com PASS/FAIL e o número.

O pedido do dono, 21/09/2026, depois de ouvir a v4: "não tô achando muito
harmoniosas as notas, vamos revisar toda a harmonia. estude Villa-Lobos", e em
seguida "3:14 ficou muito, pode ser 1:41", e a análise do "Song from π!" do
aSongScout (vídeo z7vovDiPjW4 e a partitura dele). Nas perguntas, o dono decidiu:
  - o mapeamento do aSongScout, Lá menor harmônico: 7 = Sol#5 e 0 = Sol#4, abaixo
    do 1, em vez de pausa (fecha a parte da P2 sobre o 7, o 8, o 9 e o 0);
  - o espelho fica só na melodia: pi vai e volta no violino I, e a harmonia é
    escrita para a frente nas duas metades, para toda cadência resolver.

O que a partitura do aSongScout mostra, compassos 9 a 12 (lidos no PDF): um
acorde por compasso ou por meio compasso, nunca por tempo; a nota da melodia pode
ficar fora do acorde, como nona, sexta ou décima primeira sobre o acorde parado;
Mi maior com Sol# resolvendo em Lá menor. A v4 fazia o contrário: um acorde por
tempo, para que toda nota coubesse nele (89 trocas em 144 tempos).

O estudo de Villa-Lobos (vault, pesquisas/villa-lobos-harmonia/relatorio.md)
aponta na mesma direção: ritmo harmônico lento contra melodia rápida [4], acordes
de sétima e de nona que abraçam mais graus da escala sem trocar de acorde [5],
pedal no baixo [1][2][4] e quintas descendentes quando for preciso trocar [1].
Por isso o vocabulário do critério 6 aceita sétimas e nonas, e um pedal de Lá ou
de Mi sob os acordes da tonalidade continua formando acorde de terças.

Os dez critérios (congelados antes de existir o compositor da v5):
 1. dígitos     o violino I, até o eixo, lê os N primeiros dígitos de pi no
                mapeamento novo, com os zeros, e N >= 60
 2. espelho     toda nota do violino I tem espelho, com a mesma altura, no eixo, e
                o eixo é o meio da peça (tolerância de 3 ms)
 3. duração     o som vai de 0 a 101,00 s no MIDI (tolerância de 50 ms), e o MP3
                dura 101,0 s (tolerância de 150 ms), com pelo menos 96 s de som
 4. circular    as classes de altura dos dois primeiros tempos são as dos dois
                últimos, e formam o acorde de Lá menor
 5. tessitura   igual à v3: as seis vozes presentes, toda nota na tessitura
 6. harmonia    em >= 95% dos meios compassos, o piano forma um acorde só, de
                terças (tríade, sétima ou nona); e o acorde muda em no máximo
                metade das divisas de meio compasso
 7. melodia     no tempo 1 e no tempo 3, onde o violino I ataca, a nota dele é
                do acorde do piano em >= 75% das vezes
 8. resolução   todo acorde de dominante (com Sol# e Si) segue para um acorde de
                Lá ou de Fá, há pelo menos 4 dominantes que vão para Lá, e a
                última troca da peça é dominante -> Lá
 9. roda        >= 30% das trocas de acorde descem uma quinta justa, com >= 5
                fundamentais diferentes e >= 12 trocas
10. sem nona menor  no começo de cada tempo, nenhuma nota soa um semitom acima de
                outra (segunda menor ou nona menor) em >= 95% dos tempos; e,
                amostrado a cada 50 ms, isso acontece em no máximo 5% do tempo

Rodado contra a v4 antes de congelar, cinco nascem verdes nela: espelho,
circular, tessitura, melodia e sem nona menor. Esses são guarda, não aceite: a v4
já era consonante, e o 7 e o 10 existem para que a liberdade nova (nota fora do
acorde, acorde parado por mais tempo) não traga a aspereza de volta. O aceite
desta versão são o 1 (mapeamento novo), o 3 (1:41), o 6, o 8 e o 9.

O 10 é mais frouxo que a consonância da v4 de propósito: a sétima maior (Si da
melodia sobre o Dó do acorde) passa, porque é cor e está na peça do aSongScout;
a nona menor (Fá da melodia sobre o Mi do acorde) é a que arranha, e não passa.

A janela da harmonia é o meio compasso, e isso agora é possível porque o espelho
saiu da harmonia: o compasso é 4/4 a partir do tempo 0, e o meio compasso são os
tempos 1-2 e 3-4. "Soar" continua sendo sobrepor a janela por mais de 3 ms.

ANTIORÁCULO - como eu passaria nisto sem fazer o trabalho
---------------------------------------------------------
  trocar de acorde a cada tempo, como a v4 .. o 6 limita as trocas a metade das
                                               divisas, e o meio compasso com dois
                                               acordes não forma um acorde só
  o piano parado em Ré menor, que não
    tem nota a evitar ....................... o 8 exige 4 cadências em Lá, e o 9,
                                               12 trocas e 5 fundamentais
  cadência de trás para frente .............. o 8 exige que toda dominante vá para
                                               a frente, para Lá ou Fá
  acorde que ignora a melodia ............... o 7 exige a nota do tempo forte
                                               dentro do acorde em 75% das vezes
  pi só na ida .............................. o 2 exige o retrógrado no violino I
  consonância por silêncio .................. o 3 exige 96 s de som
  a melodia escondida no grave para não
    raspar no acorde ........................ o 1 fixa a altura de cada dígito

O que este oráculo NÃO mede: se ficou harmonioso ao ouvido do dono, que é o
pedido; se lembra Villa-Lobos; e o som depois da síntese (a reverberação no WAV
prolonga cada acorde sobre o seguinte). Os três ficam UNKNOWN até o dono ouvir o
MP3. Também não conta quintas e oitavas paralelas.

Os utilitários vêm do avaliar_v3.py e do avaliar_v4.py, que estão congelados; os
hashes deles entram junto no congelamento deste.
"""

from __future__ import annotations

import sys
from pathlib import Path

from avaliar_v3 import (LIDER, TESSITURA, TOL, TOL_MIDI, TOL_MP3, duracao_do_arquivo,
                        extremos, primeira_metade, segundos_de_som, vozes_de)
from avaliar_v4 import classes, soando, tempos
from pi_digitos import digitos_de_pi

DURACAO = 101.0            # 1 min 41 s
SOM_MINIMO = 96.0
MINIMO_DE_DIGITOS = 60
MAPEAMENTO = {"0": 68, "1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77,
              "7": 80, "8": 81, "9": 83}
PISO_ACORDE = 0.95
TETO_TROCAS = 0.50
PISO_MELODIA = 0.75
MINIMO_DE_CADENCIAS = 4
PISO_QUINTAS = 0.30
MINIMO_DE_FUNDAMENTAIS = 5
MINIMO_DE_TROCAS = 12
PISO_TEMPOS = 0.95
TETO_AMOSTRAS = 0.05
AMOSTRA = 0.05             # segundos
LA, FA = 9, 5

# Acordes de terças, em intervalos a partir da fundamental.
TIPOS = {"": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6),
         "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11),
         "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9),
         "9": (0, 4, 7, 10, 2), "m9": (0, 3, 7, 10, 2), "maj9": (0, 4, 7, 11, 2),
         "add9": (0, 4, 7, 2), "madd9": (0, 3, 7, 2)}


def acorde(cls: set[int]) -> tuple[int, str] | None:
    """(fundamental, tipo) se as classes de altura forem um acorde de terças."""
    for r in sorted(cls):
        for tipo, iv in TIPOS.items():
            if cls == {(r + i) % 12 for i in iv}:
                return r, tipo
    return None


def dominante(cls: set[int]) -> bool:
    return {8, 11} <= cls          # Sol# e Si: Mi, Mi7, Sol#dim, Sol#dim7


def meios(midi: Path, fim: float) -> list[tuple[float, float]]:
    b = tempos(midi, fim)
    return [(b[k], b[min(k + 2, len(b) - 1)]) for k in range(0, len(b) - 1, 2)]


def harmonia_do_piano(vozes, midi: Path, fim: float):
    """Uma entrada por meio compasso: (início, fim, classes, acorde ou None)."""
    piano = vozes.get("Piano", [])
    saida = []
    for a, b in meios(midi, fim):
        cls = classes(piano, a, b)
        saida.append((a, b, cls, acorde(cls) if cls else None))
    return saida


def trocas_de(harm) -> list[tuple[set[int], set[int]]]:
    seq = [h[2] for h in harm if h[2]]
    return [(x, y) for x, y in zip(seq, seq[1:]) if x != y]


def nona_menor(alturas: set[int]) -> bool:
    return any((b - a) % 12 == 1 for a in alturas for b in alturas if b > a)


def criterio_digitos(vozes, ini, fim, mp3) -> tuple[bool, str]:
    inverso = {a: d for d, a in MAPEAMENTO.items()}
    lidos = "".join(inverso.get(n[2], "?")
                    for n in primeira_metade(vozes.get(LIDER, []), (ini + fim) / 2))
    esperado = digitos_de_pi(max(len(lidos), 10))[:len(lidos)]
    if lidos == esperado and len(lidos) >= MINIMO_DE_DIGITOS:
        return True, f"{len(lidos)} notas lidas, iguais aos {len(lidos)} primeiros dígitos de pi"
    i = next((k for k, (a, b) in enumerate(zip(lidos, esperado)) if a != b), len(lidos))
    return False, f"{len(lidos)} notas lidas (mínimo {MINIMO_DE_DIGITOS}); divergem de pi na posição {i + 1}"


def criterio_espelho(vozes, ini, fim, mp3) -> tuple[bool, str]:
    lider = vozes.get(LIDER, [])
    if not lider:
        return False, "sem violino I"
    eixo = (ini + fim) / 2
    sem_par = [n for n in lider
               if not any(m[2] == n[2] and abs(m[0] - (2 * eixo - n[1])) <= TOL
                          and abs(m[1] - (2 * eixo - n[0])) <= TOL for m in lider)]
    centro = (lider[0][0] + lider[-1][1]) / 2
    ok = not sem_par and abs(centro - eixo) <= TOL
    return ok, (f"{len(lider) - len(sem_par)} de {len(lider)} notas com espelho no eixo "
                f"{eixo:.2f} s; a melodia vai de {lider[0][0]:.2f} a {lider[-1][1]:.2f} s")


def criterio_duracao(vozes, ini, fim, mp3) -> tuple[bool, str]:
    ok_midi = abs(ini) <= TOL_MIDI and abs(fim - DURACAO) <= TOL_MIDI
    texto = f"MIDI de {ini:.3f} a {fim:.3f} s"
    if not mp3.exists():
        return False, texto + "; sem MP3"
    total = duracao_do_arquivo(mp3)
    som = segundos_de_som(mp3, total)
    ok = ok_midi and abs(total - DURACAO) <= TOL_MP3 and som >= SOM_MINIMO
    return ok, texto + f"; MP3 de {total:.3f} s, {som:.1f} s de som"


def criterio_circular(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    todas = [n for ns in vozes.values() for n in ns]
    abre, fecha = classes(todas, b[0], b[2]), classes(todas, b[-3], b[-1])
    ok = abre == fecha and acorde(abre) == (LA, "m")
    return ok, f"abre com {sorted(abre)}, fecha com {sorted(fecha)}, acorde {acorde(fecha)}"


def criterio_tessitura(vozes, ini, fim, mp3) -> tuple[bool, str]:
    faltam = [n for n in TESSITURA if n not in vozes]
    fora = [(nome, n[2]) for nome, ns in vozes.items() if nome in TESSITURA
            for n in ns if not TESSITURA[nome][0] <= n[2] <= TESSITURA[nome][1]]
    if faltam:
        return False, f"faltam as vozes: {', '.join(faltam)}"
    return not fora, f"{len(fora)} notas fora da tessitura" + (f", a primeira {fora[0]}" if fora else "")


def criterio_harmonia(vozes, ini, fim, mp3) -> tuple[bool, str]:
    harm = harmonia_do_piano(vozes, mp3.with_suffix(".mid"), fim)
    com_acorde = sum(h[3] is not None for h in harm) / len(harm)
    divisas = sum(1 for x, y in zip(harm, harm[1:]) if x[2] and y[2])
    fracao = len(trocas_de(harm)) / divisas if divisas else 1.0
    ok = com_acorde >= PISO_ACORDE and fracao <= TETO_TROCAS
    return ok, (f"um acorde de terças em {com_acorde:.0%} de {len(harm)} meios compassos; "
                f"troca em {fracao:.0%} das divisas")


def criterio_melodia(vozes, ini, fim, mp3) -> tuple[bool, str]:
    harm = harmonia_do_piano(vozes, mp3.with_suffix(".mid"), fim)
    lider = vozes.get(LIDER, [])
    dentro = total = 0
    for a, b, cls, _ in harm:
        ataque = [n for n in lider if abs(n[0] - a) <= TOL]
        if ataque:
            total += 1
            dentro += ataque[0][2] % 12 in cls
    fracao = dentro / total if total else 0.0
    return fracao >= PISO_MELODIA, f"nota do tempo forte dentro do acorde em {fracao:.0%} de {total}"


def criterio_resolucao(vozes, ini, fim, mp3) -> tuple[bool, str]:
    harm = harmonia_do_piano(vozes, mp3.with_suffix(".mid"), fim)
    seq = [h[2] for h in harm]
    ruins = cadencias = 0
    for i, cls in enumerate(seq):
        if not dominante(cls) or (i + 1 < len(seq) and dominante(seq[i + 1])):
            continue
        prox = seq[i + 1] if i + 1 < len(seq) else set()
        raiz = acorde(prox)[0] if acorde(prox) else None
        cadencias += raiz == LA
        ruins += raiz not in (LA, FA)
    trocas = trocas_de(harm)
    fecha = bool(trocas) and dominante(trocas[-1][0]) and (acorde(trocas[-1][1]) or (None,))[0] == LA
    ok = ruins == 0 and cadencias >= MINIMO_DE_CADENCIAS and fecha
    return ok, (f"{cadencias} dominantes vão para Lá, {ruins} vão para outro lugar; "
                f"a última troca {'é' if fecha else 'não é'} dominante -> Lá")


def criterio_roda(vozes, ini, fim, mp3) -> tuple[bool, str]:
    harm = harmonia_do_piano(vozes, mp3.with_suffix(".mid"), fim)
    raizes = [acorde(y)[0] if acorde(y) else None for _, y in trocas_de(harm)]
    primeira = next((h[2] for h in harm if h[2]), set())
    raizes = [acorde(primeira)[0] if acorde(primeira) else None] + raizes
    pares = [(a, b) for a, b in zip(raizes, raizes[1:]) if a is not None and b is not None]
    quintas = sum((b - a) % 12 == 5 for a, b in pares)
    fracao = quintas / len(pares) if pares else 0.0
    diferentes = len({r for r in raizes if r is not None})
    ok = fracao >= PISO_QUINTAS and diferentes >= MINIMO_DE_FUNDAMENTAIS and len(pares) >= MINIMO_DE_TROCAS
    return ok, f"{quintas} de {len(pares)} trocas descem uma quinta ({fracao:.0%}); {diferentes} fundamentais"


def criterio_nona(vozes, ini, fim, mp3) -> tuple[bool, str]:
    bordas = tempos(mp3.with_suffix(".mid"), fim)[:-1]
    limpos = sum(not nona_menor(soando(vozes, a + 0.01)) for a in bordas) / len(bordas)
    amostras = [ini + k * AMOSTRA for k in range(int((fim - ini) / AMOSTRA))]
    sujas = sum(nona_menor(soando(vozes, t)) for t in amostras) / len(amostras)
    ok = limpos >= PISO_TEMPOS and sujas <= TETO_AMOSTRAS
    return ok, (f"começo do tempo sem nona menor em {limpos:.0%} de {len(bordas)}; "
                f"nona menor soando em {sujas:.0%} do tempo")


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: avaliar_v5.py <arquivo.mid>")
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
    criterios = [("dígitos", criterio_digitos), ("espelho", criterio_espelho),
                 ("duração", criterio_duracao), ("circular", criterio_circular),
                 ("tessitura", criterio_tessitura), ("harmonia", criterio_harmonia),
                 ("melodia", criterio_melodia), ("resolução", criterio_resolucao),
                 ("roda", criterio_roda), ("sem nona menor", criterio_nona)]
    passou = 0
    for nome, fn in criterios:
        try:
            ok, detalhe = fn(vozes, ini, fim, midi.with_suffix(".mp3"))
        except Exception as e:
            ok, detalhe = False, f"erro: {e}"
        passou += ok
        print(f"{'PASS' if ok else 'FAIL'}  {nome:<15} {detalhe}")
    print(f"{passou}/{len(criterios)} critérios")
    return 0 if passou == len(criterios) else 1


if __name__ == "__main__":
    sys.exit(main())
