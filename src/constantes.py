"""Experimento: quais constantes matemáticas e físicas produzem melodia que
obedece às leis da harmonia, sob o mapeamento da Música do Pi.

HIPÓTESE DECLARADA ANTES DE MEDIR (2026-09-20)
H0: os dígitos de uma constante normal são estatisticamente indistinguíveis de
    dígitos uniformes aleatórios, logo NENHUMA constante deve se destacar em
    nenhuma métrica harmônica além do acaso (percentil entre 5 e 95 contra a
    série de controle).
H1: constantes cuja expansão NÃO é normal ou é curta (racionais periódicos,
    frações contínuas regulares, constantes físicas com poucos dígitos) devem
    se destacar, porque nelas existe estrutura de repetição, que é matéria-prima
    de forma musical.
Critério de destaque: percentil <= 5 ou >= 95 na série de controle de 2000
sequências uniformes do MESMO comprimento. Isso é uma régua de acaso, não de
significância corrigida para múltiplas comparações; com 9 métricas e dezenas de
candidatos, falso positivo isolado é esperado e está anotado no relatório.

Uso: python src/constantes.py --digitos 132 --controles 2000
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from pathlib import Path

from mpmath import mp, mpf, sqrt, log, zeta

from compor import ACORDES, COMPASSO, MAPEAMENTO_POC

# Intervalos consonantes em semitons, reduzidos à oitava: uníssono, terças,
# quarta justa, quinta justa, sextas. Dissonantes: segundas, trítono, sétimas.
CONSONANTES = {0, 3, 4, 5, 7, 8, 9}
TRITONO = 6


def digitos_mpmath(nome: str, n: int) -> str:
    """Dígitos significativos de uma constante matemática, com 20 de folga."""
    mp.dps = n + 25
    valores = {
        "pi": lambda: mp.pi,
        "e": lambda: mp.e,
        "phi (áurea)": lambda: mp.phi,
        "sqrt2": lambda: sqrt(2),
        "sqrt3": lambda: sqrt(3),
        "sqrt5": lambda: sqrt(5),
        "gamma (Euler-Mascheroni)": lambda: mp.euler,
        "ln2": lambda: log(2),
        "Catalan": lambda: mp.catalan,
        "Apéry zeta(3)": lambda: zeta(3),
        "Glaisher": lambda: mp.glaisher,
        "Khinchin": lambda: mp.khinchin,
        "Mertens": lambda: mp.mertens,
        "primos gêmeos": lambda: mp.twinprime,
        "tau (2pi)": lambda: 2 * mp.pi,
        "pi^2": lambda: mp.pi ** 2,
        "1/7 (periódico)": lambda: mpf(1) / 7,
        "1/81 (periódico)": lambda: mpf(1) / 81,
    }
    texto = mp.nstr(valores[nome](), n + 15, strip_zeros=False)
    return so_digitos(texto)[:n]


def so_digitos(texto: str) -> str:
    """Dígitos significativos: sem sinal, ponto, espaço, expoente nem zeros à esquerda."""
    texto = re.sub(r"[eE][-+]?\d+$", "", texto.strip())
    d = re.sub(r"\D", "", texto)
    return d.lstrip("0") or "0"


def fracao_continua(nome: str, n: int) -> str:
    """Termos da fração contínua regular, como dígitos (só termos de 1 algarismo).

    Mostra a diferença que o pedido pede: a expansão decimal de e é normal e
    sem padrão; a fração contínua de e é [2;1,2,1,1,4,1,1,6,1,...], um ostinato
    com um termo que cresce. Termos com mais de um algarismo viram o resto da
    divisão por 10 e ficam registrados no campo `truncados`.
    """
    mp.dps = 400
    x = {"e": mp.e, "pi": mp.pi, "phi (áurea)": mp.phi, "sqrt2": sqrt(2)}[nome]
    termos, truncados = [], 0
    for _ in range(n):
        a = int(x)
        if a > 9:
            truncados += 1
            termos.append("0")   # termo grande vira pausa: mod 10 inventaria uma nota
        else:
            termos.append(str(a))
        resto = x - a
        if resto == 0:
            break
        x = 1 / resto
    return "".join(termos)[:n], truncados


def fibonacci(n: int, modulo: int = 10, inicio: tuple[int, int] = (1, 1)) -> str:
    """F(n) mod m como dígitos. Com m = 10 a sequência é periódica de período 60
    (período de Pisano), o que é forma musical embutida: 60 notas e volta."""
    a_, b_ = inicio
    saida = []
    for _ in range(n):
        saida.append(str(a_ % modulo % 10))
        a_, b_ = b_, a_ + b_
    return "".join(saida)


def palavra_de_fibonacci(n: int, dois: str = "15") -> str:
    """Palavra de Fibonacci: S1='0', S2='01', S(k)=S(k-1)+S(k-2). Aperiódica e
    auto-similar. Os dois símbolos viram duas notas (por padrão Lá4 e Mi5)."""
    a_, b_ = "0", "01"
    while len(b_) < n:
        a_, b_ = b_, b_ + a_
    return "".join(dois[int(c)] for c in b_[:n])


def reciproca_de_fibonacci(n: int) -> str:
    """Constante recíproca de Fibonacci: soma de 1/F(k), k >= 1."""
    mp.dps = n + 30
    a_, b_ = 1, 1
    total = mpf(0)
    for _ in range(n + 200):
        total += mpf(1) / a_
        a_, b_ = b_, a_ + b_
    return so_digitos(mp.nstr(total, n + 10, strip_zeros=False))[:n]


def razoes_de_fibonacci(quantas: int = 14) -> list[tuple[str, float, str, float]]:
    """F(k+1)/F(k) em cents, e o intervalo justo mais próximo. É a lei da
    harmonia aplicada à sequência: 2/1 é oitava, 3/2 é quinta justa, 5/3 é
    sexta maior, 8/5 é sexta menor - todos intervalos da série harmônica."""
    from math import log2
    justos = {"uníssono": 1 / 1, "oitava": 2 / 1, "quinta justa": 3 / 2, "quarta justa": 4 / 3,
              "terça maior": 5 / 4, "terça menor": 6 / 5, "sexta maior": 5 / 3, "sexta menor": 8 / 5,
              "sétima menor": 9 / 5, "segunda maior": 9 / 8, "trítono": 45 / 32}
    a_, b_ = 1, 1
    saida = []
    for _ in range(quantas):
        r = b_ / a_
        cents = 1200 * log2(r)
        nome, dist = min(((k, abs(1200 * log2(v) - cents)) for k, v in justos.items()), key=lambda x: x[1])
        saida.append((f"{b_}/{a_}", cents, nome, dist))
        a_, b_ = b_, a_ + b_
    return saida


def constantes_do_nist(caminho: Path, minimo_digitos: int = 9) -> list[tuple[str, str, str]]:
    """Lê a tabela CODATA do NIST e devolve (nome, valor bruto, dígitos)."""
    saida = []
    for linha in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
        if len(linha) < 80 or linha.startswith((" ", "-")) and not linha.strip():
            continue
        nome = linha[:60].strip()
        valor = linha[60:85].strip()
        if not nome or not valor or not re.match(r"^[\d .]+(e[-+]\d+)?$", valor.replace("...", "")):
            continue
        d = so_digitos(valor.replace(" ", "").replace("...", ""))
        if len(d) >= minimo_digitos:
            saida.append((nome, valor, d))
    return saida


# ----------------------------------------------------------------- métricas
def melodia(digitos: str) -> list[int | None]:
    return [MAPEAMENTO_POC[d] for d in digitos]


def metricas(digitos: str) -> dict[str, float]:
    notas = melodia(digitos)
    soantes = [n for n in notas if n is not None]
    ints = [abs(b - a) for a, b in zip(soantes, soantes[1:])]
    n_int = len(ints) or 1
    m = {
        "pausas": sum(1 for n in notas if n is None) / len(notas),
        "conjunto": sum(1 for i in ints if i <= 2) / n_int,
        "consonancia": sum(1 for i in ints if (i % 12) in CONSONANTES) / n_int,
        "tritono": sum(1 for i in ints if (i % 12) == TRITONO) / n_int,
        "salto_grande": sum(1 for i in ints if i > 7) / n_int,
        "passo_medio": statistics.fmean(ints) if ints else 0.0,
    }
    # Recorrência motívica: trigramas de altura que reaparecem.
    tri = [tuple(soantes[i:i + 3]) for i in range(len(soantes) - 2)]
    if tri:
        from collections import Counter
        c = Counter(tri)
        m["recorrencia"] = sum(v for v in c.values() if v > 1) / len(tri)
    else:
        m["recorrencia"] = 0.0
    # Encaixe harmônico: o harmonizador da PoC, e quanto da melodia cabe no acorde.
    m["encaixe"] = encaixe_harmonico(notas)
    # Cadência: a última nota soante está na tríade da tônica de Lá menor?
    m["final_triade"] = 1.0 if soantes and (soantes[-1] % 12) in ACORDES["Am"] else 0.0
    return m


def encaixe_harmonico(notas: list[int | None]) -> float:
    """Para cada compasso, o melhor acorde diatônico; devolve a fração média de
    notas do compasso que pertencem a ele (tempos 1 e 3 pesando o dobro)."""
    total_peso = total_dentro = 0.0
    for i in range(0, len(notas), COMPASSO):
        compasso = notas[i:i + COMPASSO]
        pesos = [(2.0 if t in (0, 2) else 1.0) for t, n in enumerate(compasso) if n is not None]
        alturas = [n for n in compasso if n is not None]
        if not alturas:
            continue
        melhor = max(ACORDES.values(),
                     key=lambda cl: sum(p for p, n in zip(pesos, alturas) if n % 12 in cl))
        total_dentro += sum(p for p, n in zip(pesos, alturas) if n % 12 in melhor)
        total_peso += sum(pesos)
    return total_dentro / total_peso if total_peso else 0.0


def krumhansl(digitos: str) -> float:
    """Correlação do perfil de alturas com o melhor perfil de tonalidade
    (algoritmo de Krumhansl-Schmuckler, implementado no music21)."""
    from music21 import note, stream
    s = stream.Stream()
    for altura in melodia(digitos):
        if altura is not None:
            s.append(note.Note(altura, quarterLength=1))
    k = s.analyze("key")
    return float(k.correlationCoefficient)


MAIS_E_MELHOR = {"conjunto": True, "consonancia": True, "recorrencia": True,
                 "encaixe": True, "krumhansl": True, "tritono": False,
                 "salto_grande": False, "passo_medio": False}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digitos", type=int, default=132)
    ap.add_argument("--controles", type=int, default=2000)
    ap.add_argument("--nist", default="/home/eltonleao/.claude/jobs/c37d50eb/tmp/nist.txt")
    ap.add_argument("--saida", default="build/constantes.json")
    ap.add_argument("--so-fibonacci", action="store_true",
                    help="mede só a família Fibonacci, com o mesmo controle e as mesmas réguas")
    args = ap.parse_args()
    n = args.digitos
    rng = random.Random(31415926)

    # ---- série de controle, UMA POR COMPRIMENTO: comparar uma constante de 9
    # dígitos com o controle de 132 mediria o tamanho, não a constante.
    caches: dict[int, dict[str, list[float]]] = {}

    def controle_de(tam: int) -> dict[str, list[float]]:
        if tam not in caches:
            amostras = []
            for _ in range(args.controles):
                d = "".join(rng.choice("0123456789") for _ in range(tam))
                m = metricas(d)
                m["krumhansl"] = krumhansl(d)
                amostras.append(m)
            caches[tam] = {k: sorted(a[k] for a in amostras) for k in amostras[0]}
        return caches[tam]

    def percentil(tam: int, chave: str, valor: float) -> float:
        """Percentil de rank médio: empate conta meio. Sem isso, um valor que é
        o mínimo possível da métrica (recorrência 0, trítono 0) sai no percentil
        0 mesmo quando metade do controle empata com ele, e toda sequência curta
        vira 'destaque'. Foi o que aconteceu na primeira rodada: 199 de 199
        constantes físicas marcadas."""
        xs = controle_de(tam)[chave]
        menores = sum(1 for x in xs if x < valor)
        iguais = sum(1 for x in xs if x == valor)
        return 100.0 * (menores + iguais / 2) / len(xs)

    dist = controle_de(n)

    candidatos: list[tuple[str, str, str]] = []
    if args.so_fibonacci:
        candidatos += [
            ("fibonacci", "F(n) mod 10 (período de Pisano 60)", fibonacci(n, 10)),
            ("fibonacci", "F(n) mod 9", fibonacci(n, 9)),
            ("fibonacci", "F(n) mod 7 (período 16)", fibonacci(n, 7)),
            ("fibonacci", "F(n) mod 12", fibonacci(n, 12)),
            ("fibonacci", "Lucas L(n) mod 10", fibonacci(n, 10, (2, 1))),
            ("fibonacci", "palavra de Fibonacci (Lá/Mi)", palavra_de_fibonacci(n)),
            ("fibonacci", "palavra de Fibonacci (Lá/Dó)", palavra_de_fibonacci(n, "13")),
            ("fibonacci", "constante recíproca de Fibonacci", reciproca_de_fibonacci(n)),
            ("fibonacci", "phi decimal (para comparar)", digitos_mpmath("phi (áurea)", n)),
            ("fibonacci", "pi decimal (linha de base da peça)", digitos_mpmath("pi", n)),
        ]
        termos, trunc = fracao_continua("phi (áurea)", n)
        candidatos.append(("fibonacci", f"phi fração contínua ({trunc} termos > 9)", termos))
        candidatos.append(("referência", "Ode à Alegria (tema)", "3345543211233221"))
        candidatos.append(("referência", "Brilha, brilha estrelinha", "1155665443322115"))
        linhas_extra = razoes_de_fibonacci()
        print("Razões F(k+1)/F(k) contra os intervalos justos:")
        for r, cents, nome_i, erro in linhas_extra:   # nao usar `dist`: sombreia o controle
            print(f"  {r:>10}  {cents:8.2f} cents   ~ {nome_i:<14} (erro {erro:6.2f} cents)")
        print()
    for nome in [] if args.so_fibonacci else ["pi", "e", "phi (áurea)", "sqrt2", "sqrt3", "sqrt5",
                 "gamma (Euler-Mascheroni)", "ln2", "Catalan", "Apéry zeta(3)",
                 "Glaisher", "Khinchin", "Mertens", "primos gêmeos",
                 "tau (2pi)", "pi^2", "1/7 (periódico)", "1/81 (periódico)"]:
        candidatos.append(("matemática", nome, digitos_mpmath(nome, n)))
    for nome in [] if args.so_fibonacci else ["e", "pi", "phi (áurea)", "sqrt2"]:
        termos, truncados = fracao_continua(nome, n)
        candidatos.append(("fração contínua", f"{nome} [fração contínua, {truncados} termos > 9]", termos))

    nist = Path(args.nist)
    if nist.exists() and not args.so_fibonacci:
        vistos = set()
        for nome, _bruto, d in constantes_do_nist(nist, minimo_digitos=10):
            if d[:12] in vistos:          # mesma mantissa em unidades diferentes
                continue
            vistos.add(d[:12])
            candidatos.append(("física (CODATA 2022)", nome, d[:12]))

    # Referências humanas, para saber o que é "bom" numa régua musical.
    # Ode à Alegria e Brilha Estrela, em graus da escala sobre o mesmo mapa.
    if not args.so_fibonacci:
        candidatos.append(("referência", "Ode à Alegria (tema)", "3345543211233221"))
        candidatos.append(("referência", "Brilha, brilha estrelinha", "1155665443322115"))
    candidatos.append(("referência", "escala ascendente repetida", "12345678" * (n // 8 + 1)))

    linhas = []
    for familia, nome, d in candidatos:
        d = d[:n]
        if len(d) < 8:
            continue
        m = metricas(d)
        try:
            m["krumhansl"] = krumhansl(d)
        except Exception:
            m["krumhansl"] = float("nan")
        p = {k: (percentil(len(d), k, v) if k in dist else None) for k, v in m.items()}
        linhas.append({"familia": familia, "nome": nome, "digitos": len(d),
                       "primeiros": d[:16], "metricas": m, "percentil": p})

    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).write_text(json.dumps(
        {"n": n, "controles": args.controles,
         "controle_mediana": {k: statistics.median(v) for k, v in dist.items()},
         "controle_por_tamanho": {str(tam): {k: statistics.median(v) for k, v in c.items()}
                                  for tam, c in caches.items()},
         "linhas": linhas}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---- saída legível
    cab = ["conjunto", "consonancia", "tritono", "salto_grande", "recorrencia", "encaixe", "krumhansl", "pausas"]
    print(f"n={n} dígitos | controle={args.controles} sequências uniformes")
    print("mediana do controle: " + "  ".join(f"{k}={statistics.median(dist[k]):.3f}" for k in cab))
    print()
    print(f"{'família':<22}{'constante':<44}" + "".join(f"{k[:9]:>11}" for k in cab))
    for L in sorted(linhas, key=lambda x: (x["familia"], x["nome"])):
        cel = []
        for k in cab:
            v = L["metricas"][k]
            p = L["percentil"].get(k)
            marca = "*" if (p is not None and (p <= 5 or p >= 95)) else " "
            cel.append(f"{v:>10.3f}{marca}")
        print(f"{L['familia']:<22}{L['nome'][:43]:<44}" + "".join(cel))
    print("\n* = percentil <= 5 ou >= 95 contra a série de controle do mesmo comprimento")


if __name__ == "__main__":
    main()
