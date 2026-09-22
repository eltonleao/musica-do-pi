"""Expressão - o andamento, o CC11 e a pausa geral por cima de um MIDI pronto, sem mexer em nota.

Lê um MIDI da grade da v8 (112 tempos de 4/4, as 6 trilhas nomeadas, eixo no tempo 56) e escreve
outro com a mesma lista de ataques (trilha, tick, altura). O que muda:

- **Mapa de andamento.** Um `set_tempo` por colcheia, seguindo o rubato de Todd, "faster-louder":
  o bpm e o CC11 saem da mesma curva de nível, e por isso cada frase acelera e cresce até o ápice
  e relaxa na cadência, e a peça inteira arqueia até o eixo. A curva é normalizada para que a
  mediana dos `set_tempo` fora do eixo e dos 2 últimos compassos seja `mediana_bpm`.
- **O eixo e a pausa geral.** De `eixo` até o início da pausa o andamento alarga (`fator_eixo`).
  Toda nota que soa no início da pausa é cortada ali (só a duração, nunca o ataque), e o trecho
  da pausa ganha um `set_tempo` lento que dura `pausa[2]` segundos. A retomada é o sussurro:
  o nível cai a zero durante o silêncio.
- **CC11 nas 6 trilhas**, `piso + (teto - piso) x nível`, com o máximo no ataque do eixo.
- **Velocity.** Segue o nível de leve (`velocity_segue_nivel`), e todo ataque em
  [eixo, eixo + 0,25) ganha `acento_eixo`, para a maior velocity da melodia cair no eixo.
- **Final.** O `rampas` leva o rit. dos 2 últimos compassos, e as notas que soltavam no último
  `note_off` passam a soltar em `soltar` (o acorde final ocupa o compasso inteiro). Se ainda assim
  a peça acabar antes de `fim_s` segundos, o trecho depois do último ataque alarga até lá
  (fermata), para o áudio chegar aos 101 s do corte com o último ataque antes de 97 s.

O perfil (dict, `PERFIL_PADRAO` é o da v8 expressiva e o ponto de partida da v9):

    tempos               int, tamanho da grade em semínimas (112)
    eixo                 tempo do eixo (56); o oráculo usa 56 fixo, este campo só o acompanha
    mediana_bpm          mediana-alvo dos set_tempo fora de [eixo, eixo+2) e dos 2 últimos compassos
    passo_andamento      espaçamento dos set_tempo, em tempos (0,5 = um por colcheia)
    faixa_andamento      acoplamento faster-louder: bpm = mediana x (1 + faixa x (nível - 0,5))
    nivel                [(tempo, nível)], nível de 0 (sussurro) a 1 (eixo), interpolado em cosseno
    cc11                 (piso, teto) do CC11
    fator_eixo           bpm de [eixo, início da pausa) = fator x mediana_bpm; sem pausa
                         (`pausa` None), vale de `eixo` a `eixo + 2`
    pausa                (início, fim, segundos) da pausa geral; nenhum ataque pode cair dentro.
                         `None` desliga a pausa geral: nenhuma nota é cortada, nenhum
                         `set_tempo` de fermata entra, e `resumo()` devolve `pausa_s: 0`
    rampas               [(ini, fim, fator_ini, fator_fim)] que multiplicam o bpm (allargando, rit.)
    soltar               tempo em que o acorde final solta (112, o fim da grade)
    fim_s                segundo mínimo do último note_off
    velocity_segue_nivel velocity x (1 + k x (nível - 0,5))
    acento_eixo          somado à velocity de todo ataque em [eixo, eixo + 0,25)

Uso: python src/expressao.py build/v8.mid --saida build/v8-expressiva [--perfil p.json] [--sem-audio]
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import statistics
from pathlib import Path

import mido

PERFIL_PADRAO: dict = {
    "tempos": 112,
    "eixo": 56,
    "mediana_bpm": 70.0,
    "passo_andamento": 0.5,
    "faixa_andamento": 0.22,
    "nivel": [
        (0, .18), (4, .28), (8.5, .42), (12, .33), (16.5, .50), (20, .42), (26, .58),    # A
        (32, .50), (36, .36), (39, .34),                                              # cadência, transição
        (40, .38), (45, .56), (48, .52), (53, .80), (55, .92), (56, 1.0), (57.25, 1.0),  # B até o eixo
        (57.5, 0.0), (60, .12), (62.5, .26), (64, .26), (66.5, .40), (70, .42),       # o sussurro
        (72, .36), (76, .40), (80.5, .52), (84, .42), (88.5, .50), (92, .40), (97, .46),  # A'
        (100, .34), (104, .24), (108, .12), (112, .05),                               # rit.
    ],
    "cc11": (56, 127),
    "fator_eixo": 0.86,
    "pausa": (57.25, 57.5, 2.2),
    "rampas": [(54.5, 56, 1.0, 0.92), (102, 109.5, 1.0, 0.85)],
    "soltar": 112,
    "fim_s": 99.3,
    "velocity_segue_nivel": 0.15,
    "acento_eixo": 8,
}


def _nivel(perfil: dict, t: float) -> float:
    pontos = perfil["nivel"]
    if t <= pontos[0][0]:
        return pontos[0][1]
    for (t0, n0), (t1, n1) in zip(pontos, pontos[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            return n0 + (n1 - n0) * (1 - math.cos(math.pi * u)) / 2
    return pontos[-1][1]


def _rampa(perfil: dict, t: float) -> float:
    fator = 1.0
    for ini, fim, f0, f1 in perfil["rampas"]:
        if ini <= t < fim:
            u = (t - ini) / (fim - ini)
            fator *= f0 + (f1 - f0) * (1 - math.cos(math.pi * u)) / 2
        elif t >= fim and fim >= perfil["tempos"] - 8:
            fator *= f1          # o rit. final não volta
    return fator


def _notas(trilha: mido.MidiTrack) -> tuple[list[list], list[tuple[int, mido.Message]]]:
    """[tick_on, tick_off, altura, velocity, canal] e o resto da trilha, em ticks absolutos."""
    abertas: dict[tuple[int, int], list[list]] = {}
    notas, resto = [], []
    tick = 0
    for m in trilha:
        tick += m.time
        if m.type == "note_on" and m.velocity > 0:
            n = [tick, None, m.note, m.velocity, m.channel]
            abertas.setdefault((m.channel, m.note), []).append(n)
            notas.append(n)
        elif m.type == "note_off" or m.type == "note_on":
            fila = abertas.get((m.channel, m.note))
            if fila:
                fila.pop(0)[1] = tick
        elif m.type == "set_tempo" or (m.type == "control_change" and m.control == 11):
            continue
        elif m.type != "end_of_track":
            resto.append((tick, m))
    return [n for n in notas if n[1] is not None], resto


def _andamento(perfil: dict, tpb: int, ultimo_ataque: int, ultimo_off: int) -> list[tuple[int, int]]:
    """(tick, microssegundos por semínima) do mapa inteiro."""
    eixo = perfil["eixo"]
    tem_pausa = perfil["pausa"] is not None
    p_ini, p_fim, p_seg = perfil["pausa"] if tem_pausa else (eixo, eixo, 0.0)
    fim_eixo = p_ini if tem_pausa else eixo + 2   # fim do trecho em fator_eixo
    fim_grade = perfil["tempos"]
    passo = round(perfil["passo_andamento"] * tpb)
    ticks = {t for t in range(0, ultimo_off, passo) if not (p_ini * tpb < t < p_fim * tpb)}
    ticks |= {round(eixo * tpb), round(p_ini * tpb), round(p_fim * tpb), ultimo_ataque}
    ticks = sorted(ticks)

    def curva(t: float) -> float:
        return (1 + perfil["faixa_andamento"] * (_nivel(perfil, t) - 0.5)) * _rampa(perfil, t)

    def medido(t: float) -> bool:
        return not (eixo <= t < eixo + 2) and not (fim_grade - 8 <= t < fim_grade)

    escala = perfil["mediana_bpm"] / statistics.median(
        curva(t / tpb) for t in ticks if medido(t / tpb) and not (eixo <= t / tpb < p_fim))
    bpm = {}
    for t in ticks:
        pos = t / tpb
        if eixo <= pos < fim_eixo:
            bpm[t] = perfil["fator_eixo"] * perfil["mediana_bpm"]
        elif tem_pausa and p_ini <= pos < p_fim:
            bpm[t] = (p_fim - p_ini) * 60 / p_seg
        else:
            bpm[t] = escala * curva(pos)

    def duracao(de: int, ate: int) -> float:
        marcas = [t for t in ticks if de <= t < ate] + [ate]
        return sum((t1 - t0) / tpb * 60 / bpm[t0] for t0, t1 in zip(marcas, marcas[1:]))

    ate_ataque, depois = duracao(0, ultimo_ataque), duracao(ultimo_ataque, ultimo_off)
    if depois > 0 and ate_ataque + depois < perfil["fim_s"]:
        fator = depois / (perfil["fim_s"] - ate_ataque)
        for t in ticks:
            if t >= ultimo_ataque:
                bpm[t] *= fator
    return [(t, round(60e6 / bpm[t])) for t in ticks]


def aplicar(mid: mido.MidiFile, perfil: dict | None = None) -> mido.MidiFile:
    """O MIDI com o perfil aplicado. Não altera `mid`; ataques e alturas saem idênticos.

    Espera um MIDI tipo 1 com a trilha 0 de metadados e as trilhas de nota nomeadas, na grade de
    `perfil["tempos"]` semínimas e com o eixo em `perfil["eixo"]` (56 na v8 e na v9). Levanta
    ValueError se algum ataque cair dentro da pausa: a pausa, então, muda de lugar no perfil,
    dentro de [eixo, eixo + 2).
    """
    perfil = perfil or PERFIL_PADRAO
    tpb = mid.ticks_per_beat
    eixo = perfil["eixo"]
    tem_pausa = perfil["pausa"] is not None
    p_ini, p_fim = (round(perfil["pausa"][0] * tpb), round(perfil["pausa"][1] * tpb)) if tem_pausa else (None, None)
    piso, teto = perfil["cc11"]

    lidas = [(tr.name, *_notas(tr)) for tr in mid.tracks]
    todas = [n for _, notas, _ in lidas for n in notas]
    if not todas:
        raise ValueError("o MIDI não tem nota")
    if tem_pausa:
        dentro = sorted({n[0] / tpb for n in todas if p_ini <= n[0] < p_fim})
        if dentro:
            raise ValueError(f"ataques dentro da pausa, nos tempos {dentro}: mude a pausa no perfil")
    ultimo_ataque = max(n[0] for n in todas)
    if tem_pausa:
        for n in todas:
            if n[0] < p_ini < n[1]:
                n[1] = p_ini
    ultimo_off = max(n[1] for n in todas)
    soltar = round(perfil["soltar"] * tpb)
    if soltar > ultimo_off:
        for n in todas:
            if n[1] == ultimo_off:
                n[1] = soltar
        ultimo_off = soltar

    k = perfil["velocity_segue_nivel"]
    for n in todas:
        v = n[3] * (1 + k * (_nivel(perfil, n[0] / tpb) - 0.5))
        if eixo * tpb <= n[0] < (eixo + 0.25) * tpb:
            v += perfil["acento_eixo"]
        n[3] = max(1, min(127, round(v)))

    passo_cc = max(1, tpb // 48)
    cc11: list[tuple[int, int]] = []
    for t in range(0, ultimo_off + 1, passo_cc):
        valor = round(piso + (teto - piso) * _nivel(perfil, t / tpb))
        if not cc11 or cc11[-1][1] != valor:
            cc11.append((t, valor))

    saida = mido.MidiFile(type=mid.type, ticks_per_beat=tpb)
    for i, (nome, notas, resto) in enumerate(lidas):
        eventos: list[tuple[int, int, mido.Message]] = [(t, 0, m.copy()) for t, m in resto]
        if i == 0:
            eventos += [(t, 1, mido.MetaMessage("set_tempo", tempo=us))
                        for t, us in _andamento(perfil, tpb, ultimo_ataque, ultimo_off)]
        if notas:
            canal = notas[0][4]
            eventos += [(t, 2, mido.Message("control_change", channel=canal, control=11, value=v))
                        for t, v in cc11]
            for on, off, altura, vel, ch in notas:
                eventos.append((off, 1, mido.Message("note_off", channel=ch, note=altura, velocity=0)))
                eventos.append((on, 3, mido.Message("note_on", channel=ch, note=altura, velocity=vel)))
        eventos.sort(key=lambda e: (e[0], e[1]))
        trilha = mido.MidiTrack()
        cursor = 0
        for t, _, m in eventos:
            trilha.append(m.copy(time=t - cursor))
            cursor = t
        trilha.append(mido.MetaMessage("end_of_track", time=0))
        saida.tracks.append(trilha)
    return saida


def resumo(mid: mido.MidiFile, perfil: dict | None = None) -> dict:
    """Os números que o dono e o oráculo olham: mediana, pausa, último ataque e fim, em segundos."""
    perfil = perfil or PERFIL_PADRAO
    tpb = mid.ticks_per_beat
    tempos = sorted((t, m.tempo) for tr in mid.tracks for t, m in
                    zip(_ticks(tr), tr) if m.type == "set_tempo")

    def seg(tick: int) -> float:
        total = 0.0
        for (t0, us), (t1, _) in zip(tempos, tempos[1:] + [(math.inf, 0)]):
            total += (min(tick, t1) - t0) * us / tpb / 1e6
            if tick <= t1:
                break
        return total

    eixo, fim_grade = perfil["eixo"], perfil["tempos"]
    bpms = [60e6 / us for t, us in tempos
            if not (eixo <= t / tpb < eixo + 2) and not (fim_grade - 8 <= t / tpb < fim_grade)]
    ataques = [t for tr in mid.tracks for t, m in zip(_ticks(tr), tr)
               if m.type == "note_on" and m.velocity > 0]
    offs = [t for tr in mid.tracks for t, m in zip(_ticks(tr), tr)
            if m.type == "note_off" or (m.type == "note_on" and m.velocity == 0)]
    if perfil["pausa"] is not None:
        p_ini, p_fim = (round(p * tpb) for p in perfil["pausa"][:2])
        pausa_s = round(seg(p_fim) - seg(p_ini), 2)
    else:
        pausa_s = 0
    return {
        "set_tempo": len(tempos), "mediana_bpm": round(statistics.median(bpms), 2),
        "bpm_min": round(min(bpms), 1), "bpm_max": round(max(bpms), 1),
        "pausa_s": pausa_s, "eixo_s": round(seg(round(eixo * tpb)), 2),
        "ultimo_ataque_s": round(seg(max(ataques)), 2), "fim_s": round(seg(max(offs)), 2),
    }


def _ticks(trilha: mido.MidiTrack) -> list[int]:
    out, tick = [], 0
    for m in trilha:
        tick += m.time
        out.append(tick)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("midi")
    ap.add_argument("--saida", required=True, help="caminho sem extensão, ex.: build/v8-expressiva")
    ap.add_argument("--perfil", help="JSON com as chaves do PERFIL_PADRAO que mudam")
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()
    perfil = copy.deepcopy(PERFIL_PADRAO)
    if args.perfil:
        perfil.update(json.loads(Path(args.perfil).read_text(encoding="utf-8")))
    entrada, saida = Path(args.midi), Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    midi = saida.with_suffix(".mid")
    expressivo = aplicar(mido.MidiFile(str(entrada)), perfil)
    expressivo.save(str(midi))
    sidecar = entrada.with_name(entrada.stem + "-mapeamento.json")
    if sidecar.exists():
        shutil.copyfile(sidecar, f"{saida}-mapeamento.json")
    print(json.dumps(resumo(expressivo, perfil), ensure_ascii=False))
    if not args.sem_audio:
        from v8 import gravar_audio
        gravar_audio(midi)
        print(f"{midi.with_suffix('.mp3')} gravado")


if __name__ == "__main__":
    main()
