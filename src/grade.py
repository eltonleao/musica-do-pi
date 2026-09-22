"""Gravura da grade da v2: MusicXML legível e PDF de partitura.

Não compõe nada. Importa `v2.compor`, que é a fonte única da peça, e só traduz
o resultado para notação: claves, compassos, pausas, ligaduras, marcas de
ensaio, dinâmica e andamento. Se este arquivo e o `v2.py` discordarem, quem
está certo é o `v2.py` - ele é quem produz o MIDI que o oráculo mede.

O autor impresso é **Cosmos**. Foi ele quem escreveu as constantes: as alturas
do violino I são os dígitos de pi, na ordem, sem escolha humana no meio.

Cadeia de gravura, toda sem sudo e sem MuseScore:
  music21  monta o Score e escreve MusicXML
  verovio  diagrama o MusicXML em SVG, uma página por SVG
  Chrome   imprime o HTML com os SVGs em PDF, headless e explícito

Uso: python src/grade.py --digitos 132 --saida build/v2-grade
"""

from __future__ import annotations

import argparse
import importlib
import math
import html
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import v2 as V
from pi_digitos import digitos_de_pi

ABREV = {"Flauta": "Fl.", "Violino I": "Vn. I", "Violino II": "Vn. II",
         "Viola": "Vla.", "Violoncelo": "Vc.", "Piano": "Pno."}

# velocity -> marca de dinâmica. Os cortes vêm da curva DINAMICA do v2.py, que
# vai de 24 a 124: 30 tem que sair pp (a seção A é pp) e 106 tem que sair ff.
ESCALA = [(32, "pp"), (48, "p"), (64, "mp"), (80, "mf"), (100, "f")]

MAO_ESQUERDA = 60      # dó central: abaixo disso o piano vai para a clave de fá

TITULO = "Música do Pi"
SUBTITULO = "sexteto, versão 2"   # main() troca pelo da versão escolhida
# Quem assina é o cosmos, porque ninguém escolheu estas notas: π as ditou. A palavra
# é grega, κόσμος, e queria dizer "ordem", não "espaço sideral" - foi Pitágoras quem
# passou a usá-la para o universo, justamente por ver nele proporção numérica e
# harmonia. Para uma peça em que o número dita a melodia, é o crédito mais exato que
# existe, e mais preciso que o "Natura" que estava aqui antes: natureza é vago, cosmos
# é ordem.
AUTOR = "Cosmos"

# O que a página de rosto diz de cada versão. O mapeamento não entra aqui: sai
# do MAPEAMENTO do compositor, para o rosto não poder divergir do som.
ROSTO = {
    "v2": {
        "sub": "sexteto, versão 2",
        "nota": "As alturas do violino I são os {n} primeiros dígitos de π, na ordem, "
                "sem falta e sem escolha no meio. A constante é dela; o ritmo, a forma, "
                "a harmonia e a orquestração são regra aplicada sobre o que ela escreveu.",
        "forma": [("A", "expor", "violino I e violoncelo, pp"),
                  ("B", "adensar", "viola, violino II em tintinnabuli, flauta em pedal"),
                  ("C", "tensionar", "entra o piano; dominante secundária e cadência de engano"),
                  ("G.P.", "pausa geral", "um compasso de silêncio, sobre a dominante"),
                  ("D", "clímax", "tutti em três fases: chegada, auge, decaída"),
                  ("E", "dissolver", "tintinnabuli grave, ritardando, terça de Picardia")],
        "rodape": "compasso 4/4 · lá menor, com terça de Picardia no fim",
    },
    "v3": {
        "sub": "sexteto, versão 3 - o círculo",
        "nota": "As alturas do violino I são os {n} primeiros dígitos de π, na ordem, "
                "uma colcheia cada, até o eixo, e depois os mesmos de trás para frente. "
                "O 314º dígito é 3, como o primeiro: a linha sai de Dó e chega a Dó. "
                "Isso não foi escolhido, foi medido.",
        "forma": [("A", "a linha", "violino I lê π; a flauta canta a mesma linha quatro vezes mais lenta; pp"),
                  ("B", "a roda", "entra o violino II, 40 tempos atrás, com a mesma linha"),
                  ("C", "", "entra a viola, uma oitava abaixo"),
                  ("D", "o eixo", "entra o violoncelo, duas oitavas abaixo; ff no compasso 79"),
                  ("D' C' B' A'", "o espelho", "tudo de trás para frente: as vozes saem na ordem "
                   "inversa, e a peça acaba no som em que começou, pronta para o loop")],
        "rodape": "compasso 2/4 · ♩ = 97,11 · 3 min 14 s · a dinâmica é o cosseno de uma volta",
    },
    "v4": {
        "sub": "sexteto, versão 4 - o círculo, consonante",
        "nota": "As alturas do violino I são os {n} primeiros dígitos de π, na ordem, "
                "uma semínima cada, até o eixo, e depois os mesmos de trás para frente. "
                "Cada tempo tem um acorde que contém a nota de π, e a roda é o círculo "
                "das quintas: Lá m, Ré m, Sol, Dó, Fá, e Mi, Lá m.",
        "forma": [("A", "a linha", "violino I lê π sobre o arpejo do piano; p"),
                  ("B", "o chão", "entra o violoncelo na fundamental"),
                  ("C", "o coro", "entram violino II e viola, segurando notas do acorde"),
                  ("D", "o eixo", "a flauta dobra a melodia; o ápice no compasso 37"),
                  ("D' C' B' A'", "o espelho", "tudo de trás para frente: as vozes saem na ordem "
                   "inversa, e a peça acaba no som em que começou, pronta para o loop")],
        "rodape": "compasso 4/4 · ♩ = 89,07 · 3 min 14 s · a dinâmica é o cosseno de uma volta",
    },
    "v10": {
        "sub": "sexteto, versão 10 - menor que vira maior",
        "nota": "A melodia são os 31 primeiros dígitos de π, na ordem, e depois os mesmos "
                "31 de trás para frente: 62 notas ao todo, e a peça acaba no som em que "
                "começou. No tempo 56, o eixo do espelho, o modo troca - Ré menor vira "
                "Ré maior, e só duas alturas mudam, o 3 e o 6. A partir dali a música não "
                "para mais de crescer, até a nota mais aguda da peça, guardada para o fim.",
        "forma": [("A", "a linha", "violino I lê π em Ré menor; entram violoncelo, viola e violino II"),
                  ("eixo", "o espelho e a virada", "no tempo 56 a linha volta, e o modo vira Ré maior"),
                  ("A'", "adensar", "o piano fecha o arpejo em bloco, os pads dobram, a flauta dobra o violino I"),
                  ("clímax", "o fim mais alto", "as 6 vozes soam em todo compasso; Fá♯6, a nota mais aguda, no último acorde"),
                  ("", "a chegada", "cadência Sol - Lá7 - Ré, com Ré no baixo e rit. nos dois últimos compassos")],
        "rodape": "compasso 4/4 · 1 min 41 s · Ré menor até o eixo, Ré maior dali ao fim",
    },
}
NOMES = ["Dó", "Dó♯", "Ré", "Ré♯", "Mi", "Fá", "Fá♯", "Sol", "Sol♯", "Lá", "Lá♯", "Si"]


def marca_de(vel: int) -> str:
    for teto, nome in ESCALA:
        if vel <= teto:
            return nome
    return "ff"


GRADE_RITMICA = 0.5   # colcheia: todo ataque da v2 cai em múltiplo disto


def valor_escrito(eventos):
    """Troca a duração tocada pela duração escrita.

    O MIDI da v2 toca com articulação: a colcheia dura 0,45, a semínima 0,9,
    a mínima da flauta 1,75 a 1,9. Isso é o que o intérprete faz sozinho ao
    destacar a nota, e não o que se escreve - gravado como está, o music21
    inventa quiálteras de 5 e de 20 para caber 0,45 no compasso. A duração
    escrita arredonda para cima até a colcheia, sem passar do próximo ataque
    da mesma pauta; nota que já se sobrepunha a outra de propósito fica como
    estava, porque ali a sobreposição é polifonia, não articulação.
    """
    ataques = sorted({ini for ini, _, _, _ in eventos})
    saida = []
    for ini, dur, altura, vel in eventos:
        escrito = -(-dur // GRADE_RITMICA) * GRADE_RITMICA
        prox = next((a for a in ataques if a > ini), None)
        if prox is not None and ini + dur <= prox < ini + escrito:
            escrito = prox - ini
        saida.append((ini, escrito, altura, vel))
    return saida


def agrupar(eventos):
    """Junta em acorde os eventos que começam juntos e duram o mesmo.

    O piano toca oitavas na mão esquerda: dois eventos com o mesmo início e a
    mesma duração. Sem isto, music21 abre uma voz nova para cada um e a grade
    fica com duas vozes onde a mão tem uma.
    """
    caixas: dict[tuple[float, float], list[tuple[int, int]]] = {}
    for ini, dur, altura, vel in eventos:
        caixas.setdefault((ini, dur), []).append((altura, vel))
    return sorted((ini, dur, sorted(a for a, _ in notas), max(v for _, v in notas))
                  for (ini, dur), notas in caixas.items())


def pontos_de_dinamica():
    """Os tempos em que a marca de dinâmica muda, com a marca nova."""
    saida, anterior = [], None
    for t, vel in getattr(V, "DINAMICA", []):
        m = marca_de(int(vel))
        if m != anterior:
            saida.append((float(t), m))
            anterior = m
    return saida


def montar_parte(nome, eventos, clave_obj, instrumento, m21):
    clef, dynamics, instrument, key, meter, note, chord, stream = m21
    p = stream.Part(id=nome.replace(" ", "-"))
    p.partName = nome
    p.partAbbreviation = ABREV.get(nome, nome[:3])
    p.insert(0, instrumento)
    p.insert(0, clave_obj)
    p.insert(0, meter.TimeSignature(f"{V.COMPASSO}/4"))
    p.insert(0, key.KeySignature(0))          # lá menor: sem acidente na armadura

    for ini, dur, alturas, vel in agrupar(valor_escrito(eventos)):
        n = chord.Chord(alturas) if len(alturas) > 1 else note.Note(alturas[0])
        n.quarterLength = dur
        n.volume.velocity = vel
        p.insert(ini, n)

    # A dinâmica entra no primeiro ataque desta voz depois da virada da curva,
    # nunca no tempo cru: marca pendurada sobre pausa não diz nada ao músico.
    ataques = sorted({ini for ini, _, _, _ in eventos})
    virada = pontos_de_dinamica()
    for i, (t, m) in enumerate(virada):
        fim = virada[i + 1][0] if i + 1 < len(virada) else float("inf")
        alvo = next((a for a in ataques if t <= a < fim), None)
        if alvo is not None:
            p.insert(alvo, dynamics.Dynamic(m))
    return p


def montar(partes, acordes, marcas, duracao, digitos: str):
    from music21 import (chord, clef, dynamics, expressions, harmony, instrument,
                         key, layout, metadata, meter, note, stream, tempo)

    m21 = (clef, dynamics, instrument, key, meter, note, chord, stream)
    inst = {"Flauta": instrument.Flute(), "Violino I": instrument.Violin(),
            "Violino II": instrument.Violin(), "Viola": instrument.Viola(),
            "Violoncelo": instrument.Violoncello()}
    claves = {"Flauta": clef.TrebleClef(), "Violino I": clef.TrebleClef(),
              "Violino II": clef.TrebleClef(), "Viola": clef.AltoClef(),
              "Violoncelo": clef.BassClef()}

    partitura = stream.Score()
    partitura.metadata = metadata.Metadata()
    partitura.metadata.title = TITULO
    partitura.metadata.movementName = SUBTITULO
    partitura.metadata.composer = AUTOR

    criadas = []
    for nome in ordem_da_versao():
        if nome == "Piano":
            continue
        p = montar_parte(nome, partes[nome], claves[nome], inst[nome], m21)
        partitura.insert(0, p)
        criadas.append(p)

    # Piano em dois pentagramas, partido no dó central.
    direita = [e for e in partes["Piano"] if e[2] >= MAO_ESQUERDA]
    esquerda = [e for e in partes["Piano"] if e[2] < MAO_ESQUERDA]
    ps_d = montar_parte("Piano", direita, clef.TrebleClef(), instrument.Piano(), m21)
    ps_e = montar_parte("Piano", esquerda, clef.BassClef(), instrument.Piano(), m21)
    ps_d.__class__ = stream.PartStaff
    ps_e.__class__ = stream.PartStaff
    ps_e.partName = ""
    ps_e.partAbbreviation = ""
    partitura.insert(0, ps_d)
    partitura.insert(0, ps_e)
    partitura.insert(0, layout.StaffGroup([ps_d, ps_e], name="Piano",
                                          abbreviation="Pno.", symbol="brace"))

    topo = criadas[0]          # a flauta leva ensaio, andamento e cifra

    for letra, ini, _fim in marcas:
        r = expressions.RehearsalMark(letra)
        topo.insert(float(ini), r)

    # A pausa geral: o vão entre o fim de C e o começo de D. Versão sem marca de
    # ensaio C ou D - a v10 não tem pausa geral - simplesmente não desenha nada.
    fim_c = next((f for l, _, f in marcas if l == "C"), None)
    ini_d = next((i for l, i, _ in marcas if l == "D"), None)
    if fim_c is not None and ini_d is not None and ini_d > fim_c:
        gp = expressions.TextExpression("G.P.")
        gp.style.fontStyle = "bold"
        gp.placement = "above"
        topo.insert(float(fim_c), gp)

    anterior = None
    for t, bpm in getattr(V, "ANDAMENTO", []):
        mm = tempo.MetronomeMark(number=round(bpm), referent=note.Note(type="quarter"))
        topo.insert(float(t), mm)
        if anterior is not None and bpm < anterior:
            txt = expressions.TextExpression("poco rit.")
            txt.placement = "above"
            topo.insert(float(t), txt)
        anterior = bpm

    # Cifra acima da flauta: é a harmonia que a versão decidiu, e é o que permite
    # conferir a cadência de engano e a dominante secundária a olho.
    #
    # O passo entre cifras se deriva da peça, não se assume igual ao compasso. A v10
    # tem 56 acordes para 112 tempos - meio compasso cada - e com o passo fixo em
    # COMPASSO as cifras se espalhavam por 224 tempos, o dobro da peça: o
    # `makeNotation` então preenchia 28 compassos de pauta vazia depois do fim da
    # música, só com cifra correndo por cima. Versão que declara `PASSO_CIFRA` manda;
    # as outras dividem a duração real pelo número de acordes.
    passo = getattr(V, "PASSO_CIFRA", None)
    if passo is None:
        passo = duracao / len(acordes) if acordes else V.COMPASSO

    ant = None
    for i, nome in enumerate(acordes):
        if nome == ant:
            continue
        cs = harmony.ChordSymbol(cifra_music21(nome))
        cs.writeAsChord = False
        topo.insert(float(i * passo), cs)
        ant = nome

    partitura.makeNotation(inPlace=True)
    numerar_vozes(partitura)
    limpar_acidentes(partitura)
    return partitura


def numerar_vozes(partitura):
    """Faz a numeração das vozes começar em 1, e não em 0.

    O `makeVoices` do music21 dá id 0 à primeira voz do compasso, e voz 0 não
    existe em MusicXML: o verovio responde "Layer 0 cannot be found" uma vez
    por compasso e joga a camada fora. Renumerar de 1 em diante, na ordem em
    que as vozes estão no compasso, preserva quem é quem.
    """
    for compasso in partitura.recurse().getElementsByClass("Measure"):
        vozes = list(compasso.getElementsByClass("Voice"))
        for i, v in enumerate(vozes):
            v.id = str(i + 1)


def limpar_acidentes(partitura):
    """Deixa só o acidente que o músico precisa ler.

    O `makeAccidentals` do music21 roda com `cautionaryPitchClass` ligado: um
    Dó#5 no violino I faz nascer bequadro em todo Dó de qualquer oitava até o
    fim do compasso. Com seis vozes e Dó# na escala, isso deu 290 bequadros
    contra 15 sustenidos, e a grade ficou ilegível. A regra aqui é a da
    notação comum: o acidente vale para a altura exata, naquele compasso, e o
    bequadro só aparece para cancelar uma alteração que veio antes.
    """
    from music21 import pitch

    for parte in partitura.recurse().getElementsByClass("Part"):
        for compasso in parte.getElementsByClass("Measure"):
            alterado: dict[tuple[str, int], float] = {}
            notas = sorted(compasso.recurse().notes,
                           key=lambda n: n.getOffsetInHierarchy(compasso))
            for n in notas:
                # Continuação de ligadura de valor não repete acidente.
                amarrada = n.tie is not None and n.tie.type in ("stop", "continue")
                for p in n.pitches:
                    if amarrada:
                        if p.accidental is not None:
                            p.accidental.displayStatus = False
                        alterado[(p.step, p.octave)] = p.alter
                        continue
                    chave = (p.step, p.octave)
                    alter = p.alter
                    antes = alterado.get(chave, 0.0)
                    if alter == 0.0:
                        if antes != 0.0:
                            p.accidental = pitch.Accidental("natural")
                            p.accidental.displayStatus = True
                        else:
                            p.accidental = None
                    elif p.accidental is not None:
                        p.accidental.displayStatus = alter != antes
                    alterado[chave] = alter


def gravar_svgs(caminho_xml: Path, escala: int) -> list[str]:
    import verovio

    tk = verovio.toolkit()
    tk.setOptions({
        # A página do verovio é virtual: o CSS estica cada SVG até o A4, e o
        # `scale` do verovio é só zoom de saída, não muda a paginação (medido:
        # 26, 32 e 40 deram as mesmas 8 páginas). Quem encolhe a pauta no papel
        # é uma página virtual maior na mesma proporção do A4.
        "pageWidth": round(2100 * 100 / escala), "pageHeight": round(2970 * 100 / escala),
        "pageMarginTop": 80, "pageMarginBottom": 80,
        "pageMarginLeft": 80, "pageMarginRight": 80,
        "scale": 100,
        "adjustPageHeight": False,
        "breaks": "auto",
        "header": "auto", "footer": "none",
        "svgViewBox": True,
        "spacingStaff": 10, "spacingSystem": 8,
        "mmOutput": False,
    })
    if not tk.loadFile(str(caminho_xml)):
        raise SystemExit(f"verovio não abriu {caminho_xml}")
    if not tk.loadData(cabecalho_com_autor(tk.getMEI())):
        raise SystemExit("verovio recusou o MEI com o cabeçalho reescrito")
    return [tk.renderToSVG(i + 1) for i in range(tk.getPageCount())]


TITLE_STMT = re.compile(r"<titleStmt[^>]*>.*?</titleStmt>", re.S)


def cabecalho_com_autor(mei: str) -> str:
    """Reescreve o `titleStmt` do MEI para o autor sair impresso na partitura.

    Medido em 20/09/2026, verovio 6.3.0: o cabeçalho automático só desenha o
    compositor quando o elemento é `<composer>` filho direto de `<titleStmt>`.
    O music21 escreve `<creator type="composer">` no MusicXML, que o verovio
    importa como `<respStmt><persName role="composer">` - válido em MEI, e
    invisível no papel. Das quatro formas testadas, só esta imprime o nome.
    """
    novo = ("<titleStmt>"
            f"<title>{TITULO}</title>"
            f'<title type="subordinate">{SUBTITULO}</title>'
            f"<composer>{AUTOR}</composer>"
            "</titleStmt>")
    saida, n = TITLE_STMT.subn(novo, mei, count=1)
    if n != 1:
        raise SystemExit("titleStmt não encontrado no MEI")
    return saida


def ordem_da_versao():
    """A formação, na ordem da grade. A v10 herda a da v8, que herda a da v2."""
    ordem = getattr(V, "ORDEM", None)
    if ordem:
        return ordem
    from v2 import ORDEM
    return ORDEM


def mapeamentos_da_versao():
    """Os mapeamentos da versão, sempre como lista de (rótulo, mapa).

    A v2 e a v9 têm um `MAPEAMENTO` só e valem para a peça inteira. A v10 troca de
    modo no eixo e declara `MAPEAMENTOS` como [[início, fim, mapa]] em tempos: ali a
    legenda tem de sair em duas colunas, senão esconde o fato musical mais
    interessante da peça, que é o Ré menor virando Ré maior no meio.
    """
    faixas = getattr(V, "MAPEAMENTOS", None)
    if not faixas:
        return [("", V.MAPEAMENTO)]
    if len(faixas) == 1:
        return [("", faixas[0][2])]
    rotulos = ["primeira metade", "segunda metade"]
    return [(rotulos[i] if i < len(rotulos) else f"de {ini:g} a {fim:g}", mapa)
            for i, (ini, fim, mapa) in enumerate(faixas)]


# As cores do tema suzukipetropolis, em hex porque é o que o CSS de impressão e o
# verovio aceitam. A sexta cor de pauta - o azul-petróleo - não vem do tema: é
# derivação declarada no plano P12, o complemento do laranja da marca.
CORES = {
    "laranja": "#f97a1f", "laranja_forte": "#bd5205",
    "roxo": "#623ba5", "rosa": "#e23670", "rosa_forte": "#bb1b50",
    "verde": "#157f3c", "azul": "#1f6f8b",
    "creme": "#fcfaf8", "tinta": "#261c17", "cinza": "#766860", "filete": "#e5e2dc",
}

# A cor de cada linha da grade, na ordem em que as pautas aparecem no papel.
COR_DO_INSTRUMENTO = [
    ("Flauta", CORES["laranja"]),
    ("Violino I", CORES["rosa"]),
    ("Violino II", CORES["roxo"]),
    ("Viola", CORES["verde"]),
    ("Violoncelo", CORES["azul"]),
    ("Piano", CORES["laranja_forte"]),
]


# As mesmas doze alturas escritas com bemol. Qual das duas tabelas vale é questão de
# armadura, não de gosto: em Ré menor a sexta é Si♭ e chamá-la de Lá♯ contradiz a
# partitura que a criança tem na frente, onde está escrito um bemol. Em Ré maior o
# Fá♯ e o Dó♯ são os da armadura, e aí manda a tabela de sustenido.
NOMES_BEMOL = ["Dó", "Ré♭", "Ré", "Mi♭", "Mi", "Fá", "Sol♭", "Sol", "Lá♭", "Lá", "Si♭", "Si"]


def nome_de_nota(altura, grave_de_referencia: int, bemol: bool = False) -> str:
    """O nome da nota como a criança lê, sem número de oitava.

    Oitava em número é ruído para quem ainda está aprendendo a ler: o que importa
    na legenda é qual nota é, e se ela está no registro agudo. `bemol` escolhe a
    grafia enarmônica, e quem chama sabe a armadura do trecho.
    """
    if altura is None:
        return "pausa"
    tabela = NOMES_BEMOL if bemol else NOMES
    return tabela[altura % 12] + ("<span class='ag'> agudo</span>"
                                  if altura - 12 >= grave_de_referencia else "")


def arte_do_circulo(tamanho: int = 150) -> str:
    """O círculo com o diâmetro marcado: a figura que define π.

    SVG desenhado aqui dentro, sem asset e sem rede, para o PDF sair igual daqui a
    um ano offline. A volta inteira vai no laranja da marca e o diâmetro no rosa,
    que são as duas medidas cuja razão é π.
    """
    r = tamanho / 2 - 10
    c = tamanho / 2
    return f"""<svg class="arte" viewBox="0 0 {tamanho} {tamanho}" width="{tamanho}" height="{tamanho}"
     role="img" aria-label="Um círculo com a volta e o diâmetro marcados">
  <circle cx="{c}" cy="{c}" r="{r}" fill="none"
          stroke="{CORES['laranja']}" stroke-width="3.5"/>
  <line x1="{c - r}" y1="{c}" x2="{c + r}" y2="{c}"
        stroke="{CORES['rosa']}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{c}" cy="{c}" r="2.6" fill="{CORES['rosa']}"/>
</svg>"""


def capa(digitos: str) -> str:
    """A capa: título, subtítulo da versão, autoria e a figura que explica π.

    A capa não ensina nada - ela só promete. Quem ensina é a página seguinte.
    """
    texto = ROSTO[V.__name__]
    return f"""
<div class="pagina capa">
  <div class="capa-topo">
    <p class="capa-eyebrow">Suzuki Petrópolis</p>
    <h1 class="capa-titulo">{TITULO}</h1>
    <p class="capa-sub">{html.escape(texto["sub"])}</p>
  </div>
  <div class="capa-arte">
    {arte_do_circulo(170)}
    <p class="capa-razao">a volta dividida pelo diâmetro dá sempre
      <b class="capa-pi">π = 3,14159...</b></p>
    <p class="capa-legenda">e esse número, dígito por dígito, virou esta música</p>
  </div>
  <div class="capa-pe">
    <p class="capa-autor">{AUTOR}</p>
    <p class="capa-fino">as {len(digitos)} primeiras casas de π, na ordem, e depois
      de trás para frente</p>
  </div>
</div>
"""


def pagina_didatica(digitos: str, duracao: float) -> str:
    """A página que explica a peça para o aluno com o professor ao lado.

    Uma página só, e nesta ordem: o que é π, como o número virou melodia, por que a
    música vira maior no meio, e como ler as cores. Frase curta, e nenhum termo
    técnico sem a explicação na mesma frase - quem lê tem sete anos.
    """
    faixas = mapeamentos_da_versao()
    menor = min(a for _, m in faixas for a in m.values() if a is not None)
    duas = len(faixas) > 1
    mapa_a = faixas[0][1]
    mapa_b = faixas[-1][1] if duas else faixas[0][1]
    muda = {d for d in "1234567890" if mapa_a[d] != mapa_b[d]} if duas else set()
    eixo = float(getattr(V, "EIXO", duracao / 2))

    linhas = "".join(
        f"<tr class=\"{'muda' if d in muda else ''}\">"
        f"<td class='dig'>{d}</td>"
        f"<td>{nome_de_nota(mapa_a[d], menor, bemol=True)}</td>"
        + (f"<td>{nome_de_nota(mapa_b[d], menor)}</td>" if duas else "")
        + "</tr>"
        for d in "1234567890")
    cabecalho = ("<tr><th>dígito</th><th>até o meio</th><th>do meio ao fim</th></tr>"
                 if duas else "<tr><th>dígito</th><th>nota</th></tr>")

    cores = "".join(
        f"<li><span class='amostra' style='background:{cor}'></span>"
        f"{html.escape(nome)}</li>" for nome, cor in COR_DO_INSTRUMENTO)

    return f"""
<div class="pagina didatica">
  <h1 class="did-titulo">Como esta música foi feita</h1>

  <section class="bloco">
    <h2>1. O que é π</h2>
    <div class="lado-a-lado">
      {arte_do_circulo(112)}
      <div>
        <p>Pegue qualquer círculo. Meça a volta dele por fora. Meça a largura do
        círculo passando pelo meio, que se chama <b>diâmetro</b>.</p>
        <p>O diâmetro cabe um pouco mais de três vezes dentro da volta. Esse
        "pouco mais de três" é o <b>π</b> (lê-se "pi"), e dá o mesmo em todo
        círculo do mundo, grande ou pequeno.</p>
        <p class="destaque">π = 3,141592653589793...</p>
        <p>Os pontinhos no fim não são preguiça: os números continuam para sempre
        e nunca repetem um padrão. Ninguém jamais escreveu π inteiro.</p>
      </div>
    </div>
  </section>

  <section class="bloco">
    <h2>2. Como o número virou melodia</h2>
    <p>Cada dígito de π ganhou uma nota. O violino I toca os dígitos na ordem, um
    depois do outro: 3, 1, 4, 1, 5, 9... Ninguém escolheu essas notas - elas já
    estavam no número.</p>
    <table class="mapa">{cabecalho}{linhas}</table>
    <p class="fino">O dígito 0 também tem nota. As duas linhas coloridas são os
    dois dígitos que mudam no meio da peça - veja o item 3.</p>
  </section>

  <section class="bloco">
    <h2>3. Por que a música fica maior no meio</h2>
    <p>A peça toca {len(digitos)} dígitos de π e depois toca os mesmos
    {len(digitos)} de trás para frente, como um espelho. Por isso ela termina no
    mesmo som em que começou.</p>
    <p>O espelho fica no <b>tempo {eixo:.0f}</b>, bem no meio. Ali acontece a
    virada: a música estava em <b>Ré menor</b>, que soa mais triste, e passa para
    <b>Ré maior</b>, que soa mais alegre. Só duas notas precisam mudar para isso -
    as duas coloridas na tabela acima. Daí até o fim a música só cresce.</p>
    <div class="espelho">
      <span class="metade menor">Ré menor · dígitos na ordem</span>
      <span class="eixo-marca">espelho</span>
      <span class="metade maior">Ré maior · dígitos ao contrário</span>
    </div>
  </section>

  <section class="bloco">
    <h2>4. Como ler as cores</h2>
    <p>Cada instrumento tem a sua cor nas cinco linhas onde as notas são escritas.
    Ache a sua cor e siga só ela.</p>
    <ul class="cores">{cores}</ul>
    <p>Dois sinais aparecem embaixo das notas e dizem o volume:</p>
    <ul class="sinais">
      <li>{forquilha_svg(True)}<span><b>crescendo</b> - vá tocando mais forte</span></li>
      <li>{forquilha_svg(False)}<span><b>diminuendo</b> - vá tocando mais fraco</span></li>
    </ul>
  </section>
</div>
"""


def forquilha_svg(crescendo: bool) -> str:
    """O sinal de crescendo ou diminuendo, desenhado como o músico o vê na pauta."""
    cor = CORES["laranja"] if crescendo else CORES["rosa"]
    d = "M2,9 L34,2 M2,9 L34,16" if crescendo else "M34,9 L2,2 M34,9 L2,16"
    return (f"<svg class='sinal' viewBox='0 0 36 18' width='36' height='18' "
            f"aria-hidden='true'><path d='{d}' fill='none' stroke='{cor}' "
            f"stroke-width='2' stroke-linecap='round'/></svg>")


def pagina_de_rosto(digitos: str, acordes, duracao: float, partes) -> str:
    zeros = digitos.count("0")
    texto = ROSTO[V.__name__]
    faixas = mapeamentos_da_versao()
    menor = min(a for _, m in faixas for a in m.values() if a is not None)

    # A primeira faixa é a do modo menor e se escreve com bemol; da troca em diante
    # vale o sustenido da armadura nova. Grafia errada aqui contradiz o acidente
    # impresso na pauta três páginas adiante.
    def nome(a, bemol=False):
        if a is None:
            return "pausa"
        tabela = NOMES_BEMOL if bemol else NOMES
        return tabela[a % 12] + (" agudo" if a - 12 >= menor else "")

    def coluna(mapa, bemol=False):
        return " · ".join(f"{d} = {nome(mapa[d], bemol)}" for d in "1234567890")

    if len(faixas) == 1:
        mapa = coluna(faixas[0][1], bemol=True)
    else:
        # Os dígitos cuja altura muda entre as faixas vão em destaque: são eles que
        # contam a troca de modo, e sem marca ninguém acha as duas diferenças em dez.
        muda = {d for d in "1234567890"
                if len({m[d] for _, m in faixas}) > 1}

        def coluna_marcada(mapa, bemol):
            return " · ".join(
                (f"<b>{d} = {nome(mapa[d], bemol)}</b>" if d in muda
                 else f"{d} = {nome(mapa[d], bemol)}")
                for d in "1234567890")
        mapa = "<br>".join(f"<i>{html.escape(rot)}:</i> {coluna_marcada(m, i == 0)}"
                           for i, (rot, m) in enumerate(faixas))

    # A frase sobre o zero depende do que a versão faz com ele, e não se escreve fixa:
    # na PoC o 0 era pausa e o mapeamento dos agudos estava mesmo em aberto, mas a v10
    # dá altura aos dez dígitos e o mapeamento dela está fechado e provado pelo
    # oráculo. Repetir a ressalva antiga seria dizer ao músico que a peça é rascunho.
    zero_e_pausa = any(m["0"] is None for _, m in faixas)
    if zero_e_pausa:
        rodape_do_zero = f"O dígito 0 é pausa, e aparece {zeros} vezes."
    elif zeros:
        rodape_do_zero = ("Os dez dígitos têm altura própria: não há pausa na linha, e o "
                          f"0 soa {zeros} vezes como nota.")
    else:
        # Dizer "o 0 soa 0 vezes" é verdade e não informa nada. Nas 31 primeiras casas
        # de π não há zero nenhum, e o que o leitor precisa saber é que a tabela cobre
        # os dez dígitos mesmo assim.
        rodape_do_zero = ("Os dez dígitos têm altura própria e não há pausa na linha. "
                          "O 0 está na tabela, mas não chega a aparecer nestas casas de π.")
    linhas = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{len(partes[n])}</td></tr>" for n in ordem_da_versao())
    forma = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>"
                    for a, b, c in texto["forma"])
    return f"""
<div class="pagina rosto">
  <div class="topo">
    <h1>Música do Pi</h1>
    <p class="sub">{html.escape(texto["sub"])}</p>
    <p class="autor">{AUTOR}</p>
    <p class="nota">{html.escape(texto["nota"].format(n=len(digitos)))}</p>
  </div>
  <div class="meio">
    <h2>Formação</h2>
    <p>Flauta · Violino I · Violino II · Viola · Violoncelo · Piano</p>
    <h2>Mapeamento dos dígitos</h2>
    <p class="mono">{mapa}</p>
    <p class="fino">{rodape_do_zero}</p>
    <h2>Forma</h2>
    <table class="forma">{forma}</table>
    <h2>Notas por voz</h2>
    <table class="forma"><tr><th>voz</th><th>notas</th></tr>{linhas}</table>
  </div>
  <p class="rodape">{math.ceil(duracao / V.COMPASSO)} compassos · {duracao:.0f} tempos ·
  {html.escape(texto["rodape"])}</p>
</div>
"""


# CSS só da capa e da página didática. Fica num bloco à parte, com classes
# próprias, para não disputar linha com o CSS de pauta e de impressão da grade.
CSS_DIDATICO = f"""
  .capa, .didatica {{ background: {CORES['creme']}; color: {CORES['tinta']}; }}
  /* A regra global `.pagina svg` estica o SVG do verovio para a página inteira, que
     é o certo para a pauta e destrói a arte inline. Aqui o desenho tem tamanho
     próprio, e por isso a regra precisa ser desfeita nestas duas páginas. */
  .capa svg, .didatica svg {{ width: auto; height: auto; display: inline-block; }}
  .capa {{ padding: 30mm 24mm 24mm; display: flex; flex-direction: column;
           justify-content: space-between; text-align: center; }}
  .capa-eyebrow {{ font-size: 10pt; letter-spacing: 1.6mm; text-transform: uppercase;
                   color: {CORES['cinza']}; margin: 0 0 6mm; }}
  .capa-titulo {{ font-size: 46pt; margin: 0; font-weight: normal;
                  color: {CORES['laranja_forte']}; letter-spacing: 0.6mm; }}
  .capa-sub {{ font-size: 14pt; font-style: italic; color: {CORES['cinza']};
               margin: 4mm 0 0; }}
  .capa-arte {{ display: flex; flex-direction: column; align-items: center; }}
  .capa-arte .arte {{ margin-bottom: 7mm; }}
  .capa-razao {{ font-size: 13pt; margin: 0; color: {CORES['tinta']}; }}
  .capa-pi {{ color: {CORES['rosa_forte']}; white-space: nowrap; }}
  .capa-legenda {{ font-size: 11.5pt; color: {CORES['cinza']}; margin: 3mm 0 0;
                   font-style: italic; }}
  .capa-pe {{ border-top: 0.4mm solid {CORES['filete']}; padding-top: 6mm; }}
  .capa-autor {{ font-size: 19pt; letter-spacing: 1.4mm; margin: 0; }}
  .capa-fino {{ font-size: 9.5pt; color: {CORES['cinza']}; margin: 3mm 0 0; }}

  .didatica {{ padding: 12mm 16mm; font-size: 10pt; line-height: 1.42; }}
  .did-titulo {{ font-size: 19pt; font-weight: normal; margin: 0 0 4mm;
                 color: {CORES['laranja_forte']};
                 border-bottom: 0.6mm solid {CORES['laranja']}; padding-bottom: 2mm; }}
  .didatica .bloco {{ margin-bottom: 4.2mm; }}
  .didatica h2 {{ font-size: 11.5pt; font-weight: normal; margin: 0 0 1.8mm;
                  color: {CORES['roxo']}; }}
  .didatica p {{ margin: 0 0 1.8mm; }}
  .didatica .fino {{ font-size: 9pt; color: {CORES['cinza']}; }}
  .lado-a-lado {{ display: flex; gap: 7mm; align-items: flex-start; }}
  .lado-a-lado .arte {{ flex: none; }}
  .destaque {{ font-family: "DejaVu Sans Mono", monospace; font-size: 11.5pt;
               color: {CORES['rosa_forte']}; }}
  table.mapa {{ border-collapse: collapse; font-size: 10pt; width: 100%;
                margin: 2mm 0 2mm; }}
  table.mapa th {{ font-size: 8.5pt; text-transform: uppercase; font-weight: normal;
                   letter-spacing: 0.3mm; color: {CORES['cinza']};
                   text-align: left; padding: 0 4mm 1.4mm 2mm;
                   border-bottom: 0.3mm solid {CORES['filete']}; }}
  table.mapa td {{ padding: 0.55mm 4mm 0.55mm 2mm;
                   border-bottom: 0.2mm solid {CORES['filete']}; }}
  table.mapa td.dig {{ font-family: "DejaVu Sans Mono", monospace; font-size: 11pt;
                       color: {CORES['laranja_forte']}; width: 14mm; }}
  table.mapa tr.muda td {{ background: #fdeee2; color: {CORES['rosa_forte']};
                           font-weight: bold; }}
  table.mapa tr.muda td.dig {{ color: {CORES['rosa_forte']}; }}
  table.mapa .ag {{ color: {CORES['cinza']}; font-size: 8.5pt; }}
  .espelho {{ display: flex; align-items: stretch; margin-top: 3mm;
              font-size: 9.5pt; }}
  .espelho .metade {{ flex: 1; padding: 2.4mm 3mm; color: #fff; }}
  .espelho .menor {{ background: {CORES['roxo']}; text-align: left;
                     border-radius: 1.2mm 0 0 1.2mm; }}
  .espelho .maior {{ background: {CORES['laranja']}; text-align: right;
                     color: {CORES['tinta']}; border-radius: 0 1.2mm 1.2mm 0; }}
  .espelho .eixo-marca {{ background: {CORES['tinta']}; color: {CORES['creme']};
                          padding: 2.4mm 3mm; font-style: italic; }}
  /* As seis cores descem na ordem das pautas, e não em linha: quem procura a
     própria cor está procurando a própria linha na grade. */
  ul.cores {{ list-style: none; padding: 0; margin: 2mm 0; font-size: 10pt;
              columns: 2; column-gap: 10mm; }}
  ul.cores li {{ display: flex; align-items: center; gap: 2mm;
                 break-inside: avoid; margin-bottom: 1.2mm; }}
  .amostra {{ display: inline-block; width: 12mm; height: 3.6mm;
              border-radius: 0.8mm; flex: none; }}
  ul.sinais {{ list-style: none; padding: 0; margin: 1.5mm 0 0; font-size: 10pt; }}
  ul.sinais li {{ display: flex; align-items: center; gap: 3mm;
                  margin-bottom: 1.4mm; }}
  .sinal {{ flex: none; }}
"""


# A cor de cada linha da grade, na ordem em que os pentagramas saem do verovio.
# A ordem é a de `montar()`: a formação sem o piano, e depois os dois pentagramas
# do piano - mão direita e mão esquerda -, que levam a mesma cor porque são um
# instrumento só. Cinco cores vêm do tema suzukipetropolis; o azul do violoncelo
# é derivação declarada no plano, porque o tema tem cinco e os naipes são seis.
COR_DA_PAUTA = ["laranja", "rosa", "roxo", "verde", "azul", "laranja_forte",
                "laranja_forte"]

# Separa cada `<g ... class="staff">` do SVG, guardando a marca de abertura: o
# verovio emite os pentagramas como filhos diretos do compasso, na ordem da grade.
ABRE_PAUTA = re.compile(r'(<g id="[^"]+" class="staff">)')
ABRE_COMPASSO = re.compile(r'(<g id="[^"]+" class="measure">)')
# As cinco linhas do pentagrama são os `<path>` que o verovio escreve antes de
# qualquer `<g>` dentro da pauta. Tudo o que vem depois - clave, nota, haste,
# ligadura - é filho de um `<g>` com classe própria e fica fora deste recorte.
#
# A cor vai em `style=`, e não no atributo `stroke=`: o verovio embute no SVG uma
# folha de estilo com `#<id> path {stroke:currentColor}`, e regra de folha vence
# atributo de apresentação. Medido em 22/09/2026 - com `stroke=` as pautas saíram
# pretas no PDF mesmo estando coloridas no HTML. `style=` é declaração inline e
# ganha da folha.
LINHA_DA_PAUTA = re.compile(
    r'<path d="M[\d.]+ [\d.]+ L[\d.]+ [\d.]+" stroke-width="\d+"( style="stroke:#[0-9a-f]{6}")? />')


def colorir_pautas(svg: str) -> str:
    """Pinta as cinco linhas de cada pentagrama na cor do seu instrumento.

    Só a pauta muda de cor. Cabeça de nota, haste, clave, ligadura e barra de
    compasso continuam em `#261c17`: a cor identifica a linha à distância, que é
    o que o aluno precisa para achar a sua parte na grade, e colorir a nota
    destruiria a legibilidade justamente do que ele tem de ler.

    O compasso é a âncora, e não o SVG inteiro: um sistema de grade completa tem
    sete pautas na ordem da formação, e as duas últimas são as mãos do piano. O
    fim da peça tem compassos de uma pauta só - a parte de cifra, que corre além
    dos 112 tempos - e esses ficam em tinta, porque ali não há naipe a
    identificar e uma cor solta mentiria sobre quem toca.
    """
    def no_compasso(corpo: str) -> str:
        pedacos = ABRE_PAUTA.split(corpo)
        pautas = (len(pedacos) - 1) // 2
        if pautas != len(COR_DA_PAUTA):
            return corpo
        saida = [pedacos[0]]
        for i in range(1, len(pedacos), 2):
            cor = CORES[COR_DA_PAUTA[(i - 1) // 2]]
            saida.append(pedacos[i])
            saida.append(LINHA_DA_PAUTA.sub(
                lambda m: m.group(0) if m.group(1)
                else m.group(0)[:-3] + f' style="stroke:{cor}" />', pedacos[i + 1], count=5))
        return "".join(saida)

    pedacos = ABRE_COMPASSO.split(svg)
    for i in range(2, len(pedacos), 2):
        pedacos[i] = no_compasso(pedacos[i])
    return "".join(pedacos)


# O limiar da forquilha, em fração da intensidade máxima da peça. Escolhido em
# 0,12 depois de varrer 0,08 a 0,15 no perfil da v10: abaixo disso aparecem saltos
# de um compasso só, que no papel viram risquinho ilegível, e acima disso some a
# retomada do A'. Com 0,12 e a exigência de dois compassos de largura saem seis
# forquilhas, e a maior delas - compassos 20 a 26, tempos 76 a 100 - cai dentro do
# trecho [76, 104) em que o M6 do oráculo mediu rho = 0,86 de crescendo. A marcação
# concorda com a medição em vez de decorar por cima dela.
LIMIAR_FORQUILHA = 0.12
LARGURA_FORQUILHA = 2        # compassos: menos que isto não se lê impresso
# Meia boca da forquilha, na escala interna do verovio, em que o espaço entre
# duas linhas de pauta vale 180. Uma boca de 540 é um espaço e meio para cada
# lado: a mesma proporção do sinal impresso, e o que dá ângulo visível no papel.
ABERTURA_FORQUILHA = 270.0


def nivel_por_compasso(duracao: float) -> list[float]:
    """A intensidade declarada da versão, amostrada no início de cada compasso.

    É o perfil que toda chamada de `vel()` da v10 lê, e por isso é o `velocity`
    da peça antes dos reforços por voz. Medir a média dos eventos daria o número
    errado: quando um pad grave entra em pp a média cai, mas o que se ouve é a
    música ficando mais cheia. A intenção de dinâmica está no perfil; o que os
    eventos acrescentam é orquestração.
    """
    nivel = V.PERFIL["nivel"] if hasattr(V, "PERFIL") else []
    if not nivel:
        return []

    def em(t: float) -> float:
        for (t0, v0), (t1, v1) in zip(nivel, nivel[1:]):
            if t0 <= t <= t1:
                return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0.0)
        return nivel[0][1] if t < nivel[0][0] else nivel[-1][1]

    compassos = int(duracao // V.COMPASSO) + 1
    return [em(c * V.COMPASSO) for c in range(compassos)]


def forquilhas(duracao: float) -> list[tuple[int, int, int]]:
    """Os trechos de crescendo e diminuendo como (compasso inicial, final, sinal).

    Compassos contados de 1, como o músico conta. Cada trecho é uma corrida
    monótona do perfil: o sinal só muda quando a curva vira, e a corrida só vira
    forquilha se andou `LIMIAR_FORQUILHA` de intensidade em pelo menos
    `LARGURA_FORQUILHA` compassos.
    """
    perfil = nivel_por_compasso(duracao)
    saida, i = [], 0
    while i < len(perfil) - 1:
        sinal = (perfil[i + 1] > perfil[i]) - (perfil[i + 1] < perfil[i])
        if sinal == 0:
            i += 1
            continue
        j = i + 1
        while j < len(perfil) - 1 and (perfil[j + 1] - perfil[j]) * sinal > 0:
            j += 1
        if abs(perfil[j] - perfil[i]) >= LIMIAR_FORQUILHA and j - i >= LARGURA_FORQUILHA:
            saida.append((i + 1, j + 1, sinal))
        i = j
    return saida


def desenhar_forquilhas(svgs: list[str], duracao: float) -> list[str]:
    """Desenha a forquilha de cada trecho sob a pauta da flauta, na cor do sentido.

    Crescendo em laranja, diminuendo em rosa: são as duas cores que o pedido dá a
    estes dois sinais, e a página didática mostra as duas ao lado do nome. A
    forquilha fica sob o primeiro pentagrama do sistema, que é o da flauta, porque
    a dinâmica da v10 é da peça inteira e não de um naipe - repeti-la em seis
    linhas encheria a página sem dizer nada a mais.

    Um trecho que atravessa a quebra de sistema ou de página é desenhado em cada
    pedaço, aberto onde continua: é como se escreve forquilha longa no papel.
    """
    trechos = forquilhas(duracao)
    if not trechos:
        return svgs

    saida = []
    numero = 0          # o compasso corrente, em ordem de documento
    for svg in svgs:
        pedacos = ABRE_COMPASSO.split(svg)
        # Cada compasso vira (número, faixa em x, topo da pauta da flauta).
        caixas: dict[int, tuple[float, float, float]] = {}
        for i in range(2, len(pedacos), 2):
            numero += 1
            corpo = pedacos[i]
            pautas = ABRE_PAUTA.split(corpo)
            if (len(pautas) - 1) // 2 != len(COR_DA_PAUTA):
                continue          # compasso de cifra solta: não tem grade a marcar
            linhas = [m.group(0) for m in LINHA_DA_PAUTA.finditer(pautas[2])][:5]
            if len(linhas) < 5:
                continue
            pontos = [tuple(float(v) for v in re.findall(r"[\d.]+", re.search(r'd="([^"]+)"', l).group(1)))
                      for l in linhas]
            x0 = min(p[0] for p in pontos)
            x1 = max(p[2] for p in pontos)
            caixas[numero] = (x0, x1, max(p[1] for p in pontos))
        saida.append(svg if not caixas else inserir_forquilhas(svg, caixas, trechos))
    return saida


def inserir_forquilhas(svg: str, caixas: dict, trechos: list) -> str:
    """Acrescenta ao SVG da página os desenhos das forquilhas que caem nela."""
    desenhos = []
    for ini, fim, sinal in trechos:
        presentes = [c for c in range(ini, fim + 1) if c in caixas]
        if len(presentes) < 2:
            continue
        x0 = caixas[presentes[0]][0]
        x1 = caixas[presentes[-1]][1]
        # A forquilha não ocupa o trecho inteiro. Medido em 22/09/2026: um trecho
        # de quatro compassos dá 13 mil unidades de comprimento para 540 de boca,
        # proporção de 25 para 1, e no papel isso não é uma forquilha, é um risco.
        # O sinal desenhado à mão fica perto de 8 para 1, e é esse o teto aqui: a
        # forquilha começa onde o trecho começa e para quando atinge a proporção,
        # porque o que ela precisa dizer é onde a dinâmica vira, não até onde vai.
        x1 = min(x1, x0 + 8 * 2 * ABERTURA_FORQUILHA)
        # Sob a pauta da flauta, que é a primeira do sistema, e é onde a dinâmica
        # se escreve em partitura. Acima dela ficam a marca de ensaio e a cifra,
        # e a forquilha ali batia nas duas.
        y = max(caixas[c][2] for c in presentes) + 400
        cor = CORES["laranja"] if sinal > 0 else CORES["rosa"]
        # A boca da forquilha abre para onde a música vai: no crescendo ela abre
        # no fim, no diminuendo abre no começo.
        abertura = ABERTURA_FORQUILHA
        if sinal > 0:
            a, b = (x0, 0.0), (x1, abertura)
        else:
            a, b = (x0, abertura), (x1, 0.0)
        desenhos.append(
            f'<g class="forquilha">'
            f'<path d="M{a[0]:.0f} {y - a[1]:.0f} L{b[0]:.0f} {y - b[1]:.0f}" '
            f'style="stroke:{cor};fill:none" stroke-width="16" stroke-linecap="round" />'
            f'<path d="M{a[0]:.0f} {y + a[1]:.0f} L{b[0]:.0f} {y + b[1]:.0f}" '
            f'style="stroke:{cor};fill:none" stroke-width="16" stroke-linecap="round" /></g>')
    if not desenhos:
        return svg
    # Dentro do `g.page-margin`, que é onde vivem as coordenadas do compasso: o
    # verovio aninha um segundo `<svg class="definition-scale">` com viewBox
    # próprio, dez vezes maior que o de fora. Acrescentar no fim do SVG externo
    # punha a forquilha noutra escala, e ela saía atravessando a página inteira.
    marca = re.search(r'<g class="page-margin"[^>]*>', svg)
    if not marca:
        return svg
    corte = marca.end()
    return svg[:corte] + "".join(desenhos) + svg[corte:]


# O CSS de impressão com a paleta: o papel deixa de ser branco e o texto deixa de
# ser preto puro. O fundo creme e a tinta `#261c17` são os mesmos do tema, e é o
# par que dá o contraste de leitura sem o estalo do preto sobre branco.
CSS_PALETA = f"""
  body {{ background: {CORES['creme']}; color: {CORES['tinta']}; }}
  .pagina {{ background: {CORES['creme']}; }}
  .rosto .sub, .rosto h2, .rosto .fino, .rosto .rodape,
  table.forma th {{ color: {CORES['cinza']}; }}
  .rosto .nota {{ color: {CORES['tinta']}; }}
  .rosto .rodape {{ border-top-color: {CORES['filete']}; }}
  .faixa-titulo {{ background: {CORES['laranja']}; color: {CORES['tinta']};
                   padding: 4mm 6mm; margin: 0 0 6mm; }}
"""


def montar_html(svgs: list[str], rosto: str) -> str:
    corpo = "".join(f'<div class="pagina">{s}</div>' for s in svgs)
    return f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><title>Música do Pi - grade</title>
<style>
  @page {{ size: A4; margin: 0; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{ font-family: Georgia, "Times New Roman", serif; color: #111; }}
  .pagina {{ width: 210mm; height: 297mm; page-break-after: always;
             overflow: hidden; box-sizing: border-box; }}
  .pagina:last-child {{ page-break-after: auto; }}
  .pagina svg {{ width: 100%; height: 100%; display: block; }}
  .rosto {{ padding: 28mm 24mm; display: flex; flex-direction: column;
            justify-content: space-between; }}
  .rosto h1 {{ font-size: 34pt; margin: 0 0 2mm; font-weight: normal;
               letter-spacing: 0.5mm; }}
  .rosto .sub {{ font-size: 13pt; margin: 0 0 14mm; color: #555;
                 font-style: italic; }}
  .rosto .autor {{ font-size: 20pt; margin: 0 0 8mm; letter-spacing: 1.2mm; }}
  .rosto .nota {{ font-size: 10.5pt; line-height: 1.55; max-width: 130mm;
                  color: #333; }}
  .rosto h2 {{ font-size: 10pt; text-transform: uppercase; letter-spacing: 0.8mm;
               color: #666; margin: 9mm 0 2mm; font-weight: normal; }}
  .rosto p {{ margin: 0; font-size: 11pt; }}
  .rosto .mono {{ font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; }}
  .rosto .fino {{ font-size: 9.5pt; color: #666; margin-top: 2mm; }}
  table.forma {{ border-collapse: collapse; font-size: 10pt; margin-top: 1mm; }}
  table.forma td, table.forma th {{ padding: 0.8mm 6mm 0.8mm 0; text-align: left;
                                    vertical-align: top; font-weight: normal; }}
  table.forma th {{ color: #666; font-size: 9pt; text-transform: uppercase; }}
  .rosto .rodape {{ font-size: 9.5pt; color: #666; border-top: 0.3mm solid #ccc;
                    padding-top: 3mm; }}
{CSS_DIDATICO}
{CSS_PALETA}
</style></head><body>{rosto}{corpo}</body></html>
"""


def imprimir_pdf(html_path: Path, pdf_path: Path) -> None:
    """Chrome headless, explícito, como manda a regra do vault."""
    cmd = ["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--virtual-time-budget=20000",
           f"--print-to-pdf={pdf_path}", html_path.as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise SystemExit(f"Chrome não produziu PDF.\n{r.stderr[-2000:]}")


def cifra_music21(nome: str) -> str:
    """A cifra da peça no dialeto do music21.

    As versões escrevem bemol como `b`, que é o que se lê em cifra de banda: `Bb`.
    O music21 usa a notação dele, em que bemol é `-` e `b` sozinho seria um tipo de
    acorde - por isso `Bb` estoura com "Invalid chord abbreviation 'b'". Só a letra
    da fundamental se traduz; o resto do sufixo fica como está.
    """
    if len(nome) >= 2 and nome[0].isalpha() and nome[1] == "b":
        return nome[0] + "-" + nome[2:]
    return nome


def compor_adaptado(digitos: str):
    """Chama V.compor e devolve sempre (partes, acordes, marcas, duracao).

    Cada versão devolve o que o seu próprio oráculo precisa: a v2 devolve os quatro
    que a gravura quer, e a v10 devolve sete - partes, acordes, graves, k, a, b, lida -
    porque é isso que o `avaliar_v10.py` mede. Adaptar aqui é o que permite gravar a
    v10 sem tocar em `v10.py`, que está coberto pelo congelamento do P11: mudar o
    retorno de lá invalidaria a prova da peça para desenhá-la no papel.

    `marcas` e `duracao` não existem na v10 e saem derivados: as marcas de ensaio vêm
    do ROSTO, que já descreve a forma, e a duração vem do último evento composto.
    """
    r = V.compor(digitos)
    if len(r) == 4:
        return r

    partes, acordes = r[0], r[1]
    duracao = max((ini + dur) for ev in partes.values() for ini, dur, _, _ in ev)
    marcas = marcas_da_versao(duracao)
    return partes, acordes, marcas, duracao


def marcas_da_versao(duracao: float):
    """As marcas de ensaio como (letra, início, fim), em tempos.

    Versão que não devolve marcas próprias ganha as do ROSTO, ancoradas no eixo: a
    peça é um espelho, e o que o músico precisa achar na página é onde a linha volta.
    Letra vazia no ROSTO não vira marca - é linha de forma, não ponto de ensaio.
    """
    letras = [a for a, _, _ in ROSTO[V.__name__]["forma"] if a]
    eixo = float(getattr(V, "EIXO", duracao / 2))
    climax = float(getattr(V, "CLIMAX", eixo + (duracao - eixo) * 0.7))
    pontos = {"A": 0.0, "eixo": eixo, "A'": eixo + 20.0, "clímax": climax}
    saida = []
    for letra in letras:
        if letra in pontos:
            saida.append((letra, pontos[letra], pontos[letra]))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--versao", default="v2", choices=sorted(ROSTO))
    ap.add_argument("--digitos", type=int, default=132)
    ap.add_argument("--saida", default="build/v2-grade")
    ap.add_argument("--escala", type=int, default=80,
                    help="tamanho da pauta no papel, em %% do padrão do verovio")
    args = ap.parse_args()

    global V, SUBTITULO
    V = importlib.import_module(args.versao)
    SUBTITULO = ROSTO[args.versao]["sub"]
    digitos = digitos_de_pi(args.digitos)
    partes, acordes, marcas, duracao = compor_adaptado(digitos)
    partitura = montar(partes, acordes, marcas, duracao, digitos)

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    xml = saida.with_suffix(".musicxml")
    partitura.write("musicxml", fp=str(xml))

    svgs = gravar_svgs(xml, args.escala)
    # A cor entra depois da gravura, no SVG pronto: o verovio decide onde cada
    # pentagrama cai, e este passo só repinta o que ele já desenhou.
    svgs = [colorir_pautas(s) for s in svgs]
    svgs = desenhar_forquilhas(svgs, duracao)
    # A ordem que a criança lê: a capa promete, a didática explica, o rosto é a
    # ficha técnica da grade para quem rege, e só então vem a música.
    abertura = (capa(digitos) + pagina_didatica(digitos, duracao)
                + pagina_de_rosto(digitos, acordes, duracao, partes))
    pagina = montar_html(svgs, abertura)
    htm = saida.with_suffix(".html").resolve()
    htm.write_text(pagina, encoding="utf-8")
    pdf = saida.with_suffix(".pdf").resolve()
    imprimir_pdf(htm, pdf)

    print(f"{xml}  {xml.stat().st_size // 1024} KB")
    print(f"{pdf}  {len(svgs) + 3} páginas (capa + didática + rosto + "
          f"{len(svgs)} de música), {pdf.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
