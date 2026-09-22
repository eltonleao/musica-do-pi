"""Oráculo da versão 3 - o círculo. Mede um MIDI (e o MP3 ao lado) contra seis critérios.

Uso: python src/avaliar_v3.py build/v3.mid
Sai 0 se os seis passarem; imprime uma linha por critério com PASS/FAIL e o número.

O pedido do dono, 21/09/2026: a peça dura 3 min 14 s, usa 314 dígitos de pi, e
"algo nela precisa lembrar um círculo" - escolhidos forma circular, cânone
circular e palíndromo, os três juntos.

Os seis critérios (congelados antes de existir o compositor da v3):
 1. dígitos     o violino I, na primeira metade, lê de volta os 314 primeiros
                dígitos de pi, sem faltar nem sobrar nenhum (o 0 é pausa)
 2. duração     o som vai de 0 a 194,00 s no MIDI (tolerância 50 ms), o MP3 dura
                194,0 s (tolerância 150 ms) e tem pelo menos 184 s de som
 3. palíndromo  em cada trilha, a segunda metade é a primeira de trás para frente:
                toda nota (início, fim, altura, velocity) tem o espelho no eixo
 4. cânone      violino II, viola e violoncelo tocam a linha do violino I (mesma
                classe de altura, mesmo ritmo), entrando um depois do outro, com
                pelo menos 60 notas cada antes do eixo; a flauta toca a mesma
                linha em aumentação, quatro vezes mais lenta
 5. circular    a peça termina no mesmo som em que começa, com o Dó do 3 no
                violino I, e a emenda do loop não tem silêncio
 6. tessitura   as seis vozes estão presentes e toda nota cabe na tessitura

ANTIORÁCULO - como eu passaria nisto sem fazer o trabalho
---------------------------------------------------------
  silêncio no fim para chegar a 194 s ....... a duração é do último som audível,
                                               e o MP3 precisa de 184 s de som
  nota inaudível para esticar a duração ...... velocity <= 5 não conta (AUDIVEL)
  palíndromo trivial, com uma nota só ....... o critério 1 exige as 314 posições
                                               no violino I, e o 4 exige 60 notas
                                               em cada voz da roda
  "cânone" com a mesma nota repetida ........ a classe de altura é conferida nota
                                               a nota contra o líder
  vozes que entram juntas ................... as entradas são estritamente
                                               crescentes
  segunda metade copiada, não invertida ..... o espelho é conferido nota a nota,
                                               com início e fim trocados
  MP3 esticado com silêncio ................. 184 s de som acima de -50 dBFS

O que este oráculo NÃO mede, e é UNKNOWN, não aprovação: se a peça é boa, e se
o círculo se ouve. Paralelas também não entram: num cânone estrito de dígitos,
oitava paralela aparece sempre que o mesmo par de dígitos se repete na
defasagem, e a escolha de oitava não a desfaz.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi

DIGITOS = 314
DURACAO = 194.0          # 3 min 14 s
TOL_MIDI = 0.05
TOL_MP3 = 0.15
SOM_MINIMO = 184.0
TOL = 0.003              # 3 ms: arredondamento de tick
AUDIVEL = 5

# O mapeamento provisório da v2, copiado e não importado: se o compositor
# mudar o dele, o oráculo não muda junto.
MAPEAMENTO = {"1": 69, "2": 71, "3": 72, "4": 74, "5": 76, "6": 77, "7": 79,
              "8": 81, "9": 83, "0": None}
LIDER = "Violino I"
RODA = ("Violino II", "Viola", "Violoncelo")
AUMENTACAO = ("Flauta", 4.0)
MINIMO_NA_RODA = 60
TESSITURA = {"Flauta": (62, 96), "Violino I": (55, 100), "Violino II": (55, 96),
             "Viola": (48, 84), "Violoncelo": (36, 72), "Piano": (24, 100)}

Nota = tuple[float, float, int, int]   # (início, fim, altura, velocity) em segundos


def relogio(arq: mido.MidiFile):
    mudancas = sorted((t, m.tempo) for tr in arq.tracks
                      for t, m in zip(_ticks(tr), tr) if m.type == "set_tempo")
    if not mudancas or mudancas[0][0] > 0:
        mudancas.insert(0, (0, 500000))

    def segundos(tick: int) -> float:
        s, ant, tempo = 0.0, 0, mudancas[0][1]
        for t, novo in mudancas:
            if t >= tick:
                break
            s += mido.tick2second(t - ant, arq.ticks_per_beat, tempo)
            ant, tempo = t, novo
        return s + mido.tick2second(tick - ant, arq.ticks_per_beat, tempo)
    return segundos


def _ticks(trilha) -> list[int]:
    t, saida = 0, []
    for m in trilha:
        t += m.time
        saida.append(t)
    return saida


def vozes_de(midi: Path) -> dict[str, list[Nota]]:
    arq = mido.MidiFile(str(midi))
    seg = relogio(arq)
    vozes: dict[str, list[Nota]] = {}
    for tr in arq.tracks:
        nome, abertas, notas = None, {}, []
        for tick, m in zip(_ticks(tr), tr):
            if m.type == "track_name":
                nome = m.name
            elif m.type == "note_on" and m.velocity > 0:
                abertas.setdefault(m.note, []).append((tick, m.velocity))
            elif m.type in ("note_on", "note_off") and abertas.get(m.note):
                ini, vel = abertas[m.note].pop(0)
                if vel > AUDIVEL:
                    notas.append((seg(ini), seg(tick), m.note, vel))
        if nome and notas:
            vozes[nome] = sorted(notas)
    return vozes


def extremos(vozes) -> tuple[float, float]:
    todas = [n for ns in vozes.values() for n in ns]
    return min(n[0] for n in todas), max(n[1] for n in todas)


def primeira_metade(notas: list[Nota], meio: float) -> list[Nota]:
    return [n for n in notas if n[0] < meio - TOL]


def criterio_digitos(vozes, ini, fim, mp3) -> tuple[bool, str]:
    inverso = {a: d for d, a in MAPEAMENTO.items() if a is not None}
    lidos = "".join(inverso.get(n[2], "?")
                    for n in primeira_metade(vozes.get(LIDER, []), (ini + fim) / 2))
    esperado = digitos_de_pi(DIGITOS).replace("0", "")
    if lidos == esperado:
        return True, f"{len(lidos)} notas lidas, iguais aos {DIGITOS} dígitos sem os zeros"
    i = next((k for k, (a, b) in enumerate(zip(lidos, esperado)) if a != b), min(len(lidos), len(esperado)))
    return False, f"{len(lidos)} notas lidas de {len(esperado)} esperadas; divergem na posição {i + 1}"


def duracao_do_arquivo(caminho: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(caminho)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def segundos_de_som(caminho: Path, total: float) -> float:
    """Duração menos o silêncio abaixo de -50 dBFS (igual ao oráculo da v2)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(caminho),
                        "-af", "silencedetect=noise=-50dB:d=0.3", "-f", "null", "-"],
                       capture_output=True, text=True)
    mudo = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", r.stderr))
    inicios = re.findall(r"silence_start:\s*([\d.]+)", r.stderr)
    fins = re.findall(r"silence_end:\s*([\d.]+)", r.stderr)
    if inicios and len(fins) < len(inicios):
        mudo += total - float(inicios[-1])
    return max(0.0, total - mudo)


def criterio_duracao(vozes, ini, fim, mp3) -> tuple[bool, str]:
    ok_midi = abs(ini) <= TOL_MIDI and abs(fim - DURACAO) <= TOL_MIDI
    texto = f"MIDI de {ini:.3f} a {fim:.3f} s"
    if not mp3.exists():
        return False, texto + "; sem MP3"
    total = duracao_do_arquivo(mp3)
    som = segundos_de_som(mp3, total)
    ok = ok_midi and abs(total - DURACAO) <= TOL_MP3 and som >= SOM_MINIMO
    return ok, texto + f"; MP3 de {total:.3f} s, {som:.1f} s de som"


def criterio_palindromo(vozes, ini, fim, mp3) -> tuple[bool, str]:
    # Casamento por tolerância, não por ordenação: arredondar o início para
    # ordenar pode separar uma nota do espelho dela na fronteira do arredondamento.
    quebradas = []
    for nome, notas in vozes.items():
        grupos: dict[tuple[int, int], list[Nota]] = {}
        for n in notas:
            grupos.setdefault((n[2], n[3]), []).append(n)
        sem_par = [n for n in notas
                   if not any(abs(m[0] - (ini + fim - n[1])) <= TOL and abs(m[1] - (ini + fim - n[0])) <= TOL
                              for m in grupos[(n[2], n[3])])]
        if sem_par:
            quebradas.append(f"{nome} ({len(sem_par)} de {len(notas)})")
    total = sum(len(v) for v in vozes.values())
    if quebradas:
        return False, f"sem espelho em: {', '.join(quebradas)}"
    return True, f"{total} notas em {len(vozes)} trilhas, todas com espelho no eixo {(ini + fim) / 2:.2f} s"


def segue(lider: list[Nota], voz: list[Nota], fator: float) -> int | None:
    """Índice da primeira nota em que a voz deixa de imitar o líder, ou None."""
    for i, (a, b) in enumerate(zip(lider, voz)):
        esperado = voz[0][0] + fator * (a[0] - lider[0][0])
        if a[2] % 12 != b[2] % 12 or abs(b[0] - esperado) > TOL:
            return i
    return None


def criterio_canone(vozes, ini, fim, mp3) -> tuple[bool, str]:
    meio = (ini + fim) / 2
    lider = primeira_metade(vozes.get(LIDER, []), meio)
    if len(lider) < MINIMO_NA_RODA:
        return False, f"líder com {len(lider)} notas antes do eixo"
    entradas, partes = [lider[0][0]], []
    for nome in RODA:
        voz = primeira_metade(vozes.get(nome, []), meio)
        if len(voz) < MINIMO_NA_RODA:
            return False, f"{nome}: {len(voz)} notas antes do eixo"
        i = segue(lider, voz, 1.0)
        if i is not None:
            return False, f"{nome} deixa de imitar o líder na nota {i + 1}"
        entradas.append(voz[0][0])
        partes.append(f"{nome} {voz[0][0]:.1f} s")
    if any(b - a < 1.0 for a, b in zip(entradas, entradas[1:])):
        return False, f"as entradas não vêm uma depois da outra: {entradas}"
    nome, fator = AUMENTACAO
    voz = primeira_metade(vozes.get(nome, []), meio)
    if len(voz) < 20:
        return False, f"{nome}: {len(voz)} notas antes do eixo"
    i = segue(lider, voz, fator)
    if i is not None:
        return False, f"{nome} deixa a aumentação na nota {i + 1}"
    return True, "entradas: " + ", ".join(partes) + f"; {nome} em aumentação x{fator:g} com {len(voz)} notas"


def criterio_circular(vozes, ini, fim, mp3) -> tuple[bool, str]:
    abre = sorted((nome, n[2]) for nome, ns in vozes.items() for n in ns if abs(n[0] - ini) <= TOL)
    fecha = sorted((nome, n[2]) for nome, ns in vozes.items() for n in ns if abs(n[1] - fim) <= TOL)
    ok = bool(abre) and abre == fecha and (LIDER, MAPEAMENTO["3"]) in abre and abs(ini) <= TOL_MIDI
    return ok, f"abre com {len(abre)} notas, fecha com {len(fecha)}, {'iguais' if abre == fecha else 'diferentes'}"


def criterio_tessitura(vozes, ini, fim, mp3) -> tuple[bool, str]:
    faltam = [n for n in TESSITURA if n not in vozes]
    fora = [(nome, n[2]) for nome, ns in vozes.items() if nome in TESSITURA
            for n in ns if not TESSITURA[nome][0] <= n[2] <= TESSITURA[nome][1]]
    if faltam:
        return False, f"faltam as vozes: {', '.join(faltam)}"
    return not fora, f"{len(fora)} notas fora da tessitura" + (f", a primeira {fora[0]}" if fora else "")


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: avaliar_v3.py <arquivo.mid>")
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
                 ("palíndromo", criterio_palindromo), ("cânone", criterio_canone),
                 ("circular", criterio_circular), ("tessitura", criterio_tessitura)]
    passou = 0
    for nome, fn in criterios:
        try:
            ok, detalhe = fn(vozes, ini, fim, midi.with_suffix(".mp3"))
        except Exception as e:
            ok, detalhe = False, f"erro: {e}"
        passou += ok
        print(f"{'PASS' if ok else 'FAIL'}  {nome:<11} {detalhe}")
    print(f"{passou}/{len(criterios)} critérios")
    return 0 if passou == len(criterios) else 1


if __name__ == "__main__":
    sys.exit(main())
