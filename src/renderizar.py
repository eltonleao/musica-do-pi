"""Renderiza um MIDI em WAV e MP3 sem placa de som e sem interface.

Cadeia: tinysoundfont (SoundFont General MIDI) -> WAV 44,1 kHz 16 bits ->
sox (reverb leve, opcional) -> ffmpeg (MP3 192 kbps).

Uso: python src/renderizar.py build/pi-poc.mid [--soundfont assets/soundfonts/FluidR3_GM.sf2]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import tinysoundfont

TAXA = 44100
BLOCO = 4096
CAUDA_SEGUNDOS = 2.5


def sintetizar(midi: Path, soundfont: Path, ganho_db: float = -6.0) -> np.ndarray:
    """As amostras em float, estéreo, com a cauda do sintetizador, sem normalizar."""
    synth = tinysoundfont.Synth(gain=ganho_db, samplerate=TAXA)
    synth.sfload(str(soundfont))
    seq = tinysoundfont.Sequencer(synth)
    seq.midi_load(str(midi))
    blocos: list[np.ndarray] = []
    cauda = 0
    while True:
        amostras = np.frombuffer(synth.generate(BLOCO), dtype=np.float32).reshape(-1, 2)
        blocos.append(amostras.copy())
        if seq.is_empty():
            cauda += BLOCO
            if cauda >= CAUDA_SEGUNDOS * TAXA:
                break
    return np.concatenate(blocos)


def midi_para_wav(midi: Path, soundfont: Path, wav: Path, ganho_db: float = -6.0,
                  normalizar: bool = True) -> float:
    """Com normalizar=False o pico não é reescalado: o que passa de 1,0 satura."""
    audio = sintetizar(midi, soundfont, ganho_db)
    pico = float(np.max(np.abs(audio))) or 1.0
    if normalizar and pico > 0.98:
        audio = audio / pico * 0.98
    inteiros = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(inteiros.tobytes())
    return len(audio) / TAXA


def reverb(wav: Path) -> bool:
    if not shutil.which("sox"):
        return False
    tmp = wav.with_suffix(".reverb.wav")
    r = subprocess.run(["sox", str(wav), str(tmp), "reverb", "35", "50", "80", "gain", "-n", "-1"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False
    tmp.replace(wav)
    return True


def mp3(wav: Path, saida: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
                    "-b:a", "192k", "-metadata", "title=Música do Pi (PoC)",
                    "-metadata", "artist=dígitos de pi", str(saida)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("midi")
    ap.add_argument("--soundfont", default="assets/soundfonts/FluidR3_GM.sf2")
    ap.add_argument("--sem-reverb", action="store_true")
    args = ap.parse_args()
    midi = Path(args.midi)
    wav = midi.with_suffix(".wav")
    duracao = midi_para_wav(midi, Path(args.soundfont), wav)
    com_reverb = False if args.sem_reverb else reverb(wav)
    mp3(wav, midi.with_suffix(".mp3"))
    print(f"{wav.name}: {duracao:.1f} s, reverb={'sim' if com_reverb else 'não'}; {midi.with_suffix('.mp3').name} gravado")


if __name__ == "__main__":
    main()
