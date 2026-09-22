"""Oráculo da versão 2: mede um MIDI contra os sete critérios do playbook.

Uso: python src/avaliar_v2.py build/v2.mid
Sai 0 se os sete passarem; imprime uma linha por critério com PASS/FAIL e o número.

EMENDA DE 20/09/2026 - por que esta é a segunda versão do oráculo
-----------------------------------------------------------------
A primeira versão tinha seis critérios e foi burlada em seis rodadas por um
executor barato, que devolveu 6/6 e explicou como: uma nota de velocity 1,
inaudível, onze tempos depois do fim da música. Ela esticava o denominador da
fração de pausa. Pausa declarada 16%, pausa real 8% - pior que a PoC. No mesmo
teste, o critério "zero paralelas" passou numa voz com 8 notas em 31 compassos:
voz que quase não toca não produz paralela, e passa por ausência.

O contrato errado fica registrado como errado, não se apaga. As três correções:

  1. velocity <= 5 não conta em critério nenhum (AUDIVEL). Não soa, não existe.
  2. pausa se mede por COBERTURA, não por contagem de ataques: a fração do
     intervalo entre o primeiro e o último som audível em que nenhuma nota está
     soando. Mínima não é pausa, e cauda depois do último som não é duração.
  3. critério novo (7) de densidade mínima por voz, porque todo critério de
     ausência de defeito precisa de um piso do que poderia produzi-lo.

ANTIORÁCULO - como eu passaria nisto sem fazer o trabalho
---------------------------------------------------------
Escrito antes de qualquer executor rodar contra esta versão. Cada linha é uma
maneira de satisfazer a métrica sem produzir o efeito, e o que a barra:

  nota inaudível para inflar duração ......... AUDIVEL corta velocity <= 5
  cauda de silêncio no fim para inflar pausa .. span termina no último som
  mínima longa contada como pausa ............. cobertura, não contagem
  voz fantasma para não produzir paralela ..... critério 7, piso de densidade
  WAV com silêncio no fim para durar 30 s ..... critério 6 mede som, não arquivo
  pico de ruído isolado para fingir clímax .... o pico é de loudness momentâneo
                                                 integrado em 400 ms, não de pico
                                                 de amostra
  uma só voz muito forte para inflar o LRA .... LRA é percentil, um evento curto
                                                 não move o percentil 95

O que este oráculo continua NÃO medindo, e é UNKNOWN, não aprovação: se a peça
é boa. Nenhum dos sete critérios ouve nada.

Os sete critérios (congelados antes da implementação da v2):
 1. dígitos     a linha do violino I, lida de volta do MIDI, é a sequência de pi
 2. paralelas   zero quintas e oitavas paralelas entre as vozes monofônicas
 3. pausas      de 15% a 25% do span da linha sem nenhuma nota soando
 4. clímax      pico de loudness momentâneo entre 55% e 70% da duração
 5. dinâmica    LRA >= 8 LU (a PoC tem 5,0)
 6. render      o MP3 existe e tem mais de 30 s de som acima de -50 dBFS
 7. densidade   toda voz presente toca pelo menos 0,5 nota audível por compasso
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi

AUDIVEL = 5       # velocity <= 5 não soa em nenhum SoundFont razoável
COMPASSO = 4      # tempos por compasso
MONOFONICAS = ("Flauta", "Violino I", "Violino II", "Viola", "Violoncelo")

Nota = tuple[float, float, int, int]   # (início, fim, altura, velocity) em tempos


def nome_da(track) -> str:
    return next((str(m.name) for m in track if m.type == "track_name"), "?")


def notas_de(track, tpb: int) -> list[Nota]:
    """Notas audíveis com duração, em tempos. Pareia note_on com note_off."""
    tick, abertas, saida = 0, {}, []
    for m in track:
        tick += m.time
        if m.type == "note_on" and m.velocity > 0:
            abertas.setdefault(m.note, []).append((tick, m.velocity))
        elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
            fila = abertas.get(m.note)
            if fila:
                ini, vel = fila.pop(0)
                if vel > AUDIVEL and tick > ini:
                    saida.append((ini / tpb, tick / tpb, m.note, vel))
    saida.sort()
    return saida


def vozes_de(midi: Path) -> dict[str, list[Nota]]:
    arq = mido.MidiFile(str(midi))
    fora = {}
    for t in arq.tracks:
        nome = nome_da(t)
        if nome == "?":
            continue
        ns = notas_de(t, arq.ticks_per_beat)
        if ns:
            fora[nome] = ns
    return fora


def coberto(notas: list[Nota]) -> float:
    """Total de tempos com pelo menos uma nota soando (união de intervalos)."""
    total, fim_corrente = 0.0, None
    ini_corrente = 0.0
    for ini, fim, _, _ in sorted(notas):
        if fim_corrente is None or ini > fim_corrente:
            if fim_corrente is not None:
                total += fim_corrente - ini_corrente
            ini_corrente, fim_corrente = ini, fim
        else:
            fim_corrente = max(fim_corrente, fim)
    if fim_corrente is not None:
        total += fim_corrente - ini_corrente
    return total


def altura_em(notas: list[Nota], t: float) -> int | None:
    """Altura soando no tempo t; a última iniciada, se houver mais de uma."""
    soando = [(ini, p) for ini, fim, p, _ in notas if ini <= t < fim]
    return max(soando)[1] if soando else None


def perfeito(a: int, b: int) -> int | None:
    ic = (a - b) % 12
    return ic if ic in (0, 7) else None


# --- critérios ------------------------------------------------------------

def criterio_digitos(midi: Path, vozes) -> tuple[bool, str]:
    sidecar = midi.with_name(midi.stem + "-mapeamento.json")
    if not sidecar.exists():
        return False, f"falta {sidecar.name}"
    cfg = json.loads(sidecar.read_text(encoding="utf-8"))
    mapa = {d: (int(a) if a is not None else None) for d, a in cfg["mapeamento"].items()}
    inverso = {a: d for d, a in mapa.items() if a is not None}
    if "Violino I" not in vozes:
        return False, "sem trilha 'Violino I' com nota audível"
    lidos = [inverso[p] for _, _, p, _ in vozes["Violino I"] if p in inverso]
    esperado = digitos_de_pi(int(cfg["digitos"]))
    sem_zero = [d for d in esperado if mapa.get(d) is not None]
    ok = lidos == sem_zero[:len(lidos)] and len(lidos) >= 0.8 * len(sem_zero)
    return ok, f"{len(lidos)} notas lidas de {len(sem_zero)} esperadas"


def criterio_paralelas(midi: Path, vozes) -> tuple[bool, str]:
    """Quintas e oitavas paralelas sobre a grade de meios-tempos, entre as vozes
    monofônicas. Só conta quando as DUAS vozes mudam de altura na passagem: é a
    definição de movimento paralelo, e é o que a voz ausente não consegue forjar,
    porque ausência não é mudança.

    Par em dobramento sai da conferência, e a régua é medida, não declarada: se
    duas vozes estão em uníssono ou oitava em 80% ou mais dos tempos em que as
    duas soam, elas não são vozes independentes - são uma linha e o seu reforço,
    e reforço em oitava é orquestração, não defeito (Rimsky-Korsakov, Principles
    of Orchestration). Emenda de 20/09/2026, antes da implementação da v2: a
    primeira versão deste critério acusou 34 oitavas paralelas na flauta que
    dobrava a melodia, que é exatamente o que uma flauta faz. O buraco que isso
    abriria - dobrar tudo para escapar da conferência - está fechado pelo próprio
    limiar: voz que dobra 80% do tempo deixou de ser voz."""
    presentes = [n for n in MONOFONICAS if n in vozes]
    fim = max(f for ns in vozes.values() for _, f, _, _ in ns)
    grade = [k / 2 for k in range(int(fim * 2) + 1)]
    problemas, dobrados = [], []
    for i in range(len(presentes)):
        for j in range(i + 1, len(presentes)):
            va, vb = vozes[presentes[i]], vozes[presentes[j]]
            juntas = [(altura_em(va, t), altura_em(vb, t)) for t in grade]
            juntas = [(a, b) for a, b in juntas if a is not None and b is not None]
            if juntas and sum(1 for a, b in juntas if (a - b) % 12 == 0) / len(juntas) >= 0.8:
                dobrados.append(f"{presentes[i]}+{presentes[j]}")
                continue
            for k in range(len(grade) - 1):
                t1, t2 = grade[k], grade[k + 1]
                a1, a2 = altura_em(va, t1), altura_em(va, t2)
                b1, b2 = altura_em(vb, t1), altura_em(vb, t2)
                if None in (a1, a2, b1, b2) or a1 == a2 or b1 == b2:
                    continue
                ic = perfeito(a1, b1)
                if ic is not None and ic == perfeito(a2, b2):
                    problemas.append(f"t{t1:g}: {presentes[i]}/{presentes[j]} "
                                     f"{'oitavas' if ic == 0 else 'quintas'}")
    unicos = sorted(set(problemas))
    detalhe = f"{len(unicos)} paralelas"
    if unicos:
        detalhe += " (" + "; ".join(unicos[:3]) + ")"
    if dobrados:
        detalhe += f"; dobramento fora da conferência: {', '.join(dobrados)}"
    return not unicos, detalhe


def criterio_pausas(midi: Path, vozes) -> tuple[bool, str]:
    if "Violino I" not in vozes:
        return False, "sem linha"
    linha = vozes["Violino I"]
    ini, fim = linha[0][0], max(f for _, f, _, _ in linha)
    span = fim - ini
    if span <= 0:
        return False, "span nulo"
    fracao = 1 - coberto(linha) / span
    return 0.15 <= fracao <= 0.25, f"{fracao*100:.0f}% do span sem som ({span:.0f} tempos)"


def criterio_densidade(midi: Path, vozes) -> tuple[bool, str]:
    fim = max(f for ns in vozes.values() for _, f, _, _ in ns)
    compassos = max(1, round(fim / COMPASSO))
    magras = []
    for nome, ns in sorted(vozes.items()):
        d = len(ns) / compassos
        if d < 0.5:
            magras.append(f"{nome} {d:.2f}/compasso")
    pior = min((len(ns) / compassos for ns in vozes.values()), default=0)
    detalhe = f"{len(vozes)} vozes em {compassos} compassos, mínimo {pior:.2f} nota/compasso"
    if magras:
        detalhe += " - magras: " + ", ".join(magras)
    return not magras, detalhe


def ebur128(wav: Path) -> tuple[float, float, float]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", "ebur128",
                        "-f", "null", "-"], capture_output=True, text=True)
    saida = r.stderr
    momentos = [(float(a), float(b)) for a, b in re.findall(r"t:\s*([\d.]+).*?M:\s*(-?[\d.]+)", saida)]
    validos = [(t, m) for t, m in momentos if m > -70]
    lra = float(re.findall(r"LRA:\s*(-?[\d.]+)", saida)[-1]) if "LRA:" in saida else 0.0
    if not validos:
        return 0.0, lra, 0.0
    t_pico, m_pico = max(validos, key=lambda x: x[1])
    total = max(t for t, _ in momentos)
    return t_pico / total, lra, m_pico


def segundos_de_som(caminho: Path) -> float:
    """Duração menos o silêncio: arquivo longo de silêncio não é música longa."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(caminho),
                        "-af", "silencedetect=noise=-50dB:d=0.3", "-f", "null", "-"],
                       capture_output=True, text=True)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(caminho)], capture_output=True, text=True)
    try:
        total = float(d.stdout.strip())
    except ValueError:
        return 0.0
    mudo = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", r.stderr))
    inicios = re.findall(r"silence_start:\s*([\d.]+)", r.stderr)
    fins = re.findall(r"silence_end:\s*([\d.]+)", r.stderr)
    if inicios and len(fins) < len(inicios):
        mudo += total - float(inicios[-1])
    return max(0.0, total - mudo)


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: avaliar_v2.py <arquivo.mid>")
        return 2
    midi = Path(sys.argv[1])
    if not midi.exists():
        print(f"ausente: {midi}")
        return 2
    wav, mp3 = midi.with_suffix(".wav"), midi.with_suffix(".mp3")
    vozes = vozes_de(midi)
    resultados = []

    for nome, fn in [("digitos", criterio_digitos), ("paralelas", criterio_paralelas),
                     ("pausas", criterio_pausas), ("densidade", criterio_densidade)]:
        try:
            ok, detalhe = fn(midi, vozes)
        except Exception as e:
            ok, detalhe = False, f"erro: {e}"
        resultados.append((nome, ok, detalhe))

    if wav.exists():
        pos, lra, pico = ebur128(wav)
        resultados.append(("climax", 0.55 <= pos <= 0.70, f"pico a {pos*100:.0f}% da duração ({pico:.1f} LUFS)"))
        resultados.append(("dinamica", lra >= 8.0, f"LRA {lra:.1f} LU"))
    else:
        resultados.append(("climax", False, "sem WAV"))
        resultados.append(("dinamica", False, "sem WAV"))

    som = segundos_de_som(mp3) if mp3.exists() else 0.0
    resultados.append(("render", som > 30, f"{som:.0f} s de som no MP3"))

    ordem = ["digitos", "paralelas", "pausas", "climax", "dinamica", "render", "densidade"]
    resultados.sort(key=lambda r: ordem.index(r[0]))
    passou = sum(1 for _, ok, _ in resultados if ok)
    for nome, ok, detalhe in resultados:
        print(f"{'PASS' if ok else 'FAIL'}  {nome:<10} {detalhe}")
    print(f"{passou}/7 critérios")
    return 0 if passou == 7 else 1


if __name__ == "__main__":
    sys.exit(main())
