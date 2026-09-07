<h1 align="center">Musicify Studio</h1>

<p align="center">
  <b>AI-Powered Audio-to-Sheet-Music Transcription Engine</b><br/>
  Transform any audio recording into publication-ready sheet music, MIDI, and MusicXML — locally, offline, and free.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version" />
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/python-3.10+-yellow?style=flat-square&logo=python&logoColor=white" alt="Python" />
</p>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [Competitive Analysis](#competitive-analysis)
- [Known Limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Musicify Studio is a desktop application that uses neural audio analysis to transcribe audio recordings into notated sheet music. It accepts WAV or MP3 files, separates vocals from instrumentation using Demucs, detects individual notes with Spotify's Basic Pitch model, and outputs professional-quality sheet music rendered in-app via OpenSheetMusicDisplay.

All processing runs entirely on-device. No internet connection, cloud API, or subscription is required after installation.

---

## Key Features

| Feature | Description |
|---|---|
| **Neural Note Detection** | Spotify's Basic Pitch (ICASSP 2022) model performs polyphonic pitch detection with sub-note accuracy. |
| **Automatic Vocal Separation** | Integrated Demucs (htdemucs) stem separator isolates vocals from accompaniment before transcription, dramatically improving note accuracy. |
| **65+ Instrument Profiles** | Each instrument has a curated range, polyphony mode, and melodic reduction strategy (top-line melody vs. bass-line). Notes are octave-shifted to fit the target instrument's playable range. |
| **Intelligent BPM Detection** | Multi-grid onset alignment algorithm scans 60–180 BPM using 16th-note quantization scoring to lock the true tempo. Manual override available. |
| **Octave Smoothing** | Post-processing algorithm detects and corrects erratic octave jumps caused by harmonic overtone mis-detection. |
| **Multi-Format Export** | Outputs MusicXML (`.xml`), MIDI (`.mid`), and PDF sheet music (via MuseScore 4). |
| **In-App Sheet Music Viewer** | Full OpenSheetMusicDisplay renderer with zoom, pagination, and warm-paper aesthetic. |
| **Synchronized Audio Playback** | Play back the original audio alongside the rendered score with a tracking cursor. |
| **Transcription History** | Persistent session history with one-click access to past transcriptions. |
| **Native Desktop Experience** | Runs as a native window using PyWebView — no browser required. |

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   PyWebView Window                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │             Frontend (HTML/JS/CSS)               │  │
│  │    OpenSheetMusicDisplay · TailwindCSS · OSMD    │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │ HTTP (localhost:5050)          │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │              Flask Backend (app.py)              │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────────┐   │  │
│  │  │ Demucs  │→ │BasicPitch│→ │SymbolicTranscr.│   │  │
│  │  │ (Stems) │  │ (Notes)  │  │  (Score Build) │   │  │
│  │  └─────────┘  └──────────┘  └───────┬────────┘   │  │
│  │                                     │            │  │
│  │             ┌─────────────┬────────┬┘            │  │
│  │             ▼             ▼        ▼             │  │
│  │          MusicXML       MIDI    PDF (MuseScore)  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.10 or higher |
| **OS** | Windows 10/11 (x64) |
| **MuseScore 4** | *Optional.* Required only for PDF export. All other features work without it. [Download MuseScore 4](https://musescore.org/en/download) |

> **Note:** MuseScore 4 is auto-detected from standard install paths, the Windows Registry, and the system `PATH`. No manual configuration is needed.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/yoswag75/Musicify
cd musicify-studio

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch the application
python app.py
```

### Dependencies

```
numpy==1.26.4
librosa==0.11.0
soundfile==0.13.1
pretty-midi==0.2.10
flask==3.0.0
pywebview==6.2.1
basic-pitch==0.4.0
music21==9.7.1
tensorflow==2.15.0
werkzeug>=3.0.0
```

---

## Usage

1. **Launch** the application by running `python app.py` in the terminal.
2. **Select an instrument** from the dropdown — this controls range clamping, polyphony, and melodic reduction.
3. **Upload** a WAV or MP3 file using the file picker.
4. **Wait** for the transcription pipeline (progress bar tracks each stage: vocal separation → note detection → tempo analysis → score composition → rendering).
5. **View** the rendered sheet music directly in the app.
6. **Download** the output in MusicXML, MIDI, or PDF format using the native save dialog.
7. **Browse** previous transcriptions from the history panel.

---

## Project Structure

```
Musicify_v1.0.0/
├── app.py                  # Core application — Flask backend, transcription engine, PyWebView launcher
├── requirements.txt        # Python dependencies
├── icon.ico                # Application icon
├── templates/
│   └── index.html          # Frontend UI (HTML/CSS/JS, OpenSheetMusicDisplay, TailwindCSS)
└── data/                   # Runtime output directory (transcription results, history)
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Audio Intelligence** | [Basic Pitch](https://github.com/spotify/basic-pitch) (Spotify) — neural polyphonic note detection |
| **Stem Separation** | [Demucs](https://github.com/adefossez/demucs) (Meta) — state-of-the-art source separation |
| **Music Notation** | [music21](https://web.mit.edu/music21/) (MIT) — computational musicology and score construction |
| **Score Rendering** | [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/) — browser-based MusicXML renderer |
| **PDF Export** | [MuseScore 4](https://musescore.org/) — professional engraving engine |
| **MIDI Export** | [pretty-midi](https://github.com/craffel/pretty-midi) — MIDI file manipulation |
| **Audio Processing** | [librosa](https://librosa.org/) + [soundfile](https://github.com/bastibe/python-soundfile) |
| **Backend** | [Flask](https://flask.palletsprojects.com/) |
| **Desktop Shell** | [PyWebView](https://pywebview.flowrl.com/) — native OS window wrapping the web UI |
| **ML Runtime** | [TensorFlow 2.15](https://www.tensorflow.org/) |

---

## Competitive Analysis

Musicify Studio operates in the automatic music transcription (AMT) space. The following comparison evaluates it against nine established tools and platforms.

| Criteria | **Musicify Studio** | **Demucs** (Meta) | **Smule** | **AnthemScore** | **ScoreCloud** | **Klangio** | **Melodyne** (Celemony) | **Moises** | **Songscription.ai / La Touche Musicale** | **Transcribe! / Soundslice** |
|---|---|---|---|---|---|---|---|---|---|---|
| **Primary Function** | Full-pipeline AMT (audio → sheet music) | Stem separation only | Karaoke / vocal effects | Audio to sheet music | Audio to notation | Audio to sheet music (web) | Audio editing / pitch correction | AI stem separation + practice tools | Audio to sheet music / piano learning | Slow-down / loop / transcription aid |
| **Sheet Music Output** | ✅ MusicXML, PDF, MIDI | ❌ | ❌ | ✅ PDF, MusicXML, MIDI | ✅ MusicXML | ✅ MusicXML, PDF, MIDI | ❌ | ❌ | ✅ MIDI, PDF | Limited (Soundslice viewer only) |
| **Vocal Separation** | ✅ Built-in (Demucs) | ✅ Core feature | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ Core feature | ❌ | ❌ |
| **Offline / Local** | ✅ Fully offline | ✅ | ❌ Cloud-only | ✅ | ❌ Cloud-based | ❌ Cloud-based | ✅ | ❌ Cloud-based | ❌ Cloud-based | Partial (Transcribe! local, Soundslice cloud) |
| **Pricing** | **Free & open source** | Free & open source | Freemium (subscription) | $39 one-time | Freemium (subscription) | Freemium (credits + subscription) | €699+ | Freemium ($40–$100/yr) | Freemium (subscription) | $39–$149 / subscription |
| **Instrument Awareness** | ✅ 65+ profiles with range/polyphony | ❌ N/A | ❌ | Limited | Limited | Limited (piano/guitar focus) | ❌ N/A | ❌ N/A | Limited (piano-centric) | ❌ N/A |
| **BPM Detection** | ✅ Multi-grid onset analysis | ❌ N/A | ❌ | ✅ Basic | ✅ | ✅ Basic | ❌ N/A | ✅ | ✅ Basic | ✅ (manual tap tempo) |
| **In-App Score Viewer** | ✅ OSMD with playback sync | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ (Soundslice) |
| **Privacy** | ✅ All data stays on-device | ✅ | ❌ Data uploaded | ✅ | ❌ Data uploaded | ❌ Data uploaded | ✅ | ❌ Data uploaded | ❌ Data uploaded | Mixed |
| **Open Source** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

### Why Musicify Studio

1. **End-to-End Pipeline.** Unlike Demucs and Moises (separation only), Melodyne (pitch editing only), or Transcribe! (practice/slow-down tool), Musicify Studio delivers the complete workflow — from raw audio to downloadable, publication-quality sheet music — in a single application.

2. **Instrument-Aware Transcription.** No other free tool offers 65+ instrument profiles with per-instrument range clamping, polyphony control, and melodic reduction strategies. Selecting "Trumpet" produces a monophonic top-line melody; selecting "Acoustic Bass" extracts the bottom-line. Klangio and Songscription.ai are largely piano-centric, while AnthemScore and ScoreCloud offer only basic instrument selection without range or polyphony intelligence.

3. **Zero Cost, Zero Cloud.** AnthemScore charges $39. Melodyne starts at €699. Smule, ScoreCloud, Klangio, Moises, Songscription.ai, and Soundslice all require subscriptions and upload user audio to external servers. Musicify Studio is free, open source, and processes everything on-device with no data ever leaving the machine.

4. **Integrated Vocal Separation.** By embedding Demucs directly into the transcription pipeline, Musicify Studio automatically removes vocals before note detection — a step that standalone transcription tools (AnthemScore, ScoreCloud, Klangio, Songscription.ai) require users to perform manually with separate software.

5. **Full Transparency.** As an open-source project, every algorithm is inspectable, modifiable, and extensible. Closed-source competitors provide no visibility into their transcription logic, making it impossible to debug, improve, or adapt their output for specific use cases.

---

## Known Limitations

- **Windows only** — macOS and Linux support is planned but not yet available.
- **Polyphonic density** — Transcription accuracy decreases with dense harmonic content (e.g., full orchestral mixes), as is the case with all current AMT systems.
- **PDF export** — Requires MuseScore 4 to be installed separately. All other outputs work without it.
- **Processing time** — Demucs stem separation on CPU can take 1–3 minutes for a typical 3-minute track. GPU acceleration (CUDA) significantly reduces this.

---

## Contributing

Contributions are welcome. To get started:

1. Fork this repository.
2. Create a feature branch: `git checkout -b feature/your-feature`.
3. Commit your changes: `git commit -m "Add your feature"`.
4. Push to the branch: `git push origin feature/your-feature`.
5. Open a Pull Request.

---

<p align="center">
  Built with ♪ by the Musicify team
</p>
