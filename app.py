import os
import time
import json
import logging
import threading
import warnings
import shutil
import subprocess
import sys

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import numpy as np
import librosa
import soundfile as sf
import pretty_midi
import webview
from flask import Flask, request, jsonify, send_from_directory, render_template
from werkzeug.utils import secure_filename
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
from music21 import stream, note, meter, tempo, instrument, environment, metadata

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR) 

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = BUNDLE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATE_DIR = os.path.join(BUNDLE_DIR, "templates")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=DATA_DIR)

def find_musescore4() -> Optional[str]:
    """Auto-detect MuseScore 4 across common install locations and the Windows Registry."""
    candidates = [
        r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
        r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\MuseScore 4\bin\MuseScore4.exe"),
    ]

    # 1. Check common filesystem paths
    for path in candidates:
        if os.path.isfile(path):
            logger.info(f"MuseScore 4 found at: {path}")
            return path

    # 2. Check Windows Registry (Inno Setup / MSI installers write here)
    try:
        import winreg
        registry_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{MSCORE4}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{MSCORE4}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{MSCORE4}"),
        ]
        # Also search by display name in all uninstall keys
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for uninstall_path in [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ]:
                try:
                    uninstall_key = winreg.OpenKey(hive, uninstall_path)
                    for i in range(winreg.QueryInfoKey(uninstall_key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(uninstall_key, i)
                            subkey = winreg.OpenKey(uninstall_key, subkey_name)
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                if "MuseScore 4" in display_name:
                                    install_loc = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                    exe_path = os.path.join(install_loc, "bin", "MuseScore4.exe")
                                    if os.path.isfile(exe_path):
                                        logger.info(f"MuseScore 4 found via registry: {exe_path}")
                                        return exe_path
                            except (FileNotFoundError, OSError):
                                pass
                            finally:
                                winreg.CloseKey(subkey)
                        except OSError:
                            continue
                    winreg.CloseKey(uninstall_key)
                except OSError:
                    continue
    except ImportError:
        pass  # Not on Windows — skip registry check

    # 3. Check PATH via shutil.which
    which_result = shutil.which("MuseScore4") or shutil.which("mscore4") or shutil.which("musescore4")
    if which_result and os.path.isfile(which_result):
        logger.info(f"MuseScore 4 found on PATH: {which_result}")
        return which_result

    logger.warning("MuseScore 4 not found. PDF export will be disabled.")
    return None

MUSESCORE_PATH = find_musescore4()

us = environment.UserSettings()
if MUSESCORE_PATH:
    us['musescoreDirectPNGPath'] = MUSESCORE_PATH

class TranscriptionError(Exception):
    pass

# ============================================================
# INSTRUMENT ARRANGEMENT PROFILES
# ============================================================
# For each selectable instrument:
#   polyphonic  - can it sound more than one note at once? (piano, guitar...)
#   reduction   - if NOT polyphonic, which note wins when notes overlap:
#                 "top" (melody-style lead) or "bottom" (bass-style)
#   range       - (low_midi, high_midi) playable range; notes outside this
#                 get octave-shifted so they actually fit the instrument
#   source      - which separated stem to transcribe from:
#                 "no_vocals" (full accompaniment, singing removed) or
#                 "vocals" (isolated lead/vocal line) for voice-type patches

@dataclass
class InstrumentProfile:
    polyphonic: bool
    range: Tuple[int, int]
    reduction: str = "top"
    source: str = "no_vocals"


INSTRUMENT_PROFILES: Dict[str, InstrumentProfile] = {
    "Acoustic Grand Piano":  InstrumentProfile(True,  (21, 108)),
    "Bright Acoustic Piano": InstrumentProfile(True,  (21, 108)),
    "Electric Grand Piano":  InstrumentProfile(True,  (21, 108)),
    "Honky-Tonk Piano":      InstrumentProfile(True,  (21, 108)),
    "Electric Piano 1":      InstrumentProfile(True,  (28, 103)),
    "Electric Piano 2":      InstrumentProfile(True,  (28, 103)),
    "Harpsichord":           InstrumentProfile(True,  (29, 89)),
    "Clavinet":              InstrumentProfile(True,  (28, 91)),
    "Celesta":               InstrumentProfile(True,  (60, 108)),
    "Glockenspiel":          InstrumentProfile(True,  (79, 108)),
    "Music Box":             InstrumentProfile(True,  (60, 96)),
    "Vibraphone":            InstrumentProfile(True,  (53, 89)),
    "Marimba":               InstrumentProfile(True,  (45, 96)),
    "Xylophone":             InstrumentProfile(True,  (65, 96)),
    "Tubular Bells":         InstrumentProfile(True,  (60, 77)),
    "Dulcimer":              InstrumentProfile(True,  (60, 84)),
    "Drawbar Organ":         InstrumentProfile(True,  (36, 96)),
    "Percussive Organ":      InstrumentProfile(True,  (36, 96)),
    "Rock Organ":            InstrumentProfile(True,  (36, 96)),
    "Church Organ":          InstrumentProfile(True,  (21, 108)),
    "Reed Organ":            InstrumentProfile(True,  (36, 96)),
    "Accordion":             InstrumentProfile(True,  (53, 89)),
    "Harmonica":             InstrumentProfile(False, (60, 84), "top"),
    "Tango Accordion":       InstrumentProfile(True,  (53, 89)),
    "Acoustic Guitar":       InstrumentProfile(True,  (40, 88)),
    "Electric Guitar":       InstrumentProfile(True,  (40, 88)),
    "Acoustic Bass":         InstrumentProfile(False, (28, 55), "bottom"),
    "Electric Bass":         InstrumentProfile(False, (28, 55), "bottom"),
    "Violin":                InstrumentProfile(False, (55, 100), "top"),
    "Viola":                 InstrumentProfile(False, (48, 91), "top"),
    "Cello":                 InstrumentProfile(False, (36, 76), "top"),
    "Contrabass":            InstrumentProfile(False, (28, 67), "bottom"),
    "Tremolo Strings":       InstrumentProfile(True,  (36, 91)),
    "Pizzicato Strings":     InstrumentProfile(True,  (36, 91)),
    "Orchestral Harp":       InstrumentProfile(True,  (24, 103)),
    "Timpani":               InstrumentProfile(False, (36, 53), "bottom"),
    "String Ensemble 1":     InstrumentProfile(True,  (36, 91)),
    "String Ensemble 2":     InstrumentProfile(True,  (36, 91)),
    "Synth Strings 1":       InstrumentProfile(True,  (36, 91)),
    "Synth Strings 2":       InstrumentProfile(True,  (36, 91)),
    "Choir Aahs":            InstrumentProfile(True,  (48, 84), source="vocals"),
    "Voice Oohs":            InstrumentProfile(True,  (48, 84), source="vocals"),
    "Synth Voice":           InstrumentProfile(True,  (48, 84), source="vocals"),
    "Orchestra Hit":         InstrumentProfile(True,  (48, 72)),
    "Trumpet":               InstrumentProfile(False, (55, 82), "top"),
    "Trombone":              InstrumentProfile(False, (40, 72), "top"),
    "Tuba":                  InstrumentProfile(False, (28, 58), "bottom"),
    "Muted Trumpet":         InstrumentProfile(False, (55, 82), "top"),
    "French Horn":           InstrumentProfile(False, (41, 77), "top"),
    "Brass Section":         InstrumentProfile(True,  (36, 84)),
    "Synth Brass 1":         InstrumentProfile(True,  (36, 84)),
    "Synth Brass 2":         InstrumentProfile(True,  (36, 84)),
    "Soprano Sax":           InstrumentProfile(False, (56, 87), "top"),
    "Alto Sax":              InstrumentProfile(False, (49, 80), "top"),
    "Tenor Sax":             InstrumentProfile(False, (44, 75), "top"),
    "Baritone Sax":          InstrumentProfile(False, (36, 67), "top"),
    "Oboe":                  InstrumentProfile(False, (58, 91), "top"),
    "English Horn":          InstrumentProfile(False, (52, 84), "top"),
    "Bassoon":               InstrumentProfile(False, (34, 72), "bottom"),
    "Clarinet":              InstrumentProfile(False, (50, 94), "top"),
    "Piccolo":               InstrumentProfile(False, (74, 108), "top"),
    "Flute":                 InstrumentProfile(False, (60, 96), "top"),
    "Recorder":              InstrumentProfile(False, (60, 84), "top"),
    "Pan Flute":             InstrumentProfile(False, (60, 84), "top"),
    "Blown Bottle":          InstrumentProfile(False, (60, 84), "top"),
    "Shakuhachi":            InstrumentProfile(False, (55, 84), "top"),
    "Whistle":               InstrumentProfile(False, (60, 84), "top"),
    "Ocarina":               InstrumentProfile(False, (60, 84), "top"),
}

DEFAULT_PROFILE = InstrumentProfile(True, (36, 91))


def get_instrument_profile(instrument_name: str) -> InstrumentProfile:
    return INSTRUMENT_PROFILES.get(instrument_name, DEFAULT_PROFILE)


# ============================================================
# STEM SEPARATION (Demucs — free, open-source, runs locally)
# ============================================================

def demucs_available() -> bool:
    try:
        import demucs  # noqa: F401
        return True
    except ImportError:
        return False


class StemSeparator:
    """Splits a mix into 'vocals' and 'no_vocals' (everything else) so the
    transcriber isn't confused by singing, and so vocal-type instrument
    choices (Choir, Synth Voice) can transcribe the actual sung line.
    Vocal removal always runs — there is no user-facing toggle for it."""

    def separate(self, audio_path: str, work_dir: str) -> Dict[str, str]:
        fallback = {"no_vocals": audio_path, "vocals": audio_path}

        if not demucs_available():
            logger.warning("Demucs not installed - skipping vocal separation.")
            return fallback

        os.makedirs(work_dir, exist_ok=True)
        cmd = [
            sys.executable, "-m", "demucs.separate",
            "--two-stems", "vocals",
            "-n", "htdemucs",
            "-o", work_dir,
            audio_path,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Stem separation failed ({e}); using original mix.")
            return fallback

        track_name = os.path.splitext(os.path.basename(audio_path))[0]
        stem_dir = os.path.join(work_dir, "htdemucs", track_name)
        no_vocals_path = os.path.join(stem_dir, "no_vocals.wav")
        vocals_path = os.path.join(stem_dir, "vocals.wav")

        if not (os.path.exists(no_vocals_path) and os.path.exists(vocals_path)):
            logger.warning("Stem output not found; using original mix.")
            return fallback

        return {"no_vocals": no_vocals_path, "vocals": vocals_path}


class TranscriptionState:
    def __init__(self):
        self._lock = threading.Lock()
        self._progress = 0
        self._message = ""
        self._cancelled = False
        self._active = False
        self._version = 0
    
    def start(self) -> int:
        with self._lock:
            self._version += 1
            self._progress = 0
            self._message = "Preparing audio..."
            self._cancelled = False
            self._active = True
            return self._version
    
    def update(self, version: int, progress: int, message: str):
        with self._lock:
            if self._version == version and not self._cancelled:
                self._progress = progress
                self._message = message
    
    def cancel(self):
        with self._lock:
            self._cancelled = True
            self._active = False
    
    def is_cancelled(self, version: int) -> bool:
        with self._lock:
            return self._cancelled or self._version != version
    
    def finish(self, version: int):
        with self._lock:
            if self._version == version:
                self._active = False
                self._progress = 100
    
    def get_state(self):
        with self._lock:
            return {
                'progress': self._progress,
                'message': self._message,
                'cancelled': self._cancelled,
                'active': self._active
            }

transcription_state = TranscriptionState()

@dataclass
class TranscriberConfig:
    min_confidence: float = 0.40       
    min_duration_sec: float = 0.05     
    quantize_grid: float = 0.25        
    time_signature: str = '4/4'
    default_bpm: int = 120
    musescore_path: Optional[str] = MUSESCORE_PATH
    manual_bpm: Optional[float] = None 
    transpose_semitones: int = 0       
    velocity_multiplier: float = 1.8   

class SymbolicTranscriber:
    def __init__(self, config: TranscriberConfig):
        self.config = config

    def _extract_bpm_from_events(self, events: List[Dict]) -> float:
        """Derives tempo using multi-grid onset alignment across 60-180 BPM."""
        if self.config.manual_bpm is not None and self.config.manual_bpm > 0:
            return float(self.config.manual_bpm)

        if len(events) < 3:
            return float(self.config.default_bpm)

        onsets = np.array(sorted([e['start_sec'] for e in events]))
        rel_onsets = onsets - onsets[0]

        candidate_bpms = np.arange(60.0, 181.0, 1.0)
        best_bpm = float(self.config.default_bpm)
        best_score = -float('inf')

        for bpm in candidate_bpms:
            # 16th-note sub-beat period in seconds
            q_sec = 15.0 / bpm
            
            # Grid alignment metric
            phases = 2.0 * np.pi * (rel_onsets / q_sec)
            grid_score = float(np.mean(np.cos(phases)))
            
            # Gentle tie-breaker to resolve harmonic ties
            tie_breaker = -0.05 * abs(np.log(bpm / 115.0))
            score = grid_score + tie_breaker

            if score > best_score:
                best_score = score
                best_bpm = bpm

        return float(round(best_bpm))

    def _get_raw_events(self, audio_path: str) -> List[Dict]:
        try:
            _, _, raw_events = predict(audio_path, model_or_model_path=ICASSP_2022_MODEL_PATH)
        except Exception as e:
            raise TranscriptionError(f"BasicPitch inference failed: {e}")

        if not raw_events:
            raise TranscriptionError("No notes detected.")

        cleaned_events = []
        for evt in raw_events:
            start_t, end_t, pitch_midi, amplitude = evt[:4]
            if amplitude < self.config.min_confidence or (end_t - start_t) < self.config.min_duration_sec:
                continue
            
            pitch_val = int(round(pitch_midi)) + self.config.transpose_semitones
            vel_val = min(127, int(amplitude * 127 * self.config.velocity_multiplier))
                
            cleaned_events.append({
                'start_sec': start_t, 'end_sec': end_t,
                'pitch': pitch_val, 'velocity': vel_val
            })

        if not cleaned_events:
            raise TranscriptionError("All notes filtered out as noise.")

        # NOTE: every simultaneous note is kept here (no monophonic collapse).
        # Whether the final output is polyphonic (chords) or reduced to a
        # single line is decided later, per target instrument, in process().
        return sorted(cleaned_events, key=lambda x: (x['start_sec'], -x['velocity']))

    def _clamp_to_range(self, events: List[Dict], low: int, high: int) -> List[Dict]:
        """Octave-shifts notes outside the instrument's playable range until
        they fit, instead of leaving out-of-range notes as-is."""
        clamped = []
        for evt in events:
            pitch = evt['pitch']
            while pitch < low:
                pitch += 12
            while pitch > high:
                pitch -= 12
            pitch = max(low, min(high, pitch))  # safety net for very narrow ranges
            new_evt = dict(evt)
            new_evt['pitch'] = pitch
            clamped.append(new_evt)
        return clamped

    def _reduce_to_single_line(self, events: List[Dict], mode: str) -> List[Dict]:
        """Collapses overlapping notes to one active note at a time, for
        instruments that can't play chords.

        mode='top'    keeps the highest note sounding (melody-style lead)
        mode='bottom' keeps the lowest note sounding (bass-style)

        This picks notes by melodic role rather than by volume, which is
        what the old "loudest note wins" collapse did.
        """
        if not events:
            return []

        def better(a, b):
            return a['pitch'] >= b['pitch'] if mode == "top" else a['pitch'] <= b['pitch']

        ordered = sorted(events, key=lambda e: e['start_sec'])
        resolved: List[Dict] = []

        for evt in ordered:
            evt = dict(evt)
            still_active = [r for r in resolved if r['end_sec'] > evt['start_sec']]
            if any(better(r, evt) for r in still_active):
                continue  # a preferred (higher/lower) note is already sounding
            for r in still_active:
                r['end_sec'] = min(r['end_sec'], evt['start_sec'])
            resolved.append(evt)

        resolved = [e for e in resolved if (e['end_sec'] - e['start_sec']) >= self.config.min_duration_sec]
        return sorted(resolved, key=lambda e: e['start_sec'])

    def _quantize_events(self, events: List[Dict], bpm: float, reduction: Optional[str]) -> List[Dict]:
        """reduction=None keeps every note in a time-slot (chords intact).
        reduction='top'/'bottom' is a safety net that re-applies the melodic-
        role pick if grid-snapping stacks two originally distinct notes onto
        the same slot."""
        sec_per_beat = 60.0 / bpm
        quantized_events = []

        if not events:
            return []

        first_onset = events[0]['start_sec']

        for evt in events:
            rel_start = max(0.0, evt['start_sec'] - first_onset)
            dur_sec = max(self.config.min_duration_sec, evt['end_sec'] - evt['start_sec'])

            start_beat = rel_start / sec_per_beat
            dur_beat = dur_sec / sec_per_beat

            grid = self.config.quantize_grid
            q_start = round(start_beat / grid) * grid
            q_dur = max(grid, round(dur_beat / grid) * grid)

            quantized_events.append({
                'offset': q_start, 'duration': q_dur,
                'pitch': evt['pitch'], 'velocity': evt['velocity']
            })

        from collections import defaultdict
        offset_groups = defaultdict(list)
        for evt in quantized_events:
            offset_groups[evt['offset']].append(evt)
            
        final_events = []
        for offset in sorted(offset_groups.keys()):
            group = offset_groups[offset]
            if reduction is not None:
                key_fn = (lambda x: x['pitch']) if reduction == "top" else (lambda x: -x['pitch'])
                best_note = max(group, key=key_fn)
                final_events.append(best_note)
            else:
                max_dur = max(n['duration'] for n in group)
                for n in group:
                    n['duration'] = max_dur
                    final_events.append(n)

        final_events = sorted(final_events, key=lambda x: x['offset'])
        
        if reduction is not None:
            for i in range(len(final_events) - 1):
                curr = final_events[i]
                next_evt = final_events[i+1]
                # If current note bleeds into the next, truncate it
                if curr['offset'] + curr['duration'] > next_evt['offset']:
                    new_dur = next_evt['offset'] - curr['offset']
                    curr['duration'] = max(self.config.quantize_grid, new_dur)

        return final_events

    def _smooth_octaves(self, events: List[Dict]) -> List[Dict]:
        """Smooth erratic octave jumps caused by BasicPitch harmonic mis-detection.
        
        Melodies rarely jump more than ~7 semitones between consecutive notes.
        When an octave-error is detected, this pulls the note back to the
        nearest octave that minimises the interval from its neighbour.
        """
        if len(events) < 2:
            return events

        pitches = [e['pitch'] for e in events]
        median_pitch = int(np.median(pitches))

        smoothed = []
        for i, evt in enumerate(events):
            new_evt = dict(evt)
            pitch = new_evt['pitch']

            if i == 0:
                # Anchor the first note near the median pitch
                best = pitch
                best_dist = abs(pitch - median_pitch)
                for shift in [-24, -12, 12, 24]:
                    c = pitch + shift
                    if 21 <= c <= 108 and abs(c - median_pitch) < best_dist:
                        best_dist = abs(c - median_pitch)
                        best = c
                new_evt['pitch'] = best
            else:
                prev_pitch = smoothed[-1]['pitch']
                # If interval > 7 semitones, try octave corrections
                if abs(pitch - prev_pitch) > 7:
                    best = pitch
                    best_interval = abs(pitch - prev_pitch)
                    for shift in [-24, -12, 12, 24]:
                        c = pitch + shift
                        if 21 <= c <= 108 and abs(c - prev_pitch) < best_interval:
                            best_interval = abs(c - prev_pitch)
                            best = c
                    new_evt['pitch'] = best

            smoothed.append(new_evt)

        return smoothed

    def _build_music21_score(self, quantized_events: List[Dict], bpm: float, instrument_name: str, polyphonic: bool) -> stream.Score:
        from music21 import key as m21key, clef
        
        # Octave-jump smoothing assumes one active note at a time - applying
        # it to simultaneous chord notes would scramble their voicing, so it
        # only runs for single-line (non-polyphonic) arrangements.
        if not polyphonic:
            quantized_events = self._smooth_octaves(quantized_events)
        
        part = stream.Part()
        part.insert(0, instrument.fromString(instrument_name))
        part.insert(0, tempo.MetronomeMark(number=bpm))
        part.insert(0, meter.TimeSignature(self.config.time_signature))

        for evt in quantized_events:
            n = note.Note(evt['pitch'])
            n.quarterLength = evt['duration']
            n.volume.velocity = evt['velocity']
            part.insert(evt['offset'], n)

        detected_key = part.analyze('key')
        ks = detected_key if detected_key else m21key.KeySignature(0)
        part.insert(0, ks)
        
        pitches = [e['pitch'] for e in quantized_events]
        median_pitch = int(np.median(pitches)) if pitches else 60
        if median_pitch >= 55:
            part.insert(0, clef.TrebleClef())
        else:
            part.insert(0, clef.BassClef())

        for n_obj in part.recurse().getElementsByClass('Note'):
            n_obj.pitch.spellingIsInferred = True
            
        part.makeAccidentals(inPlace=True, cautionaryNotImmediateRepeat=False)
        
        final_score = stream.Score()
        final_score.insert(0, metadata.Metadata(title="Musicify Studio Sheet"))
        final_score.insert(0, part.makeNotation())
        return final_score

    def _debug_events(self, events: List[Dict], label: str):
        """Debug helper to log event details"""
        logger.info(f"=== {label} ===")
        logger.info(f"Total events: {len(events)}")
        if events:
            logger.info(f"First event: {events[0]}")
            logger.info(f"Last event: {events[-1]}")
            pitches = [e['pitch'] for e in events]
            logger.info(f"Pitch range: {min(pitches)} - {max(pitches)}")

    def process(self, audio_path: str, instrument_name: str, output_dir: str, base_name: str, state_version: int) -> Tuple[str, str, Optional[str], float, float]:
        def check_cancel():
            if transcription_state.is_cancelled(state_version):
                raise TranscriptionError("Cancelled by user")
                
        profile = get_instrument_profile(instrument_name)

        transcription_state.update(state_version, 8, "Removing vocals...")
        check_cancel()
        stems_dir = os.path.join(output_dir, f"{base_name}_stems")
        stems = StemSeparator().separate(audio_path, stems_dir)
        source_audio = stems[profile.source]

        transcription_state.update(state_version, 15, "Listening to every note...")
        check_cancel()
        
        raw_events = self._get_raw_events(source_audio)
        if not raw_events:
            raise TranscriptionError("No notes detected in audio")

        raw_events = self._clamp_to_range(raw_events, *profile.range)
        if not profile.polyphonic:
            raw_events = self._reduce_to_single_line(raw_events, profile.reduction)
        
        self._debug_events(raw_events, "RAW EVENTS")
        first_onset = raw_events[0]['start_sec']
        
        transcription_state.update(state_version, 50, "Decoding the musical DNA...")
        check_cancel()
        bpm = self._extract_bpm_from_events(raw_events)
        reduction = None if profile.polyphonic else profile.reduction
        quantized_events = self._quantize_events(raw_events, bpm, reduction)
        
        if not quantized_events:
            raise TranscriptionError("All notes were filtered out during quantization")
        
        self._debug_events(quantized_events, "QUANTIZED EVENTS")
        
        transcription_state.update(state_version, 70, "Composing your masterpiece...")
        check_cancel()
        score = self._build_music21_score(quantized_events, bpm, instrument_name, profile.polyphonic)
        
        # Verify the score has notes
        all_notes = list(score.flatten().notesAndRests)
        logger.info(f"Score contains {len(all_notes)} total notes/rests")
        if not all_notes:
            raise TranscriptionError("Score contains no notes after processing")
        
        # Debug: Print first few notes
        notes_only = [n for n in all_notes if isinstance(n, note.Note)]
        logger.info(f"Score has {len(notes_only)} actual notes")
        for n in notes_only[:5]:
            logger.info(f"Note: {n.nameWithOctave}, offset: {n.offset}, duration: {n.quarterLength}")
        
        transcription_state.update(state_version, 85, "Printing the sheet music...")
        check_cancel()
        
        xml_filename = f"{base_name}.xml"
        midi_filename = f"{base_name}.mid"
        pdf_filename = f"{base_name}.pdf"
        
        xml_path = os.path.join(output_dir, xml_filename)
        midi_path = os.path.join(output_dir, midi_filename)
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        # 1. Export MusicXML - WITH VALIDATION
        try:
            score.write('musicxml', fp=xml_path)
            # Verify the XML file was created and has content
            if not os.path.exists(xml_path):
                raise TranscriptionError("MusicXML file was not created")
            xml_size = os.path.getsize(xml_path)
            logger.info(f"MusicXML exported: {xml_path} ({xml_size} bytes)")
            if xml_size < 100:
                raise TranscriptionError("MusicXML file is too small, likely empty")
        except Exception as e:
            raise TranscriptionError(f"Failed to write MusicXML: {e}")
        
        # 2. Export MIDI via pretty_midi
        pm = pretty_midi.PrettyMIDI()
        try:
            program = pretty_midi.instrument_name_to_program(instrument_name)
        except Exception:
            program = 0
        inst = pretty_midi.Instrument(program=program)
        
        for evt in raw_events:
            inst.notes.append(pretty_midi.Note(
                velocity=int(evt['velocity']),
                pitch=int(evt['pitch']),
                start=float(evt['start_sec']),
                end=float(evt['end_sec'])
            ))
        pm.instruments.append(inst)
        pm.write(midi_path)
        logger.info(f"MIDI exported: {midi_path}")
        
        # 3. Render PDF via MuseScore
        transcription_state.update(state_version, 95, "Adding the finishing touches...")
        pdf_generated = False
        if self.config.musescore_path and os.path.exists(self.config.musescore_path):
            try:
                logger.info(f"Attempting PDF conversion with MuseScore: {self.config.musescore_path}")
                # MuseScore 4 CLI with proper error handling
                result = subprocess.run(
                    [self.config.musescore_path, "-f", "-o", pdf_path, xml_path],
                    check=True, 
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                logger.info(f"MuseScore stdout: {result.stdout}")
                if result.stderr:
                    logger.warning(f"MuseScore stderr: {result.stderr}")
                
                # Validate the PDF
                if os.path.exists(pdf_path):
                    pdf_size = os.path.getsize(pdf_path)
                    logger.info(f"PDF file created: {pdf_path} ({pdf_size} bytes)")
                    if pdf_size > 5000:
                        pdf_generated = True
                        logger.info("PDF successfully generated")
                    else:
                        logger.warning(f"PDF file too small ({pdf_size} bytes), likely invalid")
                else:
                    logger.warning("PDF file was not created by MuseScore")
                    
            except subprocess.CalledProcessError as e:
                logger.warning(f"MuseScore conversion failed with error: {e.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning("PDF generation timed out after 120 seconds")
            except Exception as e:
                logger.warning(f"PDF generation error: {e}")
                
            # Clean up failed PDF attempts
            if not pdf_generated and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    logger.info("Removed invalid PDF file")
                except OSError:
                    pass
        else:
            logger.warning("MuseScore not available, skipping PDF generation")
        
        transcription_state.finish(state_version)
        return xml_filename, midi_filename, (pdf_filename if pdf_generated else None), bpm, first_onset

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/transcription/progress', methods=['GET'])
def get_progress():
    return jsonify(transcription_state.get_state())

@app.route('/transcription/cancel', methods=['POST'])
def cancel_transcription():
    transcription_state.cancel()
    return jsonify({'success': True})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400

    file = request.files['audio']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    original_filename = secure_filename(file.filename)
    inst = request.form.get('instrument', 'Acoustic Grand Piano')
    
    unique_id = str(int(time.time()))
    base_name, ext = os.path.splitext(original_filename)
    safe_inst = inst.replace(' ', '_')
    # Unified base naming for all generated files
    core_filename = f"{unique_id}_{base_name}_{safe_inst}"
    filename = f"{core_filename}{ext}"
    
    audio_path = os.path.join(DATA_DIR, filename)
    file.save(audio_path)

    try:
        state_version = transcription_state.start()
        transcription_state.update(state_version, 5, "Tuning the instruments...")
        
        if audio_path.lower().endswith(".mp3"):
            wav_path = audio_path.replace(".mp3", ".wav")
            y, sr = librosa.load(audio_path, sr=None)
            sf.write(wav_path, y, sr)
            os.remove(audio_path) 
            audio_path = wav_path
            filename = os.path.basename(wav_path)

        config = TranscriberConfig()
        transcriber = SymbolicTranscriber(config)
        xml_file, midi_file, pdf_file, detected_bpm, audio_offset = transcriber.process(audio_path, inst, DATA_DIR, core_filename, state_version)

        history_file = os.path.join(DATA_DIR, "history.json")
        history = []
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                history = json.load(f)
        
        record = {
            "id": unique_id,
            "name": original_filename,
            "instrument": inst,
            "bpm": detected_bpm,
            "audio_offset": audio_offset,
            "audio_url": f"/data/{filename}",
            "xml_url": f"/data/{xml_file}",
            "midi_url": f"/data/{midi_file}",
            "pdf_url": f"/data/{pdf_file}" if pdf_file else None
        }
        history.insert(0, record)
        with open(history_file, "w") as f:
            json.dump(history, f)

        return jsonify(record)
    except TranscriptionError as e:
        if str(e) == "Cancelled by user":
            return jsonify({'cancelled': True})
        logger.error(f"Transcription Error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Upload Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/data/<path:filename>')
def serve_data(filename):
    return send_from_directory(DATA_DIR, filename)

@app.route('/history', methods=['GET'])
def get_history():
    history_file = os.path.join(DATA_DIR, "history.json")
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        'musescore_installed': MUSESCORE_PATH is not None and os.path.exists(MUSESCORE_PATH),
        'musescore_path': MUSESCORE_PATH
    })

@app.route('/delete/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    history_file = os.path.join(DATA_DIR, "history.json")
    if not os.path.exists(history_file):
        return jsonify({'error': 'History not found'}), 404
        
    try:
        with open(history_file, "r") as f:
            history = json.load(f)
            
        item_to_delete = next((item for item in history if item["id"] == item_id), None)
        if not item_to_delete:
            return jsonify({'error': 'Item not found'}), 404
            
        history = [item for item in history if item["id"] != item_id]
        with open(history_file, "w") as f:
            json.dump(history, f)
            
        files_to_delete = [
            item_to_delete.get("audio_url"),
            item_to_delete.get("xml_url"),
            item_to_delete.get("midi_url"),
            item_to_delete.get("pdf_url")
        ]
        
        for file_url in files_to_delete:
            if file_url:
                filename = file_url.split('/')[-1]
                file_path = os.path.join(DATA_DIR, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error during deletion: {str(e)}")
        return jsonify({'error': str(e)}), 500

class JsApi:
    def close_app(self):
        """Close the pywebview window and terminate the application."""
        if webview.windows:
            webview.windows[0].destroy()
            
    def trigger_native_download(self, filename: str):
        def _process_download():
            source_path = os.path.join(DATA_DIR, filename)
            if not os.path.exists(source_path):
                logger.error(f"Error: Could not find {source_path}")
                return
                
            try:
                if not webview.windows:
                    return
                active_window = webview.windows[0]
                
                dialog_type = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
                
                result = active_window.create_file_dialog(
                    dialog_type, 
                    directory='', 
                    save_filename=filename
                )
                
                if result and len(result) > 0:
                    destination = result[0]
                    shutil.copy2(source_path, destination)
                    logger.info(f"Successfully saved to {destination}")
            except Exception as e:
                logger.error(f"Failed to save file: {e}")

        threading.Thread(target=_process_download, daemon=True).start()

def start_server():
    app.run(host='127.0.0.1', port=5050, threaded=True)

if __name__ == '__main__':
    logger.info("Starting Musicify Server...")
    
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    
    js_api = JsApi()
    window = webview.create_window(
        'Musicify Studio', 
        'http://127.0.0.1:5050', 
        width=1100, 
        height=800,
        js_api=js_api
    )
    
    webview.start()