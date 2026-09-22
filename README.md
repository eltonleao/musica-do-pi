# Música do Pi

A melodia é o número π. Um dígito por tempo, cada dígito uma altura fixa, e nada na linha é escolha de gosto: ela é o que o número dita. Em volta dela, a harmonia, as vozes internas, o baixo e o piano são derivados por regra a partir da própria linha.

A versão atual é a **v10, "menor que vira maior"**: sexteto, 1 min 41 s. Os 31 primeiros dígitos de π na ordem, depois os mesmos 31 de trás para frente - 62 notas ao todo, e a peça termina no som em que começou. No tempo 56, o eixo do espelho, o modo troca: Ré menor vira Ré maior, e só duas alturas mudam, o 3 e o 6. Dali até o fim a música não para de crescer, até Fá♯6, a nota mais aguda da peça, guardada para o último acorde.

## Para escutar e para ler

| Arquivo | O que é |
|---|---|
| `build/v10.mp3` | a v10 como ela sai do renderizador |
| `build/escuta/v10-23lufs.mp3` | a mesma, nivelada a -23 LUFS, que é o volume de comparação |
| `build/v10-grade.pdf` | a grade completa, colorida, com capa e página didática |
| `build/v10-grade.musicxml` | a mesma grade para abrir no MuseScore, Sibelius ou Finale |
| `build/v10.mid` | o MIDI, que é de onde o oráculo lê os dígitos de volta |

As versões anteriores estão em `build/` com o mesmo padrão de nome, da `v2` à `v9`. Elas ficam porque a peça foi feita por camadas, e ouvir a v2 depois da v10 mostra o que cada decisão acrescentou. As PoCs de antes da v2 (`pi-poc`, `pi-flauta`, `fib7`/`fib10` e as demais) foram descartadas: não eram versões da peça, eram teste de ideia solta.

## Comandos

```bash
python src/v10.py                                             # compõe a v10: MIDI, WAV e MP3
bin/conferir-digitos build/v10.mid                            # oráculo: a linha do MIDI é π? (exit 0 = PASS)
python src/grade.py --versao v10 --digitos 31 --saida build/v10-grade   # MusicXML e PDF da grade
bin/renderizar build/v10.mid                                  # só o áudio, sem recompor
```

O PDF sai sem MuseScore e sem sudo: `music21` escreve o MusicXML, `verovio` diagrama cada página em SVG, e o Chrome headless imprime.

## O que a máquina confere

Nada aqui se aceita por parecer certo. Cada versão tem um avaliador (`src/avaliar_*.py`) que mede o que o plano dela prometeu, e a regra é de três estados: **PASS, FAIL, UNKNOWN**, sendo que UNKNOWN bloqueia igual a FAIL. "Não consegui medir" nunca vira aprovado.

- `bin/conferir-digitos`: recupera a sequência de dígitos a partir das alturas do MIDI e compara com π calculado do zero. A v10 passa nos 62 símbolos, ida e volta. Pausa conta como dígito 0.
- `src/pi_digitos.py`: π sai da fórmula de Machin com aritmética inteira, com guarda de 50 dígitos. Nenhuma constante copiada de lugar nenhum - se o número estivesse errado, a música estaria errada, e o oráculo não teria como saber.
- `src/avaliar_v10.py`: mede o que a v10 prometeu - que a primeira metade sai idêntica à v9 nota por nota, que a segunda metade não usa mais Fá natural nem Si bemol, que a correlação de crescendo no trecho [76, 104) é alta, e que a nota mais aguda cai no acorde final.
- `build/v10-intactas.sha256`: as versões de v3 a v9 estão congeladas. Mexer nelas invalida a prova da v10, que é definida por diferença contra a v9.

## Ferramental

| Etapa | Ferramenta | Por quê |
|---|---|---|
| Dígitos de π | `src/pi_digitos.py`, fórmula de Machin com inteiros | nenhuma constante copiada; guarda de 50 dígitos |
| MIDI | `mido` 1.3.3 | escreve e lê o arquivo mensagem a mensagem, que é o que o oráculo precisa |
| Partitura | `music21` 10.5.0 | MusicXML, cifras e conferência de condução de vozes por máquina |
| Gravura | `verovio` 6.3.0 + Chrome headless | SVG por página e impressão em PDF, sem MuseScore e sem sudo |
| Áudio | `tinysoundfont` 0.3.7 + `FluidR3_GM.sf2` | renderiza SoundFont em Python puro, sem FluidSynth e sem placa de som |
| Reverb e MP3 | `sox`, `ffmpeg` | já instalados na máquina |

Python 3.12 em `.venv`, criado com `uv venv --python 3.12`. O `tinysoundfont` entra com `--no-deps`, porque o `pyaudio` que ele declara só serve para tocar ao vivo e exige `portaudio.h`. O SoundFont `FluidR3_GM.sf2` tem 141 MB e fica fora do histórico: baixe em `assets/soundfonts/` antes de renderizar áudio.

```bash
uv venv --python 3.12
.venv/bin/pip install -r requirements.txt
```

## A formação

Flauta, violino I, violino II, viola, violoncelo e piano. O violino I carrega a linha de π do começo ao fim; a flauta o dobra na oitava depois do eixo. No PDF, cada instrumento tem a pauta de uma cor, e as cores vêm do tema visual da Suzuki Petrópolis.

## Onde está o resto

O plano, o estado de cada frente e as decisões com o motivo delas vivem no vault, em `eltonleao-obsidian/Projects/Música do Pi/`. Este repositório é o código e o que ele produz; o porquê de cada escolha está lá.
