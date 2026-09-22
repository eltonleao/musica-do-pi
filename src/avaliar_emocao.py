"""Oráculo da emoção: mede a v8 expressiva e a v9 contra a tabela "O oráculo"
do plano P10 (Projects/Música do Pi/plans/epic-fundacao/todo/P10-v9-o-arrepio-no-eixo.md).

Uso: python src/avaliar_emocao.py <arquivo.mid> --etapa expressiva|v9

Deriva `<nome>.mp3` e `<nome>-mapeamento.json` do mesmo caminho do MIDI.
Imprime uma linha `PASS|FAIL|UNKNOWN  <nome>  <detalhe>` por critério e fecha
com `n/N critérios`. Sai 0 só com todos PASS, 1 com algum FAIL, 2 quando falta
arquivo ou o formato não dá para medir (critério sem arquivo para medir é
UNKNOWN, e UNKNOWN nunca vira PASS).

EIXO = 56 é constante deste arquivo, não vem do sidecar. "Soando" é entre
note_on e note_off. "Meio compasso" são 2 tempos (semínimas). Os segundos
saem do mapa de andamento (todos os `set_tempo`) do próprio MIDI.

Na etapa expressiva rodam E0-E8; na v9 rodam E1-E8 e C1-C8 (E0 só existe na
expressiva, e compara com build/v8.mid).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

import mido

EIXO = 56                      # tempo (semínima) do eixo; constante, não vem do sidecar
JANELA_EIXO = (56, 58)         # meio compasso do eixo, usado para excluir da mediana/correlação
C27_28 = (104, 112)            # tempos dos dois últimos compassos
NOMES = ("Flauta", "Violino I", "Violino II", "Viola", "Violoncelo", "Piano")
MELODIA_NOMES = ("Violino I", "Flauta")
ACOMPANHAMENTO_NOMES = ("Violino II", "Viola", "Violoncelo", "Piano")
RAIZ = Path(__file__).resolve().parent.parent


class Peca:
    """Um MIDI lido uma vez: trilhas por nome, mapa de andamento, CC11 e notas."""

    def __init__(self, midi_path: Path):
        self.caminho = midi_path
        self.arq = mido.MidiFile(str(midi_path))
        self.tpb = self.arq.ticks_per_beat
        self.eventos_por_trilha: dict[str, list[tuple[int, mido.Message]]] = {}
        eventos_tempo = []
        for trilha in self.arq.tracks:
            tick = 0
            nome = None
            eventos = []
            for m in trilha:
                tick += m.time
                eventos.append((tick, m))
                if m.type == "track_name":
                    nome = m.name
                if m.type == "set_tempo":
                    eventos_tempo.append((tick, m.tempo))
            if nome in NOMES:
                self.eventos_por_trilha[nome] = eventos
        eventos_tempo.sort()
        if not eventos_tempo or eventos_tempo[0][0] != 0:
            eventos_tempo = [(0, 500000)] + eventos_tempo
        self.eventos_tempo = eventos_tempo

    def tempo_pos(self, tick: int) -> float:
        """Tick em unidade de tempo (semínima), fracionário."""
        return tick / self.tpb

    def tick_de_tempo(self, tempo: float) -> int:
        return round(tempo * self.tpb)

    def seg(self, tick: int) -> float:
        total = 0.0
        eventos = self.eventos_tempo
        for i, (t0, us) in enumerate(eventos):
            t1 = eventos[i + 1][0] if i + 1 < len(eventos) else None
            if t1 is not None and tick >= t1:
                total += (t1 - t0) * us / self.tpb / 1e6
            else:
                total += (tick - t0) * us / self.tpb / 1e6
                break
        return total

    def notas(self, nome: str) -> list[tuple[int, int, int, int]]:
        """(tick_on, tick_off, altura, velocity) por trilha, ordenado por tick_on."""
        abertas: dict[int, list[tuple[int, int]]] = {}
        out = []
        for tick, m in self.eventos_por_trilha.get(nome, []):
            if m.type == "note_on" and m.velocity > 0:
                abertas.setdefault(m.note, []).append((tick, m.velocity))
            elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
                fila = abertas.get(m.note)
                if fila:
                    tick_on, vel = fila.pop(0)
                    out.append((tick_on, tick, m.note, vel))
        out.sort()
        return out

    def cc(self, nome: str, controlador: int) -> list[tuple[int, int]]:
        eventos = sorted((t, m.value) for t, m in self.eventos_por_trilha.get(nome, [])
                         if m.type == "control_change" and m.control == controlador)
        return eventos

    def cc_em(self, nome: str, controlador: int, tick: int) -> int | None:
        valor = None
        for t, v in self.cc(nome, controlador):
            if t <= tick:
                valor = v
            else:
                break
        return valor

    def ataques_melodia(self) -> list[tuple[int, int, int, int, str]]:
        """(tick_on, tick_off, altura, velocity, trilha) de Violino I + Flauta, em ordem de tick."""
        out = []
        for nome in MELODIA_NOMES:
            out += [(t0, t1, alt, v, nome) for t0, t1, alt, v in self.notas(nome)]
        out.sort()
        return out

    def soando_todas(self) -> list[tuple[float, float]]:
        """Intervalos (em segundos) em que ao menos uma das 6 trilhas soa."""
        intervalos = []
        for nome in NOMES:
            for t0, t1, _, _ in self.notas(nome):
                intervalos.append((self.seg(t0), self.seg(t1)))
        intervalos.sort()
        fundidos: list[list[float]] = []
        for ini, fim in intervalos:
            if fundidos and ini <= fundidos[-1][1]:
                fundidos[-1][1] = max(fundidos[-1][1], fim)
            else:
                fundidos.append([ini, fim])
        return [(a, b) for a, b in fundidos]

    def instrumentos_soando_em(self, tick0: int, tick1: int) -> set[str]:
        out = set()
        for nome in NOMES:
            for t0, t1, _, _ in self.notas(nome):
                if t0 < tick1 and t1 > tick0:
                    out.add(nome)
                    break
        return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else None


Resultado = tuple[str, str, str]  # nome, status (PASS/FAIL/UNKNOWN), detalhe


def crit_e0(peca: Peca, ref: Peca) -> Resultado:
    def conjunto(p: Peca) -> set[tuple[str, int, int]]:
        return {(nome, t0, alt) for nome in NOMES for t0, _, alt, _ in p.notas(nome)}
    a, b = conjunto(peca), conjunto(ref)
    if a == b:
        return ("E0", "PASS", "mesmo conjunto (trilha, tick, altura) do build/v8.mid")
    return ("E0", "FAIL", f"{len(a - b)} eventos a mais, {len(b - a)} a menos que o build/v8.mid")


def crit_e1(peca: Peca) -> tuple[Resultado, float | None]:
    eventos = peca.eventos_tempo
    if len(eventos) < 20:
        return (("E1", "FAIL", f"{len(eventos)} eventos set_tempo, esperado 20 ou mais"), None)
    filtrados = [(t / peca.tpb, 60e6 / us) for t, us in eventos
                if not (JANELA_EIXO[0] <= t / peca.tpb < JANELA_EIXO[1])
                and not (C27_28[0] <= t / peca.tpb < C27_28[1])]
    if len(filtrados) < 2:
        return (("E1", "UNKNOWN", "sem eventos suficientes fora da pausa e dos c27-c28"), None)
    bpms = [b for _, b in filtrados]
    mediana = statistics.median(bpms)
    acima = any(b >= mediana * 1.05 for b in bpms)
    abaixo = any(b <= mediana * 0.95 for b in bpms)
    saltos_ok = all(abs(b2 - b1) <= 0.15 * b1 for b1, b2 in zip(bpms, bpms[1:]))
    if acima and abaixo and saltos_ok:
        return (("E1", "PASS", f"{len(eventos)} eventos, mediana {mediana:.1f} bpm"), mediana)
    detalhe = f"acima={acima} abaixo={abaixo} saltos_ok={saltos_ok} mediana={mediana:.1f}"
    return (("E1", "FAIL", detalhe), mediana)


def crit_e2(peca: Peca) -> Resultado:
    faltando, curtos = [], []
    for nome in NOMES:
        valores = [v for _, v in peca.cc(nome, 11)]
        if not valores:
            faltando.append(nome)
            continue
        faixa = max(valores) - min(valores)
        if faixa < 40:
            curtos.append(f"{nome}={faixa}")
    if faltando:
        return ("E2", "FAIL", f"sem CC11: {', '.join(faltando)}")
    if curtos:
        return ("E2", "FAIL", f"faixa < 40: {', '.join(curtos)}")
    return ("E2", "PASS", "CC11 nas 6 trilhas com faixa >= 40")


def crit_e3(peca: Peca) -> Resultado:
    meios = peca.tpb and (max(t for t, _ in peca.eventos_tempo + [(0, 0)]) // peca.tpb // 2 + 1)
    fim_tick = max((t1 for nome in NOMES for _, t1, _, _ in peca.notas(nome)), default=0)
    total_meios = int(peca.tempo_pos(fim_tick) // 2) + 1
    xs, ys = [], []
    for h in range(total_meios):
        if JANELA_EIXO[0] <= 2 * h < JANELA_EIXO[1]:
            continue
        tick = peca.tick_de_tempo(2 * h)
        bpm = None
        for t, us in peca.eventos_tempo:
            if t <= tick:
                bpm = 60e6 / us
            else:
                break
        if bpm is None:
            continue
        valores_cc = [peca.cc_em(nome, 11, tick) for nome in NOMES]
        valores_cc = [v for v in valores_cc if v is not None]
        if not valores_cc:
            continue
        xs.append(bpm)
        ys.append(sum(valores_cc) / len(valores_cc))
    r = _pearson(xs, ys)
    if r is None:
        return ("E3", "UNKNOWN", "dados insuficientes para Pearson")
    if r >= 0.5:
        return ("E3", "PASS", f"r={r:.2f}")
    return ("E3", "FAIL", f"r={r:.2f}, esperado >= 0,5")


def crit_e4(peca: Peca) -> Resultado:
    intervalos = peca.soando_todas()
    if not intervalos:
        return ("E4", "UNKNOWN", "nenhuma nota soando")
    ultimo_off = intervalos[-1][1]
    gaps = []
    for (a0, a1), (b0, b1) in zip(intervalos, intervalos[1:]):
        dur = b0 - a1
        if dur >= 0.5 and b0 < ultimo_off:
            gaps.append((a1, dur))
    if len(gaps) != 1:
        return ("E4", "FAIL", f"{len(gaps)} pausas gerais de 0,5s ou mais, esperado 1")
    inicio, dur = gaps[0]
    if not (1.5 <= dur <= 3.0):
        return ("E4", "FAIL", f"pausa de {dur:.2f}s, esperado 1,5 a 3,0")
    seg_eixo = peca.seg(peca.tick_de_tempo(EIXO))
    if not (seg_eixo <= inicio <= seg_eixo + 2):
        return ("E4", "FAIL", f"pausa começa em {inicio:.2f}s, fora de [{seg_eixo:.2f}, {seg_eixo + 2:.2f}]")
    return ("E4", "PASS", f"pausa de {dur:.2f}s a partir de {inicio:.2f}s")


def crit_e5(peca: Peca) -> Resultado:
    ataques = peca.ataques_melodia()
    tick56 = peca.tick_de_tempo(EIXO)
    ataques_no_eixo = [a for a in ataques if a[0] == tick56]
    if not ataques_no_eixo:
        return ("E5", "FAIL", f"nenhum ataque da melodia no tempo {EIXO}")
    cc_eixo = [peca.cc_em(nome, 11, tick56) for nome in NOMES]
    cc_eixo = [v for v in cc_eixo if v is not None]
    if not cc_eixo:
        return ("E5", "UNKNOWN", "sem CC11 no tempo do eixo")
    media_eixo = sum(cc_eixo) / len(cc_eixo)
    fora = [(t0, v) for t0, t1, alt, v, nome in ataques
           if not (peca.tempo_pos(t0) >= 55 and peca.tempo_pos(t0) < 57)]
    for t0, _ in fora:
        cc = [peca.cc_em(nome, 11, t0) for nome in NOMES]
        cc = [v for v in cc if v is not None]
        if cc and sum(cc) / len(cc) >= media_eixo:
            return ("E5", "FAIL", f"CC11 no tempo {peca.tempo_pos(t0):.2f} >= o do eixo")
    janela = [(t0, v) for t0, t1, alt, v, nome in ataques if 55 <= peca.tempo_pos(t0) < 57]
    fora_max = max((v for _, v in fora), default=-1)
    janela_max = max((v for _, v in janela), default=-1)
    if janela_max <= fora_max:
        return ("E5", "FAIL", "maior velocity da melodia não cai dentro de [55,57)")
    return ("E5", "PASS", f"CC11 do eixo={media_eixo:.1f}, maior velocity em [55,57)")


def crit_e6(peca: Peca) -> Resultado:
    intervalos = peca.soando_todas()
    if len(intervalos) < 2:
        return ("E6", "UNKNOWN", "sem pausa detectável para achar o ataque seguinte")
    tick56 = peca.tick_de_tempo(EIXO)
    cc_eixo = [peca.cc_em(nome, 11, tick56) for nome in NOMES]
    cc_eixo = [v for v in cc_eixo if v is not None]
    if not cc_eixo:
        return ("E6", "UNKNOWN", "sem CC11 no tempo do eixo")
    media_eixo = sum(cc_eixo) / len(cc_eixo)
    gaps = [(a1, b0) for (a0, a1), (b0, b1) in zip(intervalos, intervalos[1:]) if b0 - a1 >= 0.5]
    if len(gaps) != 1:
        return ("E6", "UNKNOWN", f"{len(gaps)} pausas gerais, esperado 1")
    _, retomada_seg = gaps[0]
    trilhas_retomam = [nome for nome in NOMES
                       if any(abs(peca.seg(t0) - retomada_seg) < 1e-6 for t0, _, _, _ in peca.notas(nome))]
    if not trilhas_retomam:
        return ("E6", "UNKNOWN", "nenhuma trilha ataca exatamente na retomada")
    cc_retomada = [peca.cc_em(nome, 11, peca.tick_de_tempo(peca.tempo_pos(round(retomada_seg))))
                  for nome in trilhas_retomam]
    tick_retomada = min(t0 for nome in trilhas_retomam for t0, _, _, _ in peca.notas(nome)
                        if abs(peca.seg(t0) - retomada_seg) < 1e-6)
    cc_retomada = [peca.cc_em(nome, 11, tick_retomada) for nome in trilhas_retomam]
    cc_retomada = [v for v in cc_retomada if v is not None]
    if not cc_retomada:
        return ("E6", "UNKNOWN", "sem CC11 na retomada")
    media_retomada = sum(cc_retomada) / len(cc_retomada)
    if media_retomada <= 0.5 * media_eixo:
        return ("E6", "PASS", f"CC11 retomada={media_retomada:.1f} <= 0,5 x eixo={media_eixo:.1f}")
    return ("E6", "FAIL", f"CC11 retomada={media_retomada:.1f} > 0,5 x eixo={media_eixo:.1f}")


def crit_e7(peca: Peca, mediana: float | None) -> Resultado:
    if mediana is None:
        return ("E7", "UNKNOWN", "mediana do E1 indisponível")
    tick0, tick1 = peca.tick_de_tempo(C27_28[0]), peca.tick_de_tempo(C27_28[1])
    dur_min = (peca.seg(tick1) - peca.seg(tick0)) / 60
    if dur_min <= 0:
        return ("E7", "UNKNOWN", "duração dos c27-c28 não positiva")
    bpm_medio = 8 / dur_min
    if bpm_medio <= 0.9 * mediana:
        return ("E7", "PASS", f"bpm médio c27-c28={bpm_medio:.1f} <= 0,9 x mediana={mediana:.1f}")
    return ("E7", "FAIL", f"bpm médio c27-c28={bpm_medio:.1f} > 0,9 x mediana={mediana:.1f}")


def crit_e8(peca: Peca) -> Resultado:
    ultimo_tick = max((t0 for nome in NOMES for t0, _, _, _ in peca.notas(nome)), default=None)
    if ultimo_tick is None:
        return ("E8", "UNKNOWN", "nenhuma nota encontrada")
    ultimo_seg = peca.seg(ultimo_tick)
    if ultimo_seg > 97.0:
        return ("E8", "FAIL", f"último ataque em {ultimo_seg:.2f}s, esperado <= 97,0")
    mp3 = peca.caminho.with_suffix(".mp3")
    if not mp3.exists():
        return ("E8", "UNKNOWN", f"falta {mp3}")
    try:
        saida = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "csv=p=0", str(mp3)], capture_output=True, text=True, check=True)
        duracao = float(saida.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        return ("E8", "UNKNOWN", f"ffprobe falhou: {e}")
    if abs(duracao - 101.0) > 0.15:
        return ("E8", "FAIL", f"mp3 com {duracao:.2f}s, esperado 101 +-0,15")
    return ("E8", "PASS", f"último ataque em {ultimo_seg:.2f}s, mp3 com {duracao:.2f}s")


def crit_c1(peca: Peca) -> Resultado:
    r = subprocess.run([sys.executable, str(RAIZ / "src" / "conferir_digitos.py"), str(peca.caminho)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return ("C1", "PASS", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "conferir-digitos ok")
    if r.returncode == 1:
        return ("C1", "FAIL", (r.stdout.strip() or r.stderr.strip()))
    return ("C1", "UNKNOWN", (r.stdout.strip() or r.stderr.strip()))


def _sidecar(peca: Peca) -> dict | None:
    caminho = peca.caminho.with_name(peca.caminho.stem + "-mapeamento.json")
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def crit_c2(peca: Peca) -> Resultado:
    tick56 = peca.tick_de_tempo(EIXO)
    fora = []
    achou_88 = False
    for nome in NOMES:
        for t0, _, alt, _ in peca.notas(nome):
            if t0 == tick56:
                if alt == 88:
                    achou_88 = True
                continue
            if alt > 76:
                fora.append((nome, peca.tempo_pos(t0), alt))
    if fora:
        return ("C2", "FAIL", f"{len(fora)} notas acima de 76 fora do tempo {EIXO}: {fora[:3]}")
    if not achou_88:
        return ("C2", "FAIL", f"o 88 não soa no tempo {EIXO}")
    return ("C2", "PASS", "nada acima de 76 fora do eixo, e o 88 soa no eixo")


def crit_c3(peca: Peca) -> Resultado:
    tick0, tick1 = peca.tick_de_tempo(EIXO), peca.tick_de_tempo(EIXO + 0.25)
    atacam = {nome for nome in NOMES if any(tick0 <= t0 < tick1 for t0, _, _, _ in peca.notas(nome))}
    faltando = set(NOMES) - atacam
    if faltando:
        return ("C3", "FAIL", f"não atacam em [{EIXO},{EIXO + 0.25}): {sorted(faltando)}")
    return ("C3", "PASS", "os 6 instrumentos atacam no eixo")


def crit_c4(peca: Peca) -> Resultado:
    tick0, tick1 = peca.tick_de_tempo(52), peca.tick_de_tempo(56)
    soam = peca.instrumentos_soando_em(tick0, tick1)
    extras = soam - {"Flauta", "Violoncelo"}
    if extras:
        return ("C4", "FAIL", f"soam além de Flauta/Violoncelo em [52,56): {sorted(extras)}")
    return ("C4", "PASS", "só Flauta e Violoncelo soam em [52,56)")


def crit_c5(peca: Peca) -> Resultado:
    contagens = []
    for c in range(13):
        tick0, tick1 = peca.tick_de_tempo(4 * c), peca.tick_de_tempo(4 * c + 4)
        contagens.append(len(peca.instrumentos_soando_em(tick0, tick1)))
    if any(b < a for a, b in zip(contagens, contagens[1:])):
        return ("C5", "FAIL", f"contagem cai entre compassos: {contagens}")
    if not contagens[-1] > contagens[0]:
        return ("C5", "FAIL", f"c13 ({contagens[-1]}) não é maior que c1 ({contagens[0]})")
    return ("C5", "PASS", f"contagem não cai, c1={contagens[0]} c13={contagens[-1]}")


def crit_c6(peca: Peca) -> Resultado:
    tick0 = peca.tick_de_tempo(108)
    classes_finais = {alt % 12 for nome in NOMES for t0, t1, alt, _ in peca.notas(nome) if t1 > tick0}
    esperadas = {2, 6, 9}  # Ré, Fá#, Lá
    if not esperadas <= classes_finais:
        return ("C6", "FAIL", f"último acorde não tem Ré+Fá#+Lá: classes={sorted(classes_finais)}")
    fa_natural_junto = any(nome for nome in NOMES for t0, t1, alt, _ in peca.notas(nome)
                           if alt % 12 == 5 and t0 < peca.tick_de_tempo(112) and t1 > tick0)
    if fa_natural_junto:
        return ("C6", "FAIL", "Fá natural soa junto com o Fá# nos 4 últimos tempos")
    ataque_re_maior = min((t0 for nome in NOMES for t0, _, alt, _ in peca.notas(nome)
                          if alt % 12 == 2 and t0 >= tick0), default=None)
    fim_fa_melodia = max((t1 for nome in MELODIA_NOMES for _, t1, alt, _ in peca.notas(nome)
                         if alt % 12 == 5), default=None)
    if ataque_re_maior is None or fim_fa_melodia is None:
        return ("C6", "UNKNOWN", "sem Ré no acorde final ou sem Fá na melodia para comparar")
    if fim_fa_melodia > ataque_re_maior:
        return ("C6", "FAIL", "o Fá da melodia não termina antes do ataque do Ré maior")
    return ("C6", "PASS", "acorde final com Ré/Fá#/Lá, sem Fá natural, Fá da melodia antes")


def crit_c7(peca: Peca, ref: Peca) -> Resultado:
    def graves_por_meio(p: Peca) -> list[int | None]:
        out = []
        for h in range(56):
            tick0, tick1 = p.tick_de_tempo(2 * h), p.tick_de_tempo(2 * h + 2)
            alturas = [alt for nome in ACOMPANHAMENTO_NOMES for t0, t1, alt, _ in p.notas(nome)
                      if t0 < tick1 and t1 > tick0]
            out.append(min(alturas) % 12 if alturas else None)
        return out
    a, b = graves_por_meio(peca), graves_por_meio(ref)
    divergencias = [h for h in range(len(a) - 2) if a[h] != b[h]]
    if divergencias:
        return ("C7", "FAIL", f"classe mais grave diverge da v8 nos meios {divergencias[:5]}")
    return ("C7", "PASS", "classe mais grave fora da melodia igual à v8 (menos nos 2 últimos)")


def crit_c8(peca: Peca) -> Resultado:
    for t0, t1, alt, _, nome in peca.ataques_melodia():
        acima = [(n2, a2) for n2 in ACOMPANHAMENTO_NOMES for t0b, t1b, a2, _ in peca.notas(n2)
                if t0b < t1 and t1b > t0 and a2 > alt]
        if acima:
            return ("C8", "FAIL", f"acompanhamento acima da melodia no tick {t0}: {acima[:2]}")
    return ("C8", "PASS", "nenhuma nota do acompanhamento soa acima da melodia num ataque dela")


def avaliar(midi_path: Path, etapa: str) -> list[Resultado]:
    if not midi_path.exists():
        return [("arquivo", "UNKNOWN", f"falta {midi_path}")]
    peca = Peca(midi_path)
    resultados: list[Resultado] = []

    if etapa == "expressiva":
        v8 = RAIZ / "build" / "v8.mid"
        if not v8.exists():
            resultados.append(("E0", "UNKNOWN", f"falta {v8}"))
        else:
            resultados.append(crit_e0(peca, Peca(v8)))

    e1, mediana = crit_e1(peca)
    resultados.append(e1)
    resultados.append(crit_e2(peca))
    resultados.append(crit_e3(peca))
    resultados.append(crit_e4(peca))
    resultados.append(crit_e5(peca))
    resultados.append(crit_e6(peca))
    resultados.append(crit_e7(peca, mediana))
    resultados.append(crit_e8(peca))

    if etapa == "v9":
        resultados.append(crit_c1(peca))
        sidecar = _sidecar(peca)
        if sidecar is None:
            for nome in ("C2", "C3", "C4", "C5", "C6", "C7", "C8"):
                resultados.append((nome, "UNKNOWN", "falta o sidecar -mapeamento.json"))
        else:
            resultados.append(crit_c2(peca))
            resultados.append(crit_c3(peca))
            resultados.append(crit_c4(peca))
            resultados.append(crit_c5(peca))
            resultados.append(crit_c6(peca))
            v8 = RAIZ / "build" / "v8.mid"
            if not v8.exists():
                resultados.append(("C7", "UNKNOWN", f"falta {v8}"))
            else:
                resultados.append(crit_c7(peca, Peca(v8)))
            resultados.append(crit_c8(peca))

    return resultados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("midi")
    ap.add_argument("--etapa", required=True, choices=("expressiva", "v9"))
    args = ap.parse_args()
    midi_path = Path(args.midi)
    resultados = avaliar(midi_path, args.etapa)
    for nome, status, detalhe in resultados:
        print(f"{status}  {nome}  {detalhe}")
    n = len(resultados)
    passaram = sum(1 for _, status, _ in resultados if status == "PASS")
    print(f"{passaram}/{n} critérios")
    if any(status == "FAIL" for _, status, _ in resultados):
        return 1
    if any(status == "UNKNOWN" for _, status, _ in resultados):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
