"""Oráculo da v10 - menor que vira maior, e o clímax no fim.

Uso: python src/avaliar_v10.py <arquivo.mid>

Deriva `<arquivo>.mp3` e `<arquivo>-mapeamento.json` do mesmo nome. Imprime uma linha
`PASS|FAIL|UNKNOWN  nome  detalhe` por critério e fecha com `n/N critérios`. Sai 0 só com
tudo PASS, 1 com algum FAIL, 2 com UNKNOWN sem nenhum FAIL.

`EIXO = 56` é constante do oráculo, não vem do sidecar. Os segundos vêm do mapa de
andamento (`set_tempo`) do próprio MIDI: `sec(t)` é o segundo do tempo `t`. "Soando" é
entre o `note_on` e o `note_off` correspondente. `S` é o loudness short-term do
`ffmpeg -af ebur128`, lido do MP3, um valor a cada 100 ms.

Os treze critérios são os da tabela "O oráculo" do plano P11:

  M0  (guarda)  [0, 56) idêntico ao de build/v9.mid: (trilha, tick de ataque, altura)
  M1  (guarda)  bin/conferir-digitos sai 0 no MIDI
  M2  (aceite)  nenhuma nota de classe 6/11 em [0, 56); nenhuma de classe 5/10 em [56, 112)
  M3  (aceite)  sem pausa geral (0,5 s ou mais sem nota soando) de sec(56) ao último note_off;
                mínimo de S em [sec(58)+3, sec(104)] no máximo 12 LU abaixo de S_eixo
  M4  (aceite)  S_final >= S_eixo + 1,0 LU
  M5  (guarda)  S_eixo >= máximo de S em [0, sec(52)] + 3,0 LU
  M6  (aceite)  RMS por compasso (astats, dB) em [76, 104): Spearman rho >= 0,6 contra o índice
  M7  (aceite)  ataques/compasso em [92,104) >= 1,5x [76,84); as 6 trilhas soam em cada
                compasso de [92, 112)
  M8  (aceite)  maior altura atacada em [96, 112) estritamente maior que em [0, 96)
  M9  (aceite)  último acorde tem as classes 2, 6, 9, com a mais grave da classe 2
  M10 (guarda)  20+ set_tempo, CC11 nas 6 trilhas com faixa >= 40, bpm médio de [104,112)
                <= 0,9x a mediana dos set_tempo fora de [56,58) e [104,112)
  M11 (guarda)  último ataque em 97,0 s ou antes; MP3 com 101 +- 0,15 s (ffprobe)
  M12 (guarda)  em todo ataque da melodia, nenhuma nota do acompanhamento soa acima dela
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

import mido

EIXO = 56
TRILHAS = ("Flauta", "Violino I", "Violino II", "Viola", "Violoncelo", "Piano")
TRILHAS_MELODIA = ("Violino I", "Flauta")
V9_MID = Path(__file__).resolve().parent.parent / "build" / "v9.mid"


# --------------------------------------------------------------------------------------
# Leitura do MIDI


def _ticks(trilha: mido.MidiTrack) -> list[int]:
    out, tick = [], 0
    for m in trilha:
        tick += m.time
        out.append(tick)
    return out


def _notas_por_trilha(mid: mido.MidiFile) -> dict[str, list[tuple[float, float, int]]]:
    """{nome: [(inicio_s, fim_s, altura)]}, em segundos, para as trilhas nomeadas."""
    tpb = mid.ticks_per_beat
    tempos = sorted((t, m.tempo) for tr in mid.tracks for t, m in
                     zip(_ticks(tr), tr) if m.type == "set_tempo")
    sec = _fabrica_sec(tempos, tpb)

    saida = {}
    for tr in mid.tracks:
        nome = next((m.name for m in tr if m.type == "track_name"), None)
        if nome not in TRILHAS:
            continue
        abertas: dict[int, list[int]] = {}
        notas = []
        tick = 0
        for m in tr:
            tick += m.time
            if m.type == "note_on" and m.velocity > 0:
                abertas.setdefault(m.note, []).append(tick)
            elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
                fila = abertas.get(m.note)
                if fila:
                    ini = fila.pop(0)
                    notas.append((sec(ini), sec(tick), m.note))
        saida[nome] = sorted(notas)
    return saida


def _notas_por_trilha_ticks(mid: mido.MidiFile) -> dict[str, list[tuple[int, int, int]]]:
    """{nome: [(tick_ini, tick_fim, altura)]}, para critérios que trabalham em tempos."""
    saida = {}
    for tr in mid.tracks:
        nome = next((m.name for m in tr if m.type == "track_name"), None)
        if nome not in TRILHAS:
            continue
        abertas: dict[int, list[int]] = {}
        notas = []
        tick = 0
        for m in tr:
            tick += m.time
            if m.type == "note_on" and m.velocity > 0:
                abertas.setdefault(m.note, []).append(tick)
            elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
                fila = abertas.get(m.note)
                if fila:
                    ini = fila.pop(0)
                    notas.append((ini, tick, m.note))
        saida[nome] = sorted(notas)
    return saida


def _fabrica_sec(tempos: list[tuple[int, int]], tpb: int):
    """sec(tick) -> segundos, seguindo o mapa de set_tempo (igual a expressao.resumo)."""
    import math

    def sec(tick: int) -> float:
        total = 0.0
        for (t0, us), (t1, _) in zip(tempos, tempos[1:] + [(math.inf, 0)]):
            total += (min(tick, t1) - t0) * us / tpb / 1e6
            if tick <= t1:
                break
        return total

    return sec


def _mapa_tempo(mid: mido.MidiFile):
    """sec(t) para t em unidades de tempo (semínima), e o inverso aproximado."""
    tpb = mid.ticks_per_beat
    tempos = sorted((t, m.tempo) for tr in mid.tracks for t, m in
                     zip(_ticks(tr), tr) if m.type == "set_tempo")
    sec_tick = _fabrica_sec(tempos, tpb)

    def sec(t: float) -> float:
        return sec_tick(round(t * tpb))

    return sec, tempos, tpb


# --------------------------------------------------------------------------------------
# ffmpeg / ffprobe


def _duracao(caminho: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", str(caminho)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _serie_s(mp3: Path) -> list[tuple[float, float]]:
    """[(t, S)] do loudness short-term do ffmpeg ebur128, um valor a cada ~100 ms.

    S abaixo de -70 LUFS (silêncio digital antes de o medidor convergir) é descartado.
    """
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp3),
                         "-af", "ebur128", "-f", "null", "-"],
                        capture_output=True, text=True)
    pares = re.findall(r"t:\s*([\d.]+).*?S:\s*(-?[\d.]+)", r.stderr)
    return [(float(t), float(s)) for t, s in pares if float(s) > -70]


def _rms_janela(mp3: Path, ini_s: float, fim_s: float) -> float | None:
    """Overall RMS level dB (astats) da janela [ini_s, fim_s). None se a janela for vazia."""
    dur = fim_s - ini_s
    if dur <= 0:
        return None
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(ini_s), "-t", str(dur),
                         "-i", str(mp3), "-af", "astats=metadata=0", "-f", "null", "-"],
                        capture_output=True, text=True)
    valores = re.findall(r"RMS level dB:\s*(-?[\d.]+)", r.stderr)
    if not valores:
        return None
    return float(valores[-1])  # a última ocorrência é o bloco "Overall"


# --------------------------------------------------------------------------------------
# Critérios


def m0_intacta(mid: mido.MidiFile, v9: mido.MidiFile) -> tuple[str, str]:
    a = _notas_por_trilha_ticks(mid)
    b = _notas_por_trilha_ticks(v9)
    tpb_a, tpb_v9 = mid.ticks_per_beat, v9.ticks_per_beat
    if tpb_a != tpb_v9:
        return "UNKNOWN", f"ticks_per_beat diferente ({tpb_a} vs {tpb_v9})"
    lim_a, lim_v9 = round(EIXO * tpb_a), round(EIXO * tpb_v9)
    diffs = []
    for nome in TRILHAS:
        na = [(t0, alt) for t0, t1, alt in a.get(nome, []) if t0 < lim_a]
        nb = [(t0, alt) for t0, t1, alt in b.get(nome, []) if t0 < lim_v9]
        if na != nb:
            diffs.append(nome)
    if diffs:
        return "FAIL", f"trilhas divergentes em [0, {EIXO}): {', '.join(diffs)}"
    return "PASS", f"[0, {EIXO}) idêntico ao de build/v9.mid nas {len(TRILHAS)} trilhas"


def m1_conferir_digitos(midi_path: Path) -> tuple[str, str]:
    r = subprocess.run([str(Path(__file__).resolve().parent.parent / "bin" / "conferir-digitos"),
                         str(midi_path)], capture_output=True, text=True)
    if r.returncode == 0:
        return "PASS", r.stdout.strip()
    if r.returncode == 1:
        return "FAIL", r.stdout.strip() or r.stderr.strip()
    return "UNKNOWN", (r.stdout.strip() or r.stderr.strip())


def m2_modo(mid: mido.MidiFile) -> tuple[str, str]:
    tpb = mid.ticks_per_beat
    lim = round(EIXO * tpb)
    notas = _notas_por_trilha_ticks(mid)
    antes_ruins = [(nome, t0, alt) for nome, ns in notas.items() for t0, t1, alt in ns
                   if t0 < lim and alt % 12 in (6, 11)]
    depois_ruins = [(nome, t0, alt) for nome, ns in notas.items() for t0, t1, alt in ns
                     if t0 >= lim and alt % 12 in (5, 10)]
    ok = not antes_ruins and not depois_ruins
    detalhe = (f"{len(antes_ruins)} nota(s) de classe 6/11 antes do eixo, "
               f"{len(depois_ruins)} de classe 5/10 depois")
    return ("PASS" if ok else "FAIL"), detalhe


def _intervalos_soando(notas: dict[str, list[tuple[float, float, int]]]) -> list[tuple[float, float]]:
    """[(inicio, fim)] mesclados de todo intervalo em que ao menos uma nota soa."""
    todos = sorted((t0, t1) for ns in notas.values() for t0, t1, _ in ns)
    if not todos:
        return []
    mesclados = [list(todos[0])]
    for t0, t1 in todos[1:]:
        if t0 <= mesclados[-1][1]:
            mesclados[-1][1] = max(mesclados[-1][1], t1)
        else:
            mesclados.append([t0, t1])
    return [(a, b) for a, b in mesclados]


def m3_sem_pausa_e_sussurro(mid: mido.MidiFile, serie_s: list[tuple[float, float]],
                             s_eixo: float | None) -> tuple[str, str]:
    sec, *_ = _mapa_tempo(mid)
    notas = _notas_por_trilha(mid)
    intervalos = _intervalos_soando(notas)
    sec56 = sec(EIXO)
    ultimo_off = max((t1 for ns in notas.values() for _, t1, _ in ns), default=0.0)
    gaps = []
    cursor = sec56
    for a, b in intervalos:
        if b <= sec56:
            continue
        inicio_gap = max(cursor, sec56)
        if a > inicio_gap:
            gaps.append((inicio_gap, a))
        cursor = max(cursor, b)
    if ultimo_off > cursor:
        gaps.append((cursor, ultimo_off))
    pausas_grandes = [(a, b) for a, b in gaps if b - a >= 0.5]

    janela_ini, janela_fim = sec(58) + 3, sec(104)
    janela = [s for t, s in serie_s if janela_ini <= t <= janela_fim]
    if s_eixo is None:
        return "UNKNOWN", "S_eixo indisponível (depende de M5)"
    if not janela:
        return "UNKNOWN", f"nenhum valor de S em [{janela_ini:.2f}, {janela_fim:.2f}]"
    minimo = min(janela)
    ok_pausa = not pausas_grandes
    ok_sussurro = minimo >= s_eixo - 12.0
    ok = ok_pausa and ok_sussurro
    detalhe = (f"{len(pausas_grandes)} pausa(s) geral(is) >= 0,5 s depois do eixo; "
               f"mínimo de S em [{janela_ini:.2f},{janela_fim:.2f}] = {minimo:.1f} LUFS "
               f"(S_eixo {s_eixo:.1f}, piso {s_eixo - 12.0:.1f})")
    return ("PASS" if ok else "FAIL"), detalhe


def _s_eixo(mid: mido.MidiFile, serie_s: list[tuple[float, float]]) -> float | None:
    sec, *_ = _mapa_tempo(mid)
    ini, fim = sec(EIXO), sec(58) + 3
    janela = [s for t, s in serie_s if ini <= t <= fim]
    return max(janela) if janela else None


def _s_final(mid: mido.MidiFile, serie_s: list[tuple[float, float]]) -> float | None:
    sec, *_ = _mapa_tempo(mid)
    ini = sec(96)
    janela = [s for t, s in serie_s if t >= ini]
    return max(janela) if janela else None


def m4_final_acima_do_eixo(s_eixo: float | None, s_final: float | None) -> tuple[str, str]:
    if s_eixo is None or s_final is None:
        return "UNKNOWN", f"S_eixo={s_eixo}, S_final={s_final}"
    ok = s_final >= s_eixo + 1.0
    return ("PASS" if ok else "FAIL"), f"S_final {s_final:.1f} LUFS, S_eixo {s_eixo:.1f} LUFS"


def m5_eixo_e_primeiro_pico(mid: mido.MidiFile, serie_s: list[tuple[float, float]],
                             s_eixo: float | None) -> tuple[str, str]:
    sec, *_ = _mapa_tempo(mid)
    fim = sec(52)
    janela = [s for t, s in serie_s if t <= fim]
    if s_eixo is None:
        return "UNKNOWN", "S_eixo indisponível"
    if not janela:
        return "UNKNOWN", f"nenhum valor de S em [0, {fim:.2f}]"
    maximo = max(janela)
    ok = s_eixo >= maximo + 3.0
    return ("PASS" if ok else "FAIL"), f"S_eixo {s_eixo:.1f} LUFS, máximo antes {maximo:.1f} LUFS"


def _compasso_ticks(mid: mido.MidiFile, compasso: int) -> tuple[float, float]:
    """Segundos [ini, fim) do compasso de índice `compasso` (4 tempos, compasso 0 = tempo 0)."""
    sec, *_ = _mapa_tempo(mid)
    return sec(compasso * 4), sec((compasso + 1) * 4)


def m6_crescendo_a_linha(mid: mido.MidiFile, mp3: Path) -> tuple[str, str]:
    compassos = range(19, 26)  # tempo 76 = compasso 19 (76/4), até 104 (exclusive) = compasso 26
    rms = []
    for c in compassos:
        ini, fim = _compasso_ticks(mid, c)
        v = _rms_janela(mp3, ini, fim)
        rms.append(v)
    if any(v is None for v in rms):
        return "UNKNOWN", f"RMS indisponível em algum dos {len(rms)} compassos"
    indices = list(range(len(rms)))
    rho = _spearman(indices, rms)
    ok = rho >= 0.6
    return ("PASS" if ok else "FAIL"), f"Spearman rho={rho:.2f} nos 7 compassos de [76,104)"


def _spearman(xs: list[float], ys: list[float]) -> float:
    def postos(vals: list[float]) -> list[float]:
        ordenado = sorted(range(len(vals)), key=lambda i: vals[i])
        postos = [0.0] * len(vals)
        i = 0
        while i < len(ordenado):
            j = i
            while j + 1 < len(ordenado) and vals[ordenado[j + 1]] == vals[ordenado[i]]:
                j += 1
            posto_medio = (i + j) / 2 + 1
            for k in range(i, j + 1):
                postos[ordenado[k]] = posto_medio
            i = j + 1
        return postos

    px, py = postos(xs), postos(ys)
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = statistics.mean(px), statistics.mean(py)
    cov = sum((a - mx) * (b - my) for a, b in zip(px, py))
    varx = sum((a - mx) ** 2 for a in px)
    vary = sum((b - my) ** 2 for b in py)
    if varx == 0 or vary == 0:
        return 0.0
    return cov / (varx ** 0.5 * vary ** 0.5)


def m7_adensamento(mid: mido.MidiFile) -> tuple[str, str]:
    notas = _notas_por_trilha_ticks(mid)
    tpb = mid.ticks_per_beat

    def ataques_no_intervalo(ini_t: float, fim_t: float) -> int:
        ini, fim = round(ini_t * tpb), round(fim_t * tpb)
        return sum(1 for ns in notas.values() for t0, _, _ in ns if ini <= t0 < fim)

    n_a = ataques_no_intervalo(76, 84) / 8
    n_b = ataques_no_intervalo(92, 104) / 12
    ok_crescimento = n_b >= 1.5 * n_a if n_a > 0 else n_b > 0

    faltam = []
    for c in range(23, 28):  # compassos cobrindo [92, 112): tempo 92/4=23 até 112/4=28
        ini_t, fim_t = c * 4, (c + 1) * 4
        ini, fim = round(ini_t * tpb), round(fim_t * tpb)
        for nome in TRILHAS:
            soa = any(t0 < fim and t1 > ini for t0, t1, _ in notas.get(nome, []))
            if not soa:
                faltam.append((c, nome))

    ok = ok_crescimento and not faltam
    detalhe = (f"ataques/compasso [76,84)={n_a:.2f}, [92,104)={n_b:.2f}; "
               f"{len(faltam)} (compasso,trilha) sem som em [92,112)")
    return ("PASS" if ok else "FAIL"), detalhe


def m8_registro(mid: mido.MidiFile) -> tuple[str, str]:
    notas = _notas_por_trilha_ticks(mid)
    tpb = mid.ticks_per_beat
    lim96, lim112 = round(96 * tpb), round(112 * tpb)
    antes = [alt for ns in notas.values() for t0, t1, alt in ns if t0 < lim96]
    depois = [alt for ns in notas.values() for t0, t1, alt in ns if lim96 <= t0 < lim112]
    if not depois:
        return "UNKNOWN", "sem ataques em [96, 112)"
    max_antes = max(antes) if antes else -1
    max_depois = max(depois)
    ok = max_depois > max_antes
    return ("PASS" if ok else "FAIL"), f"maior altura em [96,112)={max_depois}, em [0,96)={max_antes}"


def m9_acorde_final(mid: mido.MidiFile) -> tuple[str, str]:
    """O acorde no início do compasso final (tempo 104), não no instante do último ataque.

    É no início da cadência (allargando) que a nota da melodia se junta ao resto: na v9 é
    o Fá natural da picardia tardia, que ainda briga com o acorde; na v10 tem de já ser o
    Fá♯ do acorde de chegada. Medir só o último ataque isolado (quando cordas e sopro já
    soltaram) esconde essa briga e deixa a régua frouxa o bastante para passar na v9.
    """
    notas = _notas_por_trilha(mid)
    sec, *_ = _mapa_tempo(mid)
    t = sec(104)
    soando = [alt for nome in TRILHAS for t0, t1, alt in notas.get(nome, []) if t0 <= t < t1]
    if not soando:
        return "UNKNOWN", f"nenhuma nota soando no início do compasso final (t={t:.2f}s)"
    classes = {alt % 12 for alt in soando}
    tem_classes = {2, 6, 9} <= classes
    mais_grave = min(soando)
    ok_grave = mais_grave % 12 == 2
    ok = tem_classes and ok_grave
    detalhe = (f"em t={t:.2f}s: classes {sorted(classes)}, nota mais grave {mais_grave} "
               f"(classe {mais_grave % 12})")
    return ("PASS" if ok else "FAIL"), detalhe


def m10_andamento_e_cc11(mid: mido.MidiFile) -> tuple[str, str]:
    sec, tempos, tpb = _mapa_tempo(mid)
    n_set_tempo = len(tempos)
    ok_qtd = n_set_tempo >= 20

    cc11_por_trilha = {}
    for tr in mid.tracks:
        nome = next((m.name for m in tr if m.type == "track_name"), None)
        if nome not in TRILHAS:
            continue
        valores = [m.value for m in tr if m.type == "control_change" and m.control == 11]
        cc11_por_trilha[nome] = valores

    faltam_cc11 = [n for n in TRILHAS if not cc11_por_trilha.get(n)]
    faixas_curtas = [n for n, vs in cc11_por_trilha.items() if vs and (max(vs) - min(vs)) < 40]
    ok_cc11 = not faltam_cc11 and not faixas_curtas

    fora = [us for t, us in tempos if not (round(EIXO * tpb) <= t < round((EIXO + 2) * tpb))
            and not (round(104 * tpb) <= t < round(112 * tpb))]
    dentro_final = [us for t, us in tempos if round(104 * tpb) <= t < round(112 * tpb)]
    if not fora or not dentro_final:
        return "UNKNOWN", "faltam set_tempo fora do eixo/final ou dentro de [104,112) para medir"
    mediana_bpm = statistics.median(60e6 / us for us in fora)
    bpm_final = statistics.mean(60e6 / us for us in dentro_final)
    ok_final = bpm_final <= 0.9 * mediana_bpm

    ok = ok_qtd and ok_cc11 and ok_final
    detalhe = (f"{n_set_tempo} set_tempo; CC11 faltando em {faltam_cc11}, faixa curta em "
               f"{faixas_curtas}; bpm médio final {bpm_final:.1f} vs 0,9x mediana "
               f"{0.9 * mediana_bpm:.1f}")
    return ("PASS" if ok else "FAIL"), detalhe


def m11_duracao(mid: mido.MidiFile, mp3: Path) -> tuple[str, str]:
    notas = _notas_por_trilha(mid)
    ataques = [t0 for ns in notas.values() for t0, t1, alt in ns]
    if not ataques:
        return "UNKNOWN", "sem ataques"
    ultimo_ataque = max(ataques)
    ok_ataque = ultimo_ataque <= 97.0
    if not mp3.exists():
        return "UNKNOWN", f"último ataque em {ultimo_ataque:.2f} s; sem MP3"
    dur = _duracao(mp3)
    ok_dur = abs(dur - 101.0) <= 0.15
    ok = ok_ataque and ok_dur
    return ("PASS" if ok else "FAIL"), f"último ataque em {ultimo_ataque:.2f} s; MP3 de {dur:.3f} s"


def m12_c8(mid: mido.MidiFile) -> tuple[str, str]:
    """Nenhuma nota do acompanhamento soa acima da melodia, em todo ataque da melodia.

    Quando Violino I e Flauta atacam juntas no mesmo instante (dobra), a nota mais
    aguda das duas é a melodia soante naquele instante; a outra, sendo dobra da mesma
    linha, não conta como acompanhamento acima dela.
    """
    notas = _notas_por_trilha(mid)
    melodia_bruta = sorted((t0, t1, alt, nome) for nome in TRILHAS_MELODIA
                            for t0, t1, alt in notas.get(nome, []))
    todas = [(t0, t1, alt) for ns in notas.values() for t0, t1, alt in ns]

    # Agrupa ataques simultâneos das trilhas de melodia (mesmo t0) e fica só com o mais agudo.
    melodia: dict[float, tuple[float, int]] = {}
    for t0, t1, alt, nome in melodia_bruta:
        atual = melodia.get(t0)
        if atual is None or alt > atual[1]:
            melodia[t0] = (t1, alt)

    violacoes = []
    for t0, (t1, alt) in sorted(melodia.items()):
        acima = [a for a0, a1, a in todas if a0 <= t0 < a1 and a > alt]
        if acima:
            violacoes.append((t0, alt, max(acima)))
    ok = not violacoes
    detalhe = f"{len(violacoes)} ataque(s) da melodia com acompanhamento acima"
    if violacoes:
        t0, alt, acima = violacoes[0]
        detalhe += f"; primeiro em t={t0:.2f}s nota={alt} vs acima={acima}"
    return ("PASS" if ok else "FAIL"), detalhe


# --------------------------------------------------------------------------------------
# main


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: avaliar_v10.py <arquivo.mid>")
        return 2
    midi_path = Path(sys.argv[1])
    mp3_path = midi_path.with_suffix(".mp3")
    sidecar_path = midi_path.with_name(midi_path.stem + "-mapeamento.json")

    if not midi_path.exists():
        print(f"UNKNOWN  (todos)  arquivo ausente: {midi_path}")
        return 2
    mid = mido.MidiFile(str(midi_path))
    if not V9_MID.exists():
        print(f"UNKNOWN  (todos)  arquivo de referência ausente: {V9_MID}")
        return 2
    v9 = mido.MidiFile(str(V9_MID))

    serie_s = _serie_s(mp3_path) if mp3_path.exists() else []
    s_eixo = _s_eixo(mid, serie_s) if serie_s else None
    s_final = _s_final(mid, serie_s) if serie_s else None

    resultados: list[tuple[str, str, str]] = []

    def add(nome: str, status: str, detalhe: str) -> None:
        resultados.append((nome, status, detalhe))

    try:
        add("M0", *m0_intacta(mid, v9))
    except Exception as e:
        add("M0", "UNKNOWN", f"erro: {e}")

    try:
        add("M1", *m1_conferir_digitos(midi_path))
    except Exception as e:
        add("M1", "UNKNOWN", f"erro: {e}")

    try:
        add("M2", *m2_modo(mid))
    except Exception as e:
        add("M2", "UNKNOWN", f"erro: {e}")

    if not mp3_path.exists():
        add("M3", "UNKNOWN", f"MP3 ausente: {mp3_path}")
    elif not serie_s:
        add("M3", "UNKNOWN", "série de S vazia (ffmpeg ebur128 não produziu leitura)")
    else:
        try:
            add("M3", *m3_sem_pausa_e_sussurro(mid, serie_s, s_eixo))
        except Exception as e:
            add("M3", "UNKNOWN", f"erro: {e}")

    if s_eixo is None or s_final is None:
        add("M4", "UNKNOWN", f"S_eixo={s_eixo}, S_final={s_final}")
    else:
        add("M4", *m4_final_acima_do_eixo(s_eixo, s_final))

    if not mp3_path.exists() or not serie_s:
        add("M5", "UNKNOWN", "sem série de S")
    else:
        try:
            add("M5", *m5_eixo_e_primeiro_pico(mid, serie_s, s_eixo))
        except Exception as e:
            add("M5", "UNKNOWN", f"erro: {e}")

    if not mp3_path.exists():
        add("M6", "UNKNOWN", f"MP3 ausente: {mp3_path}")
    else:
        try:
            add("M6", *m6_crescendo_a_linha(mid, mp3_path))
        except Exception as e:
            add("M6", "UNKNOWN", f"erro: {e}")

    try:
        add("M7", *m7_adensamento(mid))
    except Exception as e:
        add("M7", "UNKNOWN", f"erro: {e}")

    try:
        add("M8", *m8_registro(mid))
    except Exception as e:
        add("M8", "UNKNOWN", f"erro: {e}")

    try:
        add("M9", *m9_acorde_final(mid))
    except Exception as e:
        add("M9", "UNKNOWN", f"erro: {e}")

    try:
        add("M10", *m10_andamento_e_cc11(mid))
    except Exception as e:
        add("M10", "UNKNOWN", f"erro: {e}")

    if not mp3_path.exists():
        add("M11", "UNKNOWN", f"MP3 ausente: {mp3_path}")
    else:
        try:
            add("M11", *m11_duracao(mid, mp3_path))
        except Exception as e:
            add("M11", "UNKNOWN", f"erro: {e}")

    try:
        add("M12", *m12_c8(mid))
    except Exception as e:
        add("M12", "UNKNOWN", f"erro: {e}")

    for nome, status, detalhe in resultados:
        print(f"{status}  {nome}  {detalhe}")

    n_pass = sum(1 for _, s, _ in resultados if s == "PASS")
    n_fail = sum(1 for _, s, _ in resultados if s == "FAIL")
    print(f"{n_pass}/{len(resultados)} critérios")

    if n_fail:
        return 1
    if n_pass < len(resultados):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
