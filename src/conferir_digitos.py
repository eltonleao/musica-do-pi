"""Oráculo de ida e volta: lê o MIDI, recupera os dígitos pelo mapeamento inverso
do sidecar e compara com os dígitos de pi.

Sai 0 quando batem; 1 quando não; 2 quando não dá para medir (UNKNOWN).

Uso: python src/conferir_digitos.py build/pi-poc.mid
     python src/conferir_digitos.py build/v8.mid

O sidecar é sempre `<nome>-mapeamento.json`, ao lado do MIDI. Dois formatos:

1. **PoC** (`cfg["digitos"]` é um inteiro): uma só trilha "Violino I", um dígito
   por tempo inteiro de 0 a `digitos - 1`, na ordem em que aparecem. Mantido
   por compatibilidade com `build/pi-poc.mid`.

2. **v8 em diante** (`cfg["digitos"]` é um dicionário de trechos, com pelo
   menos as chaves `"A"` e `"B"`, cada uma uma string de dígitos): a melodia
   é lida das trilhas "Violino I" e "Flauta" juntas, em ordem de tick,
   ataques em qualquer tick (não só em tempo inteiro). A sequência esperada
   não vem do sidecar: é recalculada com `pi_digitos.digitos_de_pi`, para o
   dígitos de pi. Ela é montada com os dois primeiros trechos, na
   ordem em que aparecem os dígitos de pi - o comprimento de "A" e de "B" no
   sidecar diz só *quantos* dígitos cada trecho tem, nunca o valor deles -,
   seguida do reverso da mesma sequência: `esperado = (A+B) + reverso(A+B)`.

   Chaves opcionais do sidecar, lidas só neste formato:

   - `"oitava"`: dicionário `{"<tempo>": <semitons>}`. No tempo inteiro dado
     (chave string), subtrai `<semitons>` da altura de QUALQUER ataque
     acontecendo naquele tempo, nas duas trilhas, antes de inverter o
     mapeamento. Ex.: `{"56": 12}` tira uma oitava do ataque do tempo 56.
   - `"mapeamentos"`: lista de `[inicio, fim, {digito: altura}]` (tempos, fim
     exclusivo, cobrindo [0, tempos)). Cada trecho tem o inverso próprio, e o
     dígito de um ataque é lido no inverso do trecho que contém o tempo dele.
     Sem essa chave vale o `"mapeamento"` de hoje, único, para o arquivo
     inteiro - os formatos antigos continuam lendo igual.
   - `"dona"`: lista de `[inicio, fim, "<trilha>"]` (tempos, fim exclusivo).
     Decide, quando duas trilhas atacam no mesmo tick com a mesma classe de
     altura (dobra), qual delas é a "dona" do trecho - o dígito é lido só
     nela. Sem essa chave, ou fora de todo intervalo declarado, vale o
     default da decisão 5 do plano P10: Flauta nos tempos `[40, 72)`,
     Violino I no resto.

   Regra da dobra: dois ataques no mesmo tick com a mesma classe de altura
   (`altura % 12` igual, depois da oitava) contam como um dígito só, lido na
   trilha dona. Dois ataques no mesmo tick com classes DIFERENTES tornam a
   leitura inconsistente e a conferência sai 1 direto (sem comparar com pi).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import mido

from pi_digitos import digitos_de_pi

TICKS_POR_SEMINIMA = 480
TRILHAS_MELODIA = ("Violino I", "Flauta")


class DivergenciaDeClasse(Exception):
    """Duas trilhas atacam no mesmo tick com classes de altura diferentes."""


def _eventos_de_trilha(arq: mido.MidiFile, nome: str) -> list[tuple[int, int]]:
    """Lista de (tick, altura) dos note_on com velocity > 0 da trilha com esse track_name."""
    trilha = next((t for t in arq.tracks if any(m.type == "track_name" and m.name == nome for m in t)), None)
    if trilha is None:
        return []
    tick = 0
    out = []
    for m in trilha:
        tick += m.time
        if m.type == "note_on" and m.velocity > 0:
            out.append((tick, m.note))
    return out


def digitos_do_midi_poc(caminho: Path, mapeamento: dict[str, int | None], quantos: int) -> str:
    """Formato PoC: uma trilha, um dígito por tempo inteiro."""
    arq = mido.MidiFile(str(caminho))
    if arq.ticks_per_beat != TICKS_POR_SEMINIMA:
        raise RuntimeError(f"ticks_per_beat {arq.ticks_per_beat}, esperado {TICKS_POR_SEMINIMA}")
    eventos = _eventos_de_trilha(arq, "Violino I")
    if not eventos:
        raise RuntimeError("trilha 'Violino I' não encontrada")
    inverso = {altura: d for d, altura in mapeamento.items() if altura is not None}
    pausa = next((d for d, altura in mapeamento.items() if altura is None), None)
    inicio_por_tempo: dict[int, int] = {}
    for tick, altura in eventos:
        if tick % TICKS_POR_SEMINIMA:
            raise RuntimeError(f"nota fora do tempo no tick {tick}")
        tempo = tick // TICKS_POR_SEMINIMA
        if tempo in inicio_por_tempo:
            raise RuntimeError(f"duas notas no tempo {tempo}")
        inicio_por_tempo[tempo] = altura
    saida = []
    for tempo in range(quantos):
        if tempo in inicio_por_tempo:
            altura = inicio_por_tempo[tempo]
            if altura not in inverso:
                raise RuntimeError(f"altura {altura} no tempo {tempo} não está no mapeamento")
            saida.append(inverso[altura])
        elif pausa is not None:
            saida.append(pausa)
        else:
            raise RuntimeError(f"tempo {tempo} sem nota e o mapeamento não tem pausa")
    return "".join(saida)


def _trilha_dona(tempo: float, dona: list) -> str:
    for ini, fim, nome in dona:
        if ini <= tempo < fim:
            return nome
    return "Flauta" if 40 <= tempo < 72 else "Violino I"


def _inversos_por_trecho(cfg: dict) -> list[tuple[float, float, dict[int, str]]]:
    """[(inicio, fim, inverso)] em tempos, fim exclusivo, cobrindo [0, tempos).

    Com `"mapeamentos"` no sidecar, um inverso por trecho declarado. Sem esse campo,
    um único trecho [0, tempos) com o `"mapeamento"` de sempre.
    """
    if "mapeamentos" in cfg:
        trechos = []
        for ini, fim, mapa in cfg["mapeamentos"]:
            mapeamento = {d: (int(a) if a is not None else None) for d, a in mapa.items()}
            inverso = {altura: d for d, altura in mapeamento.items() if altura is not None}
            trechos.append((float(ini), float(fim), inverso))
        return trechos
    mapeamento = {d: (int(a) if a is not None else None) for d, a in cfg["mapeamento"].items()}
    inverso = {altura: d for d, altura in mapeamento.items() if altura is not None}
    return [(0.0, float(cfg.get("tempos", math.inf)), inverso)]


def _inverso_do_tempo(tempo: float, trechos: list[tuple[float, float, dict[int, str]]]) -> dict[int, str]:
    for ini, fim, inverso in trechos:
        if ini <= tempo < fim:
            return inverso
    raise RuntimeError(f"tempo {tempo} não coberto por nenhum trecho de 'mapeamentos'")


def digitos_do_midi_v8(caminho: Path, cfg: dict) -> str:
    """Formato v8 em diante: Violino I + Flauta, ataque em qualquer tick, oitava e dobra."""
    arq = mido.MidiFile(str(caminho))
    tpb = arq.ticks_per_beat
    eventos = []
    for nome in TRILHAS_MELODIA:
        eventos += [(tick, altura, nome) for tick, altura in _eventos_de_trilha(arq, nome)]
    if not eventos:
        raise RuntimeError("nenhuma das trilhas 'Violino I'/'Flauta' encontrada ou sem notas")
    eventos.sort(key=lambda ev: ev[0])

    trechos_mapeamento = _inversos_por_trecho(cfg)
    usa_mapeamentos = "mapeamentos" in cfg
    oitava = {int(k): int(v) for k, v in cfg.get("oitava", {}).items()}
    dona = cfg.get("dona", [])

    def ajustar(tick: int, altura: int) -> tuple[int, float]:
        tempo = tick / tpb
        tempo_int = round(tempo)
        if abs(tempo - tempo_int) < 1e-6 and tempo_int in oitava:
            altura -= oitava[tempo_int]
        return altura, tempo

    digitos = []
    i, n = 0, len(eventos)
    while i < n:
        tick = eventos[i][0]
        grupo = []
        j = i
        while j < n and eventos[j][0] == tick:
            _, altura, trilha = eventos[j]
            alt_ajustada, tempo = ajustar(tick, altura)
            grupo.append((alt_ajustada, trilha, tempo))
            j += 1
        if len(grupo) == 1:
            alt_final = grupo[0][0]
        else:
            classes = {a % 12 for a, _, _ in grupo}
            if len(classes) > 1:
                raise DivergenciaDeClasse(f"classes de altura diferentes no tick {tick}")
            tempo = grupo[0][2]
            dona_trilha = _trilha_dona(tempo, dona)
            candidatos = [a for a, tr, _ in grupo if tr == dona_trilha]
            alt_final = candidatos[0] if candidatos else grupo[0][0]
        tempo = grupo[0][2]
        inverso = _inverso_do_tempo(tempo, trechos_mapeamento)
        if alt_final not in inverso:
            if usa_mapeamentos:
                # Mapeamento por trecho: uma altura fora do vocabulário do trecho é o
                # sinal de que o modo errado está soando (ex.: Fá natural depois do
                # eixo, quando o mapeamento maior não usa mais o 65). Isso é uma
                # divergência mensurável contra pi, não falta de dado: o dígito lido
                # vira um marcador que nunca bate com nenhum dígito de pi, e a
                # comparação final relata FAIL.
                digitos.append("?")
                i = j
                continue
            raise RuntimeError(f"altura {alt_final} no tick {tick} não está no mapeamento")
        digitos.append(inverso[alt_final])
        i = j
    return "".join(digitos)


def esperados_v8(cfg: dict) -> str:
    """A + B, tirados de pi_digitos (não do sidecar), seguidos do reverso de A + B."""
    trechos = cfg["digitos"]
    tam_a, tam_b = len(trechos["A"]), len(trechos["B"])
    pi_bruto = digitos_de_pi(tam_a + tam_b)
    a_esperado, b_esperado = pi_bruto[:tam_a], pi_bruto[tam_a:]
    metade = a_esperado + b_esperado
    return metade + metade[::-1]


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: conferir_digitos.py <arquivo.mid>")
        return 2
    midi = Path(sys.argv[1])
    sidecar = midi.with_name(midi.stem + "-mapeamento.json")
    if not midi.exists() or not sidecar.exists():
        print(f"UNKNOWN: falta {midi if not midi.exists() else sidecar}")
        return 2
    cfg = json.loads(sidecar.read_text(encoding="utf-8"))
    if "mapeamento" not in cfg or "digitos" not in cfg:
        print(f"UNKNOWN: sidecar {sidecar} sem 'mapeamento' ou 'digitos'")
        return 2

    digitos_cfg = cfg["digitos"]
    try:
        if isinstance(digitos_cfg, int):
            mapeamento = {d: (int(a) if a is not None else None) for d, a in cfg["mapeamento"].items()}
            lidos = digitos_do_midi_poc(midi, mapeamento, digitos_cfg)
            esperados = digitos_de_pi(digitos_cfg)
        elif isinstance(digitos_cfg, dict) and "A" in digitos_cfg and "B" in digitos_cfg:
            lidos = digitos_do_midi_v8(midi, cfg)
            esperados = esperados_v8(cfg)
        else:
            print(f"UNKNOWN: formato de 'digitos' desconhecido em {sidecar}")
            return 2
    except DivergenciaDeClasse as e:
        print(f"FAIL: {e}")
        return 1
    except RuntimeError as e:
        print(f"UNKNOWN: {e}")
        return 2

    if lidos == esperados:
        print(f"PASS: {len(esperados)} dígitos recuperados do MIDI batem com pi ({lidos[:12]}...)")
        return 0
    tamanho = min(len(lidos), len(esperados))
    primeiro = next((i for i in range(tamanho) if lidos[i] != esperados[i]), tamanho)
    print(f"FAIL: divergência no dígito {primeiro + 1}: lido "
          f"{lidos[primeiro] if primeiro < len(lidos) else '<faltando>'}, "
          f"pi {esperados[primeiro] if primeiro < len(esperados) else '<faltando>'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
