"""Os dígitos de pi, calculados aqui mesmo (fórmula de Machin com inteiros grandes).

Nada de constante copiada: o gerador e o oráculo usam a mesma função, e a
guarda abaixo confere os 50 primeiros dígitos contra o valor conhecido para
pegar erro de implementação.
"""

GUARDA_50 = "31415926535897932384626433832795028841971693993751"


def digitos_de_pi(n: int) -> str:
    """Devolve os n primeiros dígitos de pi como string, começando pelo 3."""
    if n < 1:
        return ""
    precisao = n + 10
    escala = 10 ** precisao

    def arctan_inverso(x: int) -> int:
        total = 0
        termo = escala // x
        x2 = x * x
        k = 0
        sinal = 1
        while termo:
            total += sinal * (termo // (2 * k + 1))
            termo //= x2
            k += 1
            sinal = -sinal
        return total

    pi = 16 * arctan_inverso(5) - 4 * arctan_inverso(239)
    texto = str(pi)
    if not texto.startswith(GUARDA_50[: min(50, n)]):
        raise RuntimeError("os dígitos calculados não batem com a guarda de 50 dígitos")
    return texto[:n]


if __name__ == "__main__":
    import sys

    quantos = int(sys.argv[1]) if len(sys.argv) > 1 else 128
    print(digitos_de_pi(quantos))
