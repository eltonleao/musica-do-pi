"""Oráculo da versão 6: a Sonata ao Luar e o Bach matemático sobre os dígitos de pi.

Pedido do dono, 21/09/2026: "elabora um /plano /pesquisar moonlight sonata
beethoven e peças matemáticas de bach [...] composição inspirada em bach e
beethoven respeitando as leis matemáticas do pi. precisa ficar não apenas
matemático mas também agradável aos ouvidos e à mente". Decisões dele no
brainstorming: "Eco permitido", "Ritmo fixo e harmonia por dígito", "Arco:
regra, eixo humano, pedal, volta". O desenho e as réguas estão em
Projects/Música do Pi/analysis/v6-desenho.md, no vault; o plano é o P9.

Escrito e congelado (build/v6-oraculo.sha256) antes de src/v6.py existir. O
RED roda contra build/v5.mid; o GREEN, contra build/v6.mid.

O acompanhamento é tudo menos o violino I e a flauta. A mão direita do piano é
altura >= 50; a esquerda, < 50. As seções são as do desenho: A = compassos
1-14, B = 15-24, A' = 25-38.

  1. dígitos      a ida do violino I, agrupada por compasso, com compassos
                  consecutivos idênticos colapsados (o eco), lida pelo
                  mapeamento inverso: 60 dígitos ou mais, iguais aos de pi
  2. espelho      toda nota do violino I tem par em altura e tempo no eixo
                  (critério do avaliar_v5.py)
  3. duração      MIDI de 101 s; MP3 de 101 +- 0,15 s com 96 s de som
                  (critério do avaliar_v5.py)
  4. circular     o acompanhamento soa exatamente {Lá, Dó, Mi} nos dois
                  primeiros e nos dois últimos tempos
  5. tessitura    as seis vozes presentes, todas na tessitura do avaliar_v3.py
                  (critério do avaliar_v5.py)
  6. sol#         todo Sol# do violino I cai em tempo cujo acompanhamento
                  contém Mi: zero exceções
  7. tempo forte  nota do violino I que começa nos tempos 1 e 3 pertence ao
                  acompanhamento do meio compasso: 90% ou mais
  8. nona menor   notas do violino I de um tempo ou mais que soam um semitom
                  acima de nota do acompanhamento sem serem dele: 10% ou menos
  9. V -> i       saídas de acorde de Mi (E, E7, E7b9) vão para Lá menor em 90%
                  ou mais, com 3 saídas no mínimo
 10. vocabulário  acordes distintos reconhecidos no acompanhamento, por meio
                  compasso: 10 ou menos, e nenhum meio compasso sem acorde
 11. napolitano   um meio compasso {Si b, Ré, Fá} nos compassos 15-24 (37,2 a
                  63,8 s), com Mi maior até dois meios compassos depois
 12. pedal        8 compassos consecutivos ou mais em que o violoncelo soa só a
                  classe Mi durante 95% do compasso
 13. figura       tempos em que as notas da mão direita repetem as do tempo
                  anterior (posição e altura): 40% ou mais
 14. baixo        ataques da mão esquerda em oitavas: 25% ou mais; ataques por
                  compasso: mediana de 2 ou menos
 15. condução     nas trocas de acorde da mão direita, soma dos deslocamentos
                  das quatro notas ordenadas: mediana de 4 semitons ou menos
 16. eco          compassos com melodia cujo vizinho é idêntico (posição,
                  duração, altura): 70% ou mais
 17. ritmo        em cada seção, compassos com melodia no padrão de ataques
                  mais comum da seção: 80% ou mais
 18. destaque     violino I 3 dB ou mais acima do violino II, da viola e do
                  violoncelo, cada voz renderizada sozinha e sem normalização,
                  nos compassos em que as duas tocam
 19. clímax       a janela de 5 s de maior RMS do MP3 tem o centro entre 42 e 60 s
 20. corte        RMS de 100,0-100,7 s no MP3 no máximo 6 dB abaixo do RMS de
                  95-100 s

ANTIORÁCULO - como eu passaria nisto sem fazer o trabalho:
  - repetir compassos à vontade para inflar o eco: o colapso só junta vizinhos
    idênticos, a leitura continua tendo de dar os dígitos de pi em ordem, e o
    espelho continua exigindo par para cada nota;
  - tirar o Sol# da melodia para passar no sol#: a melodia é conferida dígito
    a dígito pelo critério 1;
  - calar o violino II ou a viola quando o violino I toca, para o destaque não
    ter o que comparar: sem compasso em comum com o violino I, o destaque falha;
  - um acorde de Si b solto em qualquer lugar: o napolitano exige a janela do
    eixo e o Mi logo depois; a figura, o baixo e a condução medem o piano que
    existe, e não um piano declarado.

O que este oráculo NÃO mede: se a peça é agradável. Isso é o ouvido do dono, e
fica UNKNOWN até ele ouvir o MP3. Também não mede o reverb nem a partitura.

Utilitários congelados junto: avaliar_v5.py, avaliar_v4.py, avaliar_v3.py,
pi_digitos.py e renderizar.py (o render solo do critério 18).
"""

from __future__ import annotations

import bisect
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import mido
import numpy as np

from avaliar_v3 import LIDER, TOL, extremos, primeira_metade, vozes_de
from avaliar_v4 import classes, tempos
from avaliar_v5 import MAPEAMENTO, criterio_duracao, criterio_espelho, criterio_tessitura
from pi_digitos import digitos_de_pi
from renderizar import TAXA, sintetizar

MINIMO_DE_DIGITOS = 60
FLAUTA = "Flauta"
PADS = ("Violino II", "Viola", "Violoncelo")
MAO_DIREITA = 50
SECOES = {"A": (1, 14), "B": (15, 24), "A'": (25, 38)}
EIXO_DO_NAPOLITANO = (15, 24)
LA, MI = 9, 4
TONICA = {9, 0, 4}
NAPOLITANO = {10, 2, 5}
MI_MAIOR = {4, 8, 11}
FAMILIA_DE_MI = {(4, ""), (4, "7"), (4, "7b9")}
TIPOS = {"": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10),
         "maj7": (0, 4, 7, 11), "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9), "7b9": (0, 4, 7, 10, 1),
         "9": (0, 4, 7, 10, 2), "m9": (0, 3, 7, 10, 2), "maj9": (0, 4, 7, 11, 2),
         "add9": (0, 4, 7, 2), "madd9": (0, 3, 7, 2)}

PISO_TEMPO_FORTE = 0.90
TETO_NONA = 0.10
PISO_V_I = 0.90
MINIMO_DE_SAIDAS = 3
TETO_VOCABULARIO = 10
MINIMO_DE_PEDAL = 8
FRACAO_DO_PEDAL = 0.95
PISO_FIGURA = 0.40
PISO_OITAVAS = 0.25
TETO_ATAQUES = 2
TETO_CONDUCAO = 4
PISO_ECO = 0.70
PISO_RITMO = 0.80
DESTAQUE_DB = 3.0
JANELA_CLIMAX = 5.0
CLIMAX = (42.0, 60.0)
FINAL, ANTES_DO_FINAL, QUEDA_DB = (100.0, 100.7), (95.0, 100.0), 6.0
DIVISOES = 24                     # posição dentro do tempo, em 1/24 de tempo
SOUNDFONT = Path(__file__).resolve().parent.parent / "assets/soundfonts/FluidR3_GM.sf2"

_audio: dict[Path, np.ndarray] = {}


def acorde(cls: set[int]) -> tuple[int, str] | None:
    for r in sorted(cls):
        for tipo, iv in TIPOS.items():
            if cls == {(r + i) % 12 for i in iv}:
                return r, tipo
    return None


def acompanhamento(vozes) -> list:
    return [n for nome, ns in vozes.items() if nome not in (LIDER, FLAUTA) for n in ns]


def compassos(b: list[float]) -> list[tuple[float, float]]:
    return [(b[k], b[min(k + 4, len(b) - 1)]) for k in range(0, len(b) - 1, 4)]


def meios(b: list[float]) -> list[tuple[float, float]]:
    return [(b[k], b[min(k + 2, len(b) - 1)]) for k in range(0, len(b) - 1, 2)]


def indice(t: float, bordas: list[float]) -> int:
    """Índice da janela que contém o instante t (bordas = inícios das janelas)."""
    return bisect.bisect_right(bordas, t + TOL) - 1


def por_compasso(notas, b) -> dict[int, list]:
    inicios = [a for a, _ in compassos(b)]
    grupos: dict[int, list] = {}
    for n in notas:
        grupos.setdefault(indice(n[0], inicios), []).append(n)
    return grupos


def assinatura(notas, a: float, tempo: float) -> tuple:
    """Posição, duração e altura de cada nota do compasso, em 1/24 de tempo."""
    return tuple((round((n[0] - a) / tempo * DIVISOES), round((n[1] - n[0]) / tempo * DIVISOES), n[2])
                 for n in sorted(notas))


def assinaturas(notas, b) -> dict[int, tuple]:
    tempo = b[1] - b[0]
    comps = compassos(b)
    return {m: assinatura(ns, comps[m][0], tempo) for m, ns in por_compasso(notas, b).items()}


def nomes_por_meio(vozes, b) -> list[tuple[set[int], tuple[int, str] | None]]:
    acomp = acompanhamento(vozes)
    return [(cls, acorde(cls)) for cls in (classes(acomp, a, c) for a, c in meios(b))]


def figuras(vozes, b) -> list[tuple]:
    """As notas da mão direita que começam em cada tempo: (posição, altura)."""
    direita = [n for n in vozes.get("Piano", []) if n[2] >= MAO_DIREITA]
    saida: list[list] = [[] for _ in range(len(b) - 1)]
    for n in direita:
        k = indice(n[0], b[:-1])
        if 0 <= k < len(saida):
            saida[k].append((round((n[0] - b[k]) / (b[k + 1] - b[k]) * DIVISOES), n[2]))
    return [tuple(sorted(f)) for f in saida]


def pcm(mp3: Path) -> np.ndarray:
    if mp3 not in _audio:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "f32le", "-ac", "1",
                            "-ar", str(TAXA), "-"], capture_output=True, check=True)
        _audio[mp3] = np.frombuffer(r.stdout, dtype=np.float32)
    return _audio[mp3]


def rms(amostras: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(amostras, dtype=np.float64)))) if len(amostras) else 0.0


def db(x: float, y: float) -> float:
    return 20 * np.log10(max(x, 1e-12) / max(y, 1e-12))


def criterio_digitos(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    ida = primeira_metade(vozes.get(LIDER, []), (ini + fim) / 2)
    grupos, sigs = por_compasso(ida, b), assinaturas(ida, b)
    lidas, colapsados, anterior = [], 0, None
    for m in sorted(grupos):
        if anterior is not None and m == anterior + 1 and sigs[m] == sigs[anterior]:
            colapsados += 1
        else:
            lidas += sorted(grupos[m])
        anterior = m
    inverso = {a: d for d, a in MAPEAMENTO.items()}
    lidos = "".join(inverso.get(n[2], "?") for n in lidas)
    esperado = digitos_de_pi(max(len(lidos), 10))[:len(lidos)]
    if lidos == esperado and len(lidos) >= MINIMO_DE_DIGITOS:
        return True, (f"{len(lidos)} dígitos lidos, iguais aos de pi; "
                      f"{colapsados} compassos de eco colapsados")
    i = next((k for k, (x, y) in enumerate(zip(lidos, esperado)) if x != y), len(lidos))
    return False, (f"{len(lidos)} dígitos lidos (mínimo {MINIMO_DE_DIGITOS}); "
                   f"divergem de pi na posição {i + 1}")


def criterio_circular(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    acomp = acompanhamento(vozes)
    abre, fecha = classes(acomp, b[0], b[2]), classes(acomp, b[-3], b[-1])
    ok = abre == TONICA and fecha == TONICA
    return ok, f"o acompanhamento abre com {sorted(abre)} e fecha com {sorted(fecha)}"


def criterio_sol(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    acomp = acompanhamento(vozes)
    sols = [n for n in vozes.get(LIDER, []) if n[2] % 12 == 8]
    sem_mi = []
    for n in sols:
        k = indice(n[0], b[:-1])
        if MI not in classes(acomp, b[k], b[k + 1]):
            sem_mi.append(round(n[0], 2))
    detalhe = f"{len(sols) - len(sem_mi)} de {len(sols)} Sol# sobre acompanhamento com Mi"
    return not sem_mi, detalhe + (f"; o primeiro sem Mi em {sem_mi[0]} s" if sem_mi else "")


def criterio_tempo_forte(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    acomp, lider = acompanhamento(vozes), vozes.get(LIDER, [])
    dentro = total = 0
    for a, c in meios(b):
        for n in (n for n in lider if abs(n[0] - a) <= TOL):
            total += 1
            dentro += n[2] % 12 in classes(acomp, a, c)
    fracao = dentro / total if total else 0.0
    return fracao >= PISO_TEMPO_FORTE, f"{dentro} de {total} notas dos tempos 1 e 3 no acorde ({fracao:.0%})"


def criterio_nona(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    tempo = b[1] - b[0]
    acomp = acompanhamento(vozes)
    longas = [n for n in vozes.get(LIDER, []) if n[1] - n[0] >= tempo - TOL]
    nonas = []
    for n in longas:
        acc, p = classes(acomp, n[0], n[1]), n[2] % 12
        if p not in acc and (p - 1) % 12 in acc:
            nonas.append(round(n[0], 2))
    fracao = len(nonas) / len(longas) if longas else 1.0
    return (bool(longas) and fracao <= TETO_NONA,
            f"{len(nonas)} de {len(longas)} notas longas em nona menor ({fracao:.1%})"
            + (f", em {nonas[:4]} s" if nonas else ""))


def criterio_v_i(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    nomes = [nome for _, nome in nomes_por_meio(vozes, b)]
    saidas = boas = 0
    for x, y in zip(nomes, nomes[1:]):
        if x in FAMILIA_DE_MI and y not in FAMILIA_DE_MI:
            saidas += 1
            boas += y == (LA, "m")
    fracao = boas / saidas if saidas else 0.0
    ok = saidas >= MINIMO_DE_SAIDAS and fracao >= PISO_V_I
    return ok, f"{boas} de {saidas} saídas do acorde de Mi vão para Lá menor ({fracao:.0%})"


def criterio_vocabulario(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    nomes = [nome for _, nome in nomes_por_meio(vozes, b)]
    sem = sum(n is None for n in nomes)
    distintos = {n for n in nomes if n is not None}
    ok = sem == 0 and len(distintos) <= TETO_VOCABULARIO
    return ok, f"{len(distintos)} acordes distintos; {sem} de {len(nomes)} meios compassos sem acorde reconhecido"


def criterio_napolitano(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    harm = nomes_por_meio(vozes, b)
    primeiro, ultimo = EIXO_DO_NAPOLITANO
    achados = []
    for h in range(2 * (primeiro - 1), 2 * ultimo):
        if h < len(harm) and harm[h][0] == NAPOLITANO:
            depois = [harm[h + j][0] for j in (1, 2) if h + j < len(harm)]
            achados.append((h, any(MI_MAIOR <= cls for cls in depois)))
    resolvidos = [h for h, ok in achados if ok]
    if resolvidos:
        return True, (f"Si b maior em {len(achados)} meios compassos; o do compasso "
                      f"{resolvidos[-1] // 2 + 1} vai a Mi maior em até dois meios compassos")
    return False, f"Si b maior em {len(achados)} meios compassos dos compassos 15-24, nenhum seguido de Mi maior"


def criterio_pedal(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    cello = vozes.get("Violoncelo", [])
    marcas = []
    for a, c in compassos(b):
        pontos = [a + (i + 0.5) * (c - a) / 200 for i in range(200)]
        so_mi = sum({n[2] % 12 for n in cello if n[0] <= t < n[1]} == {MI} for t in pontos)
        marcas.append(so_mi / len(pontos) >= FRACAO_DO_PEDAL)
    maior = corrida = 0
    for m in marcas:
        corrida = corrida + 1 if m else 0
        maior = max(maior, corrida)
    return maior >= MINIMO_DE_PEDAL, f"{maior} compassos consecutivos de pedal de Mi no violoncelo; {sum(marcas)} no total"


def criterio_figura(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    fig = figuras(vozes, b)
    com = [k for k in range(1, len(fig)) if fig[k]]
    repete = sum(fig[k] == fig[k - 1] for k in com)
    fracao = repete / len(com) if com else 0.0
    return fracao >= PISO_FIGURA, f"a mão direita repete o tempo anterior em {repete} de {len(com)} tempos ({fracao:.0%})"


def criterio_baixo(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    esquerda = sorted(n for n in vozes.get("Piano", []) if n[2] < MAO_DIREITA)
    ataques: list[tuple[float, list[int]]] = []
    for n in esquerda:
        if ataques and abs(n[0] - ataques[-1][0]) <= TOL:
            ataques[-1][1].append(n[2])
        else:
            ataques.append((n[0], [n[2]]))
    if not ataques:
        return False, "mão esquerda sem nota"
    oitavas = sum(any(y - x == 12 for x in ps for y in ps) for _, ps in ataques)
    inicios = [a for a, _ in compassos(b)]
    conta = Counter(indice(t, inicios) for t, _ in ataques)
    mediana = statistics.median(conta.get(m, 0) for m in range(len(inicios)))
    fracao = oitavas / len(ataques)
    ok = fracao >= PISO_OITAVAS and mediana <= TETO_ATAQUES
    return ok, f"{oitavas} de {len(ataques)} ataques em oitavas ({fracao:.0%}); mediana de {mediana:g} ataques por compasso"


def criterio_conducao(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    fig = figuras(vozes, b)
    passos = []
    for k in range(1, len(fig)):
        x, y = sorted(p for _, p in fig[k - 1]), sorted(p for _, p in fig[k])
        if len(x) == 4 and len(y) == 4 and {p % 12 for p in x} != {p % 12 for p in y}:
            passos.append(sum(abs(p - q) for p, q in zip(x, y)))
    if not passos:
        return False, "nenhuma troca de acorde entre tempos de quatro notas na mão direita"
    mediana = statistics.median(passos)
    return mediana <= TETO_CONDUCAO, f"{len(passos)} trocas; deslocamento mediano de {mediana:g} semitons, o maior {max(passos)}"


def criterio_eco(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    sigs = assinaturas(vozes.get(LIDER, []), b)
    com_par = sum(sigs.get(m - 1) == s or sigs.get(m + 1) == s for m, s in sigs.items())
    fracao = com_par / len(sigs) if sigs else 0.0
    return fracao >= PISO_ECO, f"{com_par} de {len(sigs)} compassos com melodia têm vizinho idêntico ({fracao:.0%})"


def criterio_ritmo(vozes, ini, fim, mp3) -> tuple[bool, str]:
    b = tempos(mp3.with_suffix(".mid"), fim)
    sigs = assinaturas(vozes.get(LIDER, []), b)
    partes, ok = [], True
    for nome, (p, u) in SECOES.items():
        padroes = [tuple(x[0] for x in s) for m, s in sigs.items() if p - 1 <= m <= u - 1]
        if not padroes:
            partes.append(f"{nome} sem melodia")
            continue
        comum = Counter(padroes).most_common(1)[0][1] / len(padroes)
        ok &= comum >= PISO_RITMO
        partes.append(f"{nome} {comum:.0%} de {len(padroes)}")
    return ok, "compassos no padrão de ataques da seção: " + ", ".join(partes)


def solo(midi: Path, nome: str, pasta: Path) -> np.ndarray:
    arq = mido.MidiFile(str(midi))
    novo = mido.MidiFile(ticks_per_beat=arq.ticks_per_beat, type=arq.type)
    for tr in arq.tracks:
        nomes = [m.name for m in tr if m.type == "track_name"]
        tem_nota = any(m.type == "note_on" for m in tr)
        if not tem_nota or (nomes and nomes[0] == nome):
            novo.tracks.append(tr)
    caminho = pasta / f"solo-{len(list(pasta.iterdir()))}.mid"
    novo.save(str(caminho))
    return sintetizar(caminho, SOUNDFONT).astype(np.float64)


def energia(audio: np.ndarray, janelas) -> float:
    pedacos = [audio[int(a * TAXA):int(c * TAXA)] for a, c in janelas]
    todas = np.concatenate(pedacos) if pedacos else np.zeros(0)
    return rms(todas)


def criterio_destaque(vozes, ini, fim, mp3) -> tuple[bool, str]:
    midi = mp3.with_suffix(".mid")
    b = tempos(midi, fim)
    comps = compassos(b)

    def toca(nome):
        return {m for m, (a, c) in enumerate(comps)
                if any(n[0] < c - TOL and n[1] > a + TOL for n in vozes.get(nome, []))}

    lider = toca(LIDER)
    with tempfile.TemporaryDirectory() as pasta:
        violino = solo(midi, LIDER, Path(pasta))
        partes, ok = [], True
        for nome in PADS:
            comuns = sorted(lider & toca(nome))
            if not comuns:
                partes.append(f"{nome} sem compasso em comum")
                ok = False
                continue
            outro = solo(midi, nome, Path(pasta))
            janelas = [comps[m] for m in comuns]
            dif = db(energia(violino, janelas), energia(outro, janelas))
            ok &= dif >= DESTAQUE_DB
            partes.append(f"{nome} {dif:+.1f} dB em {len(comuns)} compassos")
    return ok, "violino I acima de: " + "; ".join(partes)


def criterio_climax(vozes, ini, fim, mp3) -> tuple[bool, str]:
    if not mp3.exists():
        return False, "sem MP3"
    audio = pcm(mp3).astype(np.float64)
    n = int(JANELA_CLIMAX * TAXA)
    if len(audio) < n:
        return False, "MP3 mais curto que a janela"
    acumulado = np.concatenate([[0.0], np.cumsum(audio ** 2)])
    passo = TAXA // 20
    inicios = np.arange(0, len(audio) - n + 1, passo)
    energias = acumulado[inicios + n] - acumulado[inicios]
    centro = (inicios[int(np.argmax(energias))] + n / 2) / TAXA
    return CLIMAX[0] <= centro <= CLIMAX[1], f"a janela de {JANELA_CLIMAX:g} s mais forte tem o centro em {centro:.1f} s"


def criterio_corte(vozes, ini, fim, mp3) -> tuple[bool, str]:
    if not mp3.exists():
        return False, "sem MP3"
    audio = pcm(mp3)
    fim_rms = rms(audio[int(FINAL[0] * TAXA):int(FINAL[1] * TAXA)])
    antes_rms = rms(audio[int(ANTES_DO_FINAL[0] * TAXA):int(ANTES_DO_FINAL[1] * TAXA)])
    dif = db(fim_rms, antes_rms)
    return dif >= -QUEDA_DB, f"{FINAL[0]:g}-{FINAL[1]:g} s a {dif:+.1f} dB de {ANTES_DO_FINAL[0]:g}-{ANTES_DO_FINAL[1]:g} s"


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: avaliar_v6.py <arquivo.mid>")
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
                 ("tessitura", criterio_tessitura), ("sol#", criterio_sol),
                 ("tempo forte", criterio_tempo_forte), ("nona menor", criterio_nona),
                 ("V -> i", criterio_v_i), ("vocabulário", criterio_vocabulario),
                 ("napolitano", criterio_napolitano), ("pedal", criterio_pedal),
                 ("figura", criterio_figura), ("baixo", criterio_baixo),
                 ("condução", criterio_conducao), ("eco", criterio_eco),
                 ("ritmo", criterio_ritmo), ("destaque", criterio_destaque),
                 ("clímax", criterio_climax), ("corte", criterio_corte)]
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
