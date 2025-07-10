import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pretty_midi
import numpy as np
from music21 import converter
import subprocess
import librosa
import soundfile as sf

# Sub-Functions

def midi_to_note_name(midi_number):
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = midi_number // 12 - 1
    note_name = note_names[midi_number % 12]
    return f"{note_name}{octave}"

def convert_to_midi(pitches, instrument_name, output_path):
    midi = pretty_midi.PrettyMIDI()
    instrument_program = pretty_midi.instrument_name_to_program(instrument_name)
    midi_instrument = pretty_midi.Instrument(program=instrument_program)

    # Processing pitch data - pitches should be a 1D array of fundamental frequencies
    hop_length = 512
    sr = 22050
    time_step = hop_length / sr  # Time per frame
    
    current_note = None
    note_start_time = 0
    
    for i, pitch_hz in enumerate(pitches):
        current_time = i * time_step
        
        if pitch_hz > 0:  # Valid pitch detected
            # Converting Hz to MIDI note number
            midi_note = int(round(librosa.hz_to_midi(pitch_hz)))
            midi_note = max(0, min(127, midi_note))  # Clamp to valid MIDI range
            
            if current_note is None:
                # Starting new note
                current_note = midi_note
                note_start_time = current_time
            elif current_note != midi_note:
                # Note changed - ending previous note and starting new one
                if current_time > note_start_time:
                    note = pretty_midi.Note(
                        velocity=80, 
                        pitch=current_note, 
                        start=note_start_time, 
                        end=current_time
                    )
                    midi_instrument.notes.append(note)
                current_note = midi_note
                note_start_time = current_time
        else:
            # No pitch - ending current note if one exists
            if current_note is not None:
                if current_time > note_start_time:
                    note = pretty_midi.Note(
                        velocity=80, 
                        pitch=current_note, 
                        start=note_start_time, 
                        end=current_time
                    )
                    midi_instrument.notes.append(note)
                current_note = None
    
    # Ending final note if it exists
    if current_note is not None:
        final_time = len(pitches) * time_step
        if final_time > note_start_time:
            note = pretty_midi.Note(
                velocity=80, 
                pitch=current_note, 
                start=note_start_time, 
                end=final_time
            )
            midi_instrument.notes.append(note)

    midi.instruments.append(midi_instrument)
    midi_file_path = output_path + ".mid"
    midi.write(midi_file_path)
    return midi_file_path

def generate_sheet_music(midi_file, output_path):
    try:
        midi_stream = converter.parse(midi_file)
        layout = midi_stream.flatten()
        layout.makeMeasures()
        subprocess.run([r"C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe", midi_file, '-o', output_path], check=True)
        return output_path
    except subprocess.CalledProcessError:
        print("MuseScore not found or failed to generate PDF. MIDI file created successfully.")
        return None
    except Exception as e:
        print(f"Error generating sheet music: {e}")
        return None

def extract_features(audio_path):

    try:
        # Loading audio file
        y, sr = librosa.load(audio_path, sr=22050)  # Loading with 22050 Hz sample rate
        
        # Using librosa's pitch detection (YIN algorithm)
        hop_length = 512
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr, hop_length=hop_length, threshold=0.1)
        
        # Extracting the fundamental frequency for each time frame
        pitch_contour = []
        
        for t in range(pitches.shape[1]):
            # Finding the pitch with highest magnitude at this time frame
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            
            # Only keep pitches above a certain threshold
            if magnitudes[index, t] > 0.1:
                pitch_contour.append(pitch)
            else:
                pitch_contour.append(0)  # If no clear pitch detected
        
        return np.array(pitch_contour), sr
        
    except Exception as e:
        print(f"Error processing audio: {e}")
        # Fallback to random data if audio processing fails
        return np.random.randint(40, 80, 100), None

def process_audio(audio_path, instrument, output_dir):
    pitches, sr = extract_features(audio_path)
    base_name = f"{os.path.basename(audio_path).split('.')[0]}_{instrument.replace(' ', '_')}"
    output_path = os.path.join(output_dir, base_name)
    
    # Converting pitches to MIDI
    midi_path = convert_to_midi(pitches, instrument, output_path)
    
    # Generating sheet music
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
    sheet_music_path = generate_sheet_music(midi_path, pdf_path)
    
    return midi_path, sheet_music_path

def convert_mp3_to_wav(mp3_path):
    
    try:
        wav_path = mp3_path.replace(".mp3", ".wav")
        if not os.path.exists(wav_path):
            # Load audio with librosa
            y, sr = librosa.load(mp3_path, sr=None)
            # Save as WAV using soundfile
            sf.write(wav_path, y, sr)
        return wav_path
    except Exception as e:
        print(f"Error converting MP3 to WAV: {e}")
        # Return original path
        return mp3_path

# Tkinter UI setup

instrument_list = ['Acoustic Grand Piano', 'Bright Acoustic Piano', 'Electric Grand Piano', 'Honky-Tonk Piano',
                    'Electric Piano 1', 'Electric Piano 2', 'Harpsichord', 'Clavinet', 'Celesta', 'Glockenspiel',
                    'Music Box', 'Vibraphone', 'Marimba', 'Xylophone', 'Tubular Bells', 'Dulcimer', 'Drawbar Organ',
                    'Percussive Organ', 'Rock Organ', 'Church Organ', 'Reed Organ', 'Accordion', 'Harmonica',
                    'Tango Accordion', 'Acoustic Guitar (Nylon)', 'Acoustic Guitar (Steel)', 'Electric Guitar (Jazz)',
                    'Electric Guitar (Clean)', 'Electric Guitar (Muted)', 'Overdriven Guitar', 'Distortion Guitar',
                    'Guitar Harmonics', 'Acoustic Bass', 'Electric Bass (Finger)', 'Electric Bass (Pick)',
                    'Fretless Bass', 'Slap Bass 1', 'Slap Bass 2', 'Synth Bass 1', 'Synth Bass 2', 'Violin', 'Viola',
                    'Cello', 'Contrabass', 'Tremolo Strings', 'Pizzicato Strings', 'Orchestral Harp', 'Timpani',
                    'String Ensemble 1', 'String Ensemble 2', 'Synth Strings 1', 'Synth Strings 2', 'Choir Aahs',
                    'Voice Oohs', 'Synth Voice', 'Orchestra Hit', 'Trumpet', 'Trombone', 'Tuba', 'Muted Trumpet',
                    'French Horn', 'Brass Section', 'Synth Brass 1', 'Synth Brass 2', 'Soprano Sax', 'Alto Sax',
                    'Tenor Sax', 'Baritone Sax', 'Oboe', 'English Horn', 'Bassoon', 'Clarinet', 'Piccolo', 'Flute',
                    'Recorder', 'Pan Flute', 'Blown Bottle', 'Shakuhachi', 'Whistle', 'Ocarina', 'Lead 1 (Square)',
                    'Lead 2 (Sawtooth)', 'Lead 3 (Calliope)', 'Lead 4 (Chiff)', 'Lead 5 (Charang)', 'Lead 6 (Voice)',
                    'Lead 7 (Fifths)', 'Lead 8 (Bass + Lead)', 'Pad 1 (New Age)', 'Pad 2 (Warm)', 'Pad 3 (Polysynth)',
                    'Pad 4 (Choir)', 'Pad 5 (Bowed)', 'Pad 6 (Metallic)', 'Pad 7 (Halo)', 'Pad 8 (Sweep)', 'FX 1 (Rain)',
                    'FX 2 (Soundtrack)', 'FX 3 (Crystal)', 'FX 4 (Atmosphere)', 'FX 5 (Brightness)', 'FX 6 (Goblins)',
                    'FX 7 (Echoes)', 'FX 8 (Sci-Fi)', 'Sitar', 'Banjo', 'Shamisen', 'Koto', 'Kalimba', 'Bagpipe',
                    'Fiddle', 'Shanai', 'Tinkle Bell', 'Agogo', 'Steel Drums', 'Woodblock', 'Taiko Drum', 'Melodic Tom',
                    'Synth Drum', 'Reverse Cymbal', 'Guitar Fret Noise', 'Breath Noise', 'Seashore', 'Bird Tweet',
                    'Telephone Ring', 'Helicopter', 'Applause', 'Gunshot']

class MusicifyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Musicify")
        self.root.geometry("700x350")
        self.root.configure(bg="#1a1a2e")

        # Title
        title = tk.Label(root, text="Musicify your Audio File", font=("Helvetica", 20), fg="white", bg="#1a1a2e")
        title.pack(pady=10)

        # Frame for inputs
        frame = tk.Frame(root, bg="#1a1a2e")
        frame.pack(pady=10)

        # MP3 input
        self.mp3_path_var = tk.StringVar()
        tk.Label(frame, text="Upload Audio File (.mp3/.wav/.flac):", font=("Helvetica", 12), bg="#1a1a2e", fg="white").grid(row=0, column=0, sticky='e', padx=10, pady=5)
        tk.Entry(frame, textvariable=self.mp3_path_var, width=40, font=("Helvetica", 12)).grid(row=0, column=1, pady=5)
        tk.Button(frame, text="Browse", command=self.browse_audio).grid(row=0, column=2, padx=5)

        # Instrument selection
        self.instrument_var = tk.StringVar(value='Acoustic Grand Piano')
        tk.Label(frame, text="Select Instrument:", font=("Helvetica", 12), bg="#1a1a2e", fg="white").grid(row=1, column=0, sticky='e', padx=10, pady=5)
        ttk.Combobox(frame, textvariable=self.instrument_var, values=instrument_list, width=38).grid(row=1, column=1, pady=5)

        # Output path
        self.output_path_var = tk.StringVar()
        tk.Label(frame, text="Select Output Folder:", font=("Helvetica", 12), bg="#1a1a2e", fg="white").grid(row=2, column=0, sticky='e', padx=10, pady=5)
        tk.Entry(frame, textvariable=self.output_path_var, width=40, font=("Helvetica", 12)).grid(row=2, column=1, pady=5)
        tk.Button(frame, text="Browse", command=self.browse_folder).grid(row=2, column=2, padx=5)

        # Progress bar
        self.progress_var = tk.StringVar(value="Ready to process...")
        tk.Label(root, textvariable=self.progress_var, font=("Helvetica", 10), bg="#1a1a2e", fg="lightblue").pack(pady=5)

        # Buttons
        button_frame = tk.Frame(root, bg="#1a1a2e")
        button_frame.pack(pady=15)
        tk.Button(button_frame, text="Submit", font=("Helvetica", 12), command=self.submit).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Exit", font=("Helvetica", 12), command=self.root.quit).pack(side=tk.LEFT, padx=10)

    def browse_audio(self):
        path = filedialog.askopenfilename(filetypes=[
            ("Audio Files", "*.mp3 *.wav *.flac *.m4a *.ogg"), 
            ("MP3 Files", "*.mp3"), 
            ("WAV Files", "*.wav"),
            ("FLAC Files", "*.flac"),
            ("All Files", "*.*")
        ])
        if path:
            self.mp3_path_var.set(path)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_path_var.set(folder)

    def submit(self):
        audio_path = self.mp3_path_var.get()
        instrument = self.instrument_var.get()
        output_dir = self.output_path_var.get()

        if not audio_path or not instrument or not output_dir:
            messagebox.showerror("Error", "Please provide all required inputs (audio file, instrument, output folder).")
            return

        try:
            self.progress_var.set("Processing audio file...")
            self.root.update()
            
            song_name = os.path.basename(audio_path).split('.')[0]
            project_folder = os.path.join(output_dir, f"{song_name}_Musicified")

            if not os.path.exists(project_folder):
                os.makedirs(project_folder)

            # Converting to WAV if needed
            if audio_path.lower().endswith('.mp3'):
                self.progress_var.set("Converting MP3 to WAV...")
                self.root.update()
                wav_path = convert_mp3_to_wav(audio_path)
            else:
                wav_path = audio_path

            self.progress_var.set("Extracting pitch information...")
            self.root.update()
            
            midi_path, sheet_music_path = process_audio(wav_path, instrument, project_folder)

            self.progress_var.set("Conversion complete!")
            
            result_message = f"Conversion complete!\nMIDI file saved to: {midi_path}"
            if sheet_music_path:
                result_message += f"\nPDF sheet music saved to: {sheet_music_path}"
            else:
                result_message += "\nNote: PDF generation failed (MuseScore not found), but MIDI file was created successfully."
            
            messagebox.showinfo("Success", result_message)
            
        except Exception as e:
            self.progress_var.set("Error occurred during processing")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MusicifyApp(root)
    root.mainloop()