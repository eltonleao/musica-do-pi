"""A sequência de Fibonacci, calculada aqui mesmo com inteiros exatos.

Nada de constante copiada: soma inteira, sem ponto flutuante. A guarda abaixo
confere os 15 primeiros termos contra o valor conhecido para pegar erro de
implementação.
"""

GUARDA_15 = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]


def fibonacci(n: int) -> list[int]:
    """Devolve os n primeiros termos de Fibonacci, começando em 1, 1."""
    if n < 1:
        return []
    termos = [1, 1]
    while len(termos) < n:
        termos.append(termos[-1] + termos[-2])
    termos = termos[:n]
    if termos[: min(15, n)] != GUARDA_15[: min(15, n)]:
        raise RuntimeError("os termos calculados não batem com a guarda de 15 termos")
    return termos


if __name__ == "__main__":
    import sys

    print(fibonacci(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
