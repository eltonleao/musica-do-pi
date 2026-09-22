"""Música do Pi, versão 2: sexteto (flauta, violinos I e II, viola, violoncelo,
piano), com o playbook de composição aplicado.

Uso: python src/v2.py --digitos 132 --saida build/v2

A invariante não mudou: a sequência de alturas do violino I é a sequência dos
dígitos de pi pelo mapeamento, na ordem, sem pular nenhum. O que mudou é tudo o
que não é altura - ritmo, forma, textura, dinâmica e andamento -, que é
exatamente o grau de liberdade que a isorritmia isola: talea (o padrão rítmico)
é livre, color (o padrão de alturas) é pi.

FORMA EM ARCO, cinco seções e uma pausa geral. As porcentagens são da duração
total, e existem porque o oráculo mede o pico de loudness entre 55% e 70%: o
clímax cai no início de D e a peça leva um quarto da duração para se dissolver,
que é o desenho do Adagio de Barber - quatro acordes de clímax e uma longa
descida.

  A  expor        0-19%   violino I e violoncelo, nada mais. pp
  B  adensar     19-43%   entram viola, violino II em tintinnabuli, flauta
  C  tensionar   43-57%   entra o piano; dominante secundária e cadência de
                          engano; a talea encurta e a harmonia anda mais rápido
  GP pausa geral 57-60%   silêncio absoluto do sexteto, sobre a dominante
  D  clímax      60-74%   tutti, ff, piano em colcheias, flauta no agudo
  E  dissolver   74-100%  tintinnabuli grave, ritardando, terça de Picardia

AS TÉCNICAS, e de onde vieram (pesquisas/composicao-pausas-e-drama-para-a-
musica-do-pi/relatorio.md, 60 fontes):

  isorritmia      talea por seção, de comprimento coprimo com o número de
                  dígitos da seção, para o padrão rítmico nunca cair no mesmo
                  lugar do padrão de alturas [12]
  tintinnabuli    o violino II toca a nota da tríade de Lá mais próxima da
                  melodia, acima em B e abaixo em E [14]
  pedal           violoncelo e flauta sustentam nota fixa sob harmonia que anda
  pausa geral     silêncio de um compasso para o conjunto inteiro, antes do
                  clímax [23]
  cadência de
  engano          V vai para VI em vez de I, no fim de B [40]
  dominante
  secundária      Lá maior resolve em Ré menor dentro de C [35]
  terça de
  Picardia        o acorde final é Lá MAIOR, não menor [39]
  arco dinâmico   de pp a ff e de volta, com andamento variável

O que este arquivo NÃO faz, e é decisão do dono (frente P2, no vault): o
mapeamento dos dígitos 8, 9 e 0 continua o provisório da PoC, e por isso a saída
se chama `v2` e não fecha a frente P3.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi

# --- mapeamento provisório (igual ao da PoC; a decisão final é do P2) -------
MAPEAMENTO: dict[str, int | None] = {
    "1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77, "7": 79,
    "8": 81, "9": 83, "0": None,
}

T_TICKS = 480          # ticks por semínima
COMPASSO = 4           # tempos por compasso
TRIADE_TONICA = (9, 0, 4)   # Lá, Dó, Mi - a tríade da voz tintinnabular

PROGRAMA = {"Flauta": 73, "Violino I": 40, "Violino II": 40,
            "Viola": 41, "Violoncelo": 42, "Piano": 0}
ORDEM = ["Flauta", "Violino I", "Violino II", "Viola", "Violoncelo", "Piano"]

TESSITURA = {"Flauta": (62, 96), "Violino I": (55, 100), "Violino II": (55, 96),
             "Viola": (48, 84), "Violoncelo": (36, 72), "Piano": (24, 100)}

ACORDES: dict[str, tuple[int, int, int]] = {
    "Am": (9, 0, 4), "Dm": (2, 5, 9), "E": (4, 8, 11), "F": (5, 9, 0),
    "C": (0, 4, 7), "G": (7, 11, 2), "Em": (4, 7, 11),
    "A": (9, 1, 4),      # Lá MAIOR: dominante secundária de Dm, e a Picardia final
}

# (letra, quantos dígitos, talea em tempos - negativo é pausa que não gasta dígito)
SECOES: list[tuple[str, int, list[float]]] = [
    ("A", 24, [2.0, 1.0, 1.0]),
    ("B", 32, [1.0, 1.0, 0.5, 0.5, 1.0, -1.0]),
    ("C", 36, [0.5, 0.5, 1.0, 0.5, 0.5, 1.0]),
    ("D", 28, [1.0, 0.5, 0.5, 1.0, 1.0]),
    ("E", 12, [2.0, -1.0, 2.0, 2.0, 3.0]),
]
PAUSA_GERAL = 4.0      # um compasso de silêncio entre C e D
FINAL_LONGO = 8.0      # a última nota da linha segura dois compassos

# Curva de dinâmica: (tempo, velocity base). Interpolada linearmente.
DINAMICA = [(0, 30), (32, 46), (72, 74), (88, 92), (92, 86), (100, 106),
            (108, 124), (116, 104), (124, 78), (142, 48), (170, 24)]

# Curva de andamento: (tempo, bpm). Degraus, não rampa - o MIDI muda de tempo
# num ponto e fica.
ANDAMENTO = [(0, 100), (32, 104), (72, 112), (92, 104), (124, 96),
             (136, 84), (144, 68)]

Evento = tuple[float, float, int, int]   # (início, duração, altura, velocity) em tempos


# --- utilidades -----------------------------------------------------------

def interpolar(curva: list[tuple[float, float]], t: float) -> float:
    if t <= curva[0][0]:
        return curva[0][1]
    for (t1, v1), (t2, v2) in zip(curva, curva[1:]):
        if t1 <= t <= t2:
            return v1 + (v2 - v1) * (t - t1) / (t2 - t1) if t2 > t1 else v1
    return curva[-1][1]


def din(t: float, offset: int = 0) -> int:
    return max(22, min(127, int(round(interpolar(DINAMICA, t))) + offset))


def soando(eventos: list[Evento], t: float) -> int | None:
    """Altura soando no tempo t - a última iniciada, se houver mais de uma."""
    cands = [(i, p) for i, d, p, _ in eventos if i <= t < i + d]
    return max(cands)[1] if cands else None


def perfeito(a: int, b: int) -> int | None:
    """Mesma fórmula do oráculo, de propósito: 0 = oitava, 7 = quinta."""
    ic = (a - b) % 12
    return ic if ic in (0, 7) else None


def gera_paralela(t: float, ant: int | None, nova: int, prontas: list[list[Evento]]) -> bool:
    """A nota `nova`, atacada em t depois de `ant`, forma quinta ou oitava
    paralela com alguma voz já escrita? Testa na grade de meios-tempos, que é a
    grade que o oráculo usa."""
    if ant is None or ant == nova:
        return False
    for ev in prontas:
        b1, b2 = soando(ev, t - 0.5), soando(ev, t)
        if b1 is None or b2 is None or b1 == b2:
            continue
        # Nos DOIS sentidos: `(a - b) % 12` não é simétrico, e uma quinta vista
        # de baixo para cima dá 5, não 7. Testar só um sentido deixou passar uma
        # quinta paralela entre violino I e violoncelo em t76, que o oráculo -
        # que percorre as vozes numa ordem fixa - viu e eu não.
        for x1, x2, y1, y2 in ((ant, nova, b1, b2), (b1, b2, ant, nova)):
            ic = perfeito(x1, y1)
            if ic is not None and ic == perfeito(x2, y2):
                return True
    return False


def escolher(classes, alvo: int, faixa: tuple[int, int], t: float, ant: int | None,
             prontas: list[list[Evento]], acima_de: int | None = None) -> int:
    """A nota das `classes` mais perto de `alvo` dentro da faixa que não produz
    paralela. Se todas produzirem, devolve a mais perto: paralela medida vale
    mais que paralela escondida atrás de uma nota ruim."""
    cands = [p for p in range(faixa[0], faixa[1] + 1) if p % 12 in classes]
    if acima_de is not None:
        cands = [p for p in cands if p > acima_de] or cands
    cands.sort(key=lambda p: (abs(p - alvo), p))
    for p in cands:
        if not gera_paralela(t, ant, p, prontas):
            return p
    return cands[0]


# --- a linha: pi pela talea -----------------------------------------------

def linha_de_pi(digitos: str) -> tuple[list[Evento], list[tuple[str, float, float]], float]:
    """Aplica a talea de cada seção aos dígitos. Devolve os eventos da melodia
    (altura None = o dígito 0, que é pausa), as marcas de seção e a duração."""
    eventos: list[Evento] = []
    marcas: list[tuple[str, float, float]] = []
    t, i = 0.0, 0
    for letra, quantos, talea in SECOES:
        t_ini, k, alvo = t, 0, i + quantos
        while i < alvo and i < len(digitos):
            d = talea[k % len(talea)]
            k += 1
            if d < 0:
                t += -d
                continue
            altura = MAPEAMENTO[digitos[i]]
            ultimo = (i == len(digitos) - 1) or (i == alvo - 1 and letra == "E")
            dur = FINAL_LONGO if ultimo else d
            if altura is not None:
                eventos.append((t, dur, altura, 0))
            t += dur
            i += 1
        t = math.ceil(t / COMPASSO) * COMPASSO
        marcas.append((letra, t_ini, t))
        if letra == "C":
            marcas.append(("GP", t, t + PAUSA_GERAL))
            t += PAUSA_GERAL
    return eventos, marcas, t


def secao_em(marcas, t: float) -> str:
    for letra, ini, fim in marcas:
        if ini <= t < fim:
            return letra
    return marcas[-1][0]


# --- harmonia -------------------------------------------------------------

def harmonia(melodia: list[Evento], marcas, n_comp: int) -> list[str]:
    """Um acorde por compasso: casamento com as notas do compasso, mais um plano
    de tensão que força os pontos dramáticos. O plano vence o casamento - é ele
    que faz a peça ter direção em vez de só concordar com pi."""
    por_compasso: list[list[tuple[float, int]]] = [[] for _ in range(n_comp)]
    for ini, dur, altura, _ in melodia:
        c = int(ini // COMPASSO)
        if c < n_comp:
            por_compasso[c].append((ini % COMPASSO, altura))

    fim_de = {letra: fim for letra, _, fim in marcas}
    ini_de = {letra: ini for letra, ini, _ in marcas}
    forcados: dict[int, str] = {0: "Am"}
    c_fim_b = int(fim_de["B"] // COMPASSO) - 1
    forcados[c_fim_b] = "E"                         # dominante...
    forcados[c_fim_b + 1] = "F"                     # ...que engana: V -> VI
    c_ini_c = int(ini_de["C"] // COMPASSO)
    forcados[c_ini_c + 2] = "A"                     # dominante secundária...
    forcados[c_ini_c + 3] = "Dm"                    # ...de Ré menor
    c_gp = int(ini_de["GP"] // COMPASSO)
    forcados[c_gp - 1] = "E"                        # a pausa geral fica suspensa na dominante
    c_d = int(ini_de["D"] // COMPASSO)
    for k, nome in enumerate(["Am", "F", "C", "G", "Am", "Dm", "E"]):
        if c_d + k < n_comp:
            forcados[c_d + k] = nome
    forcados[n_comp - 1] = "A"                      # terça de Picardia

    escolha: list[str] = []
    for c in range(n_comp):
        if c in forcados:
            escolha.append(forcados[c])
            continue
        melhor, pontos_melhor = "Am", -99.0
        for nome, classes in ACORDES.items():
            pontos = 0.0
            for pos, altura in por_compasso[c]:
                peso = 2.0 if pos in (0.0, 2.0) else 1.0
                if altura % 12 in classes:
                    pontos += peso
                elif nome in ("E", "A") and altura % 12 == 7:
                    pontos -= 1.5                   # sol natural contra o sol#
            if nome == "A":
                pontos -= 3.0                       # Lá maior só onde o plano pede
            if escolha and escolha[-1] == nome:
                pontos -= 0.75
            if pontos > pontos_melhor:
                melhor, pontos_melhor = nome, pontos
        escolha.append(melhor)
    return escolha


# --- as vozes -------------------------------------------------------------

def voz_tintinnabular(melodia: list[Evento], marcas, letras: tuple[str, ...],
                      acima: bool, faixa: tuple[int, int],
                      prontas: list[list[Evento]], offset_vel: int) -> list[Evento]:
    """Pärt: para cada nota da melodia, a nota da tríade da tônica mais próxima,
    acima ou abaixo. Quando a mais próxima produz paralela, vai a seguinte - a
    regra do tintinnabuli admite primeira e segunda posição."""
    saida: list[Evento] = []
    ant: int | None = None
    for ini, dur, altura, _ in melodia:
        if secao_em(marcas, ini) not in letras:
            continue
        cands = [p for p in range(faixa[0], faixa[1] + 1) if p % 12 in TRIADE_TONICA]
        cands = [p for p in cands if (p > altura if acima else p < altura)] or cands
        cands.sort(key=lambda p: abs(p - altura))
        escolhida = next((p for p in cands[:3] if not gera_paralela(ini, ant, p, prontas + [saida])),
                         cands[0])
        saida.append((ini, dur, escolhida, din(ini, offset_vel)))
        ant = escolhida
    return saida


def compor(digitos: str):
    melodia, marcas, duracao = linha_de_pi(digitos)
    n_comp = int(math.ceil((duracao + FINAL_LONGO) / COMPASSO))
    acordes = harmonia(melodia, marcas, n_comp)
    gp_ini = next(ini for letra, ini, _ in marcas if letra == "GP")
    gp_fim = gp_ini + PAUSA_GERAL

    def em_silencio(t: float) -> bool:
        return gp_ini <= t < gp_fim

    # O clímax não é o instante em que o tutti entra: é onde a peça chega DEPOIS
    # de entrar. D adensa em três fases para o pico de loudness cair no terço
    # central da seção, e não na primeira semínima dela - medido em 20/09/2026,
    # quando o tutti de entrada pôs o pico a 52% da duração, fora dos 55-70%.
    d_ini = next(ini for letra, ini, _ in marcas if letra == "D")

    def fase_d(t: float) -> int:
        k = int((t - d_ini) // COMPASSO)
        return 0 if k < 2 else (1 if k < 5 else 2)

    partes: dict[str, list[Evento]] = {n: [] for n in ORDEM}

    # 1. Violino I: a linha, com a dinâmica da curva e um empurrão no clímax.
    for ini, dur, altura, _ in melodia:
        secao = secao_em(marcas, ini)
        extra = 8 if secao == "D" else (-4 if secao == "A" else 0)
        partes["Violino I"].append((ini, dur, altura, din(ini, extra)))
    vn1 = partes["Violino I"]

    # 2. Violoncelo: pedal em A e E, fundamental com movimento em B, C e D.
    #    A fundamental passa pela mesma conferência das outras vozes: quando ela
    #    produz paralela com a linha, o baixo vai para a terça (primeira
    #    inversão) ou troca de oitava, que é a saída de sempre do baixo. Sem
    #    isto o violoncelo tinha duas paralelas com o violino I, em t76 e t140.
    def baixo_de(nome: str, t: float, ant: int | None, alvo: int) -> int:
        classes = ACORDES[nome]
        for opcoes in ((classes[0],), (classes[0], classes[1]), classes):
            p = escolher(opcoes, alvo, (36, 60), t, ant, [vn1])
            if not gera_paralela(t, ant, p, [vn1]):
                return p
        return escolher((classes[0],), alvo, (36, 60), t, ant, [vn1])

    ant_cello: int | None = None
    for c, nome in enumerate(acordes):
        t = c * COMPASSO
        if em_silencio(t):
            continue
        secao = secao_em(marcas, t)
        vel = din(t, -6)
        alvo = ant_cello or 45
        if secao in ("A", "E"):
            # Pedal: uma semibreve por compasso, e em A a mesma nota por dois
            # compassos, que é o que deixa a exposição imóvel.
            if secao == "A" and c % 2 == 1 and partes["Violoncelo"]:
                i0, d0, p0, v0 = partes["Violoncelo"][-1]
                partes["Violoncelo"][-1] = (i0, d0 + COMPASSO, p0, v0)
                ant_cello = p0
                continue
            fund = baixo_de(nome, t, ant_cello, alvo)
            partes["Violoncelo"].append((t, float(COMPASSO), fund, vel))
            ant_cello = fund
        elif secao in ("B", "C"):
            fund = baixo_de(nome, t, ant_cello, alvo)
            quinta = escolher((ACORDES[nome][2],), fund + 7, (36, 60), t + 2, fund, [vn1])
            partes["Violoncelo"].append((t, 2.0, fund, vel))
            partes["Violoncelo"].append((t + 2, 2.0, quinta, vel - 5))
            ant_cello = quinta
        else:   # D: oitavas martelando, que é o chão do clímax
            fund = baixo_de(nome, t, ant_cello, 48)
            partes["Violoncelo"].append((t, 1.5, fund, vel))
            partes["Violoncelo"].append((t + 2, 1.5, max(36, fund - 12), vel - 3))
            ant_cello = fund
    cello = partes["Violoncelo"]

    # 3. Viola: entra em B. Semibreve em B e E, mínimas em C, tremolo em D.
    ant_vla: int | None = None
    for c, nome in enumerate(acordes):
        t = c * COMPASSO
        secao = secao_em(marcas, t)
        if secao == "A" or em_silencio(t):
            continue
        classes = ACORDES[nome]
        vel = din(t, -10)
        if secao == "D":
            alvo = ant_vla or 64
            p = escolher(classes, alvo, (55, 79), t, ant_vla, [vn1, cello])
            if fase_d(t) == 0:
                partes["Viola"].append((t, float(COMPASSO), p, vel - 4))
            else:   # tremolo medido: oito colcheias por compasso
                for k in range(8):
                    partes["Viola"].append((t + k * 0.5, 0.45, p, vel - 6 + (4 if k % 2 == 0 else 0)))
            ant_vla = p
        elif secao == "C":
            p1 = escolher(classes, ant_vla or 64, (52, 76), t, ant_vla, [vn1, cello])
            p2 = escolher(classes, p1 + 3, (52, 76), t + 2, p1, [vn1, cello])
            partes["Viola"].append((t, 2.0, p1, vel))
            partes["Viola"].append((t + 2, 2.0, p2, vel - 4))
            ant_vla = p2
        else:
            p = escolher(classes, ant_vla or 62, (52, 74), t, ant_vla, [vn1, cello])
            partes["Viola"].append((t, float(COMPASSO), p, vel))
            ant_vla = p
    viola = partes["Viola"]

    # 4. Violino II: tintinnabuli em B (acima) e E (abaixo); voz harmônica em C
    #    e D, onde a textura precisa de peso e não de brilho.
    partes["Violino II"] = voz_tintinnabular(melodia, marcas, ("B",), True, (69, 93),
                                             [vn1, cello, viola], -14)
    partes["Violino II"] += voz_tintinnabular(melodia, marcas, ("E",), False, (57, 76),
                                              [vn1, cello, viola], -12)
    ant_vn2: int | None = None
    for c, nome in enumerate(acordes):
        t = c * COMPASSO
        secao = secao_em(marcas, t)
        if secao not in ("C", "D") or em_silencio(t):
            continue
        classes = ACORDES[nome]
        vel = din(t, -8)
        prontas = [vn1, cello, viola]
        if secao == "D":
            p = escolher(classes, 81 if fase_d(t) else 74, (67, 93), t, ant_vn2, prontas)
            if fase_d(t) == 0:
                partes["Violino II"].append((t, float(COMPASSO), p, vel - 6))
            else:
                for k in range(4):
                    partes["Violino II"].append((t + k, 0.9, p, vel - 4))
            ant_vn2 = p
        else:
            p1 = escolher(classes, ant_vn2 or 74, (67, 88), t, ant_vn2, prontas)
            p2 = escolher(classes, p1 - 2, (67, 88), t + 2, p1, prontas)
            partes["Violino II"].append((t, 2.0, p1, vel))
            partes["Violino II"].append((t + 2, 2.0, p2, vel - 5))
            ant_vn2 = p2
    partes["Violino II"].sort()
    vn2 = partes["Violino II"]

    # 5. Flauta: cala em A. Pedal agudo na terça em B (a terça, não a quinta: a
    #    quinta contra a fundamental do violoncelo produziu sete quintas
    #    paralelas seguidas na primeira tentativa, medidas em 20/09/2026).
    #    Em C marca os tempos fortes; em D sobe ao agudo a cada dois tempos; em
    #    E devolve as últimas alturas como eco.
    ant_fl: int | None = None
    for c, nome in enumerate(acordes):
        t = c * COMPASSO
        secao = secao_em(marcas, t)
        if secao in ("A", "E") or em_silencio(t):
            continue
        classes = ACORDES[nome]
        prontas = [vn1, cello, viola, vn2]
        if secao == "B" and c % 2 == 0:
            p = escolher((classes[1],), 79, (74, 88), t, ant_fl, prontas)
            partes["Flauta"].append((t, float(2 * COMPASSO), p, din(t, -18)))
            ant_fl = p
        elif secao == "C":
            for k in (0, 2):
                alvo = soando(vn1, t + k)
                if alvo is None:
                    continue
                p = alvo + 12 if alvo + 12 <= 96 else alvo
                if gera_paralela(t + k, ant_fl, p, prontas):
                    p = escolher(classes, p, (74, 93), t + k, ant_fl, prontas)
                partes["Flauta"].append((t + k, 1.75, p, din(t, -12)))
                ant_fl = p
        elif secao == "D":
            if fase_d(t) == 0:
                continue        # a flauta ainda não chegou: o auge precisa de teto para subir
            for k in (0, 2):
                alvo = soando(vn1, t + k)
                if alvo is None:
                    continue
                p = min(alvo + 12, 96)
                if gera_paralela(t + k, ant_fl, p, prontas):
                    p = escolher(classes, p, (79, 96), t + k, ant_fl, prontas)
                partes["Flauta"].append((t + k, 1.9, p, din(t, -6)))
                ant_fl = p
    # Eco da coda: as quatro últimas alturas da linha, piano, uma oitava acima,
    # entrando depois que o violino I já calou.
    ultimas = [p for _, _, p, _ in melodia][-4:]
    t_eco = duracao - 10
    for k, p in enumerate(ultimas):
        alt = p + 12 if p + 12 <= 96 else p
        partes["Flauta"].append((t_eco + k * 2, 1.8, alt, max(24, din(t_eco, -8))))
    flauta = sorted(partes["Flauta"])
    partes["Flauta"] = flauta

    # 6. Piano: entra em C. Oitavas na esquerda, arpejo na direita; colcheias no
    #    clímax; na coda arpeja a tríade devagar, que é o gesto do Spiegel im
    #    Spiegel.
    for c, nome in enumerate(acordes):
        t = c * COMPASSO
        secao = secao_em(marcas, t)
        if secao in ("A", "B") or em_silencio(t):
            continue
        classes = ACORDES[nome]
        fund = next(p for p in range(36, 52) if p % 12 == classes[0])
        vel = din(t, -14)
        ultimo = c == n_comp - 1
        arpejo = [p for p in range(55, 84) if p % 12 in classes][:4]
        if secao == "E":
            partes["Piano"].append((t, float(COMPASSO), fund - 12, vel - 6))
            for k, p in enumerate(arpejo[:3]):
                partes["Piano"].append((t + k * 1.0, float(COMPASSO - k), p, vel - 10 - 2 * k))
            if ultimo:
                for p in arpejo:
                    partes["Piano"].append((t, FINAL_LONGO, p, vel - 4))
        elif secao == "D":
            partes["Piano"].append((t, 2.0, fund - 12, vel))
            partes["Piano"].append((t + 2, 2.0, fund - 12, vel - 4))
            if fase_d(t) == 0:
                continue
            padrao = [arpejo[0], arpejo[2], arpejo[1], arpejo[2]] if len(arpejo) > 2 else arpejo
            for k in range(8):
                partes["Piano"].append((t + k * 0.5, 0.45, padrao[k % len(padrao)], vel - 8))
        else:   # C
            partes["Piano"].append((t, 2.0, fund - 12, vel - 2))
            partes["Piano"].append((t + 2, 2.0, fund, vel - 8))
            for k in range(4):
                partes["Piano"].append((t + k * 1.0, 0.9, arpejo[k % len(arpejo)], vel - 12))

    for nome in partes:
        partes[nome] = sorted(e for e in partes[nome] if TESSITURA[nome][0] <= e[2] <= TESSITURA[nome][1])
    return partes, acordes, marcas, duracao


# --- escrita --------------------------------------------------------------

def escrever_midi(partes, caminho: Path) -> None:
    arq = mido.MidiFile(ticks_per_beat=T_TICKS)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("key_signature", key="Am", time=0))
    cursor = 0
    for t, bpm in ANDAMENTO:
        tick = int(t * T_TICKS)
        meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=tick - cursor))
        cursor = tick
    arq.tracks.append(meta)
    for canal, nome in enumerate(ORDEM):
        trilha = mido.MidiTrack()
        trilha.append(mido.MetaMessage("track_name", name=nome, time=0))
        trilha.append(mido.Message("program_change", channel=canal, program=PROGRAMA[nome], time=0))
        trilha.append(mido.Message("control_change", channel=canal, control=91, value=78, time=0))
        pontos = []
        for ini, dur, altura, vel in partes[nome]:
            pontos.append((int(round(ini * T_TICKS)), 1, "note_on", altura, vel))
            pontos.append((int(round((ini + dur) * T_TICKS)), 0, "note_off", altura, 0))
        pontos.sort()
        cursor = 0
        for tick, _, tipo, altura, vel in pontos:
            trilha.append(mido.Message(tipo, channel=canal, note=altura, velocity=vel, time=tick - cursor))
            cursor = tick
        trilha.append(mido.MetaMessage("end_of_track", time=T_TICKS))
        arq.tracks.append(trilha)
    arq.save(str(caminho))


def escrever_musicxml(partes, acordes, caminho: Path) -> None:
    from music21 import instrument, key, metadata, meter, note, stream, tempo

    inst = {"Flauta": instrument.Flute(), "Violino I": instrument.Violin(),
            "Violino II": instrument.Violin(), "Viola": instrument.Viola(),
            "Violoncelo": instrument.Violoncello(), "Piano": instrument.Piano()}
    partitura = stream.Score()
    partitura.metadata = metadata.Metadata(title="Música do Pi (v2, sexteto)",
                                           composer="dígitos de pi + regras")
    for nome in ORDEM:
        parte = stream.Part(id=nome)
        parte.partName = nome
        parte.insert(0, inst[nome])
        parte.insert(0, tempo.MetronomeMark(number=ANDAMENTO[0][1]))
        parte.insert(0, meter.TimeSignature("4/4"))
        parte.insert(0, key.Key("a"))
        for ini, dur, altura, vel in partes[nome]:
            n = note.Note(altura)
            n.quarterLength = dur
            n.volume.velocity = vel
            parte.insert(ini, n)
        partitura.insert(0, parte)
    partitura.write("musicxml", fp=str(caminho))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digitos", type=int, default=132)
    ap.add_argument("--saida", default="build/v2")
    args = ap.parse_args()

    digitos = digitos_de_pi(args.digitos)
    partes, acordes, marcas, duracao = compor(digitos)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    escrever_midi(partes, saida.with_suffix(".mid"))
    escrever_musicxml(partes, acordes, saida.with_suffix(".musicxml"))
    saida.with_name(saida.name + "-mapeamento.json").write_text(json.dumps(
        {"mapeamento": MAPEAMENTO, "digitos": args.digitos, "compasso": "4/4",
         "andamento": ANDAMENTO, "formacao": ORDEM,
         "secoes": [{"letra": l, "inicio": i, "fim": f} for l, i, f in marcas]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    zeros = digitos.count("0")
    print(f"{args.digitos} dígitos ({zeros} zeros = pausa), {len(acordes)} compassos, "
          f"{duracao:.0f} tempos, {sum(len(v) for v in partes.values())} notas")
    for letra, ini, fim in marcas:
        print(f"  {letra:<2} {ini:6.0f} a {fim:6.0f} tempos  ({ini/duracao*100:4.1f}% a {fim/duracao*100:5.1f}%)")
    print("acordes: " + " ".join(acordes))
    for nome in ORDEM:
        print(f"  {nome:<12} {len(partes[nome]):3d} notas")


if __name__ == "__main__":
    main()
