import os
import PySimpleGUI as sg
from pydub import AudioSegment
import pretty_midi
import numpy as np
from music21 import converter
import subprocess

# Functions as per your existing script
def midi_to_note_name(midi_number):
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = midi_number // 12 - 1
    note_name = note_names[midi_number % 12]
    return f"{note_name}{octave}"

def convert_to_midi(pitches, instrument_name, output_path):
    midi = pretty_midi.PrettyMIDI()
    instrument_program = pretty_midi.instrument_name_to_program(instrument_name)
    midi_instrument = pretty_midi.Instrument(program=instrument_program)

    for i in range(pitches.shape[1]):
        pitch = pitches[:, i]
        pitch = pitch[pitch > 0]

        if pitch.size > 0:
            note_number = int(round(pitch.mean()))
            note_number = max(0, min(127, note_number))
            start_time = i * 0.1
            end_time = start_time + 0.1
            note = pretty_midi.Note(velocity=100, pitch=note_number, start=start_time, end=end_time)
            midi_instrument.notes.append(note)

    midi.instruments.append(midi_instrument)
    midi_file_path = output_path + ".mid"
    midi.write(midi_file_path)
    return midi_file_path

def generate_sheet_music(midi_file, output_path):
    midi_stream = converter.parse(midi_file)
    layout = midi_stream.flatten()
    layout.makeMeasures()
    subprocess.run([r"C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe", midi_file, '-o', output_path], check=True)
    return output_path

def extract_features(audio_path):
    return np.random.randint(40, 80, (1, 100)), None

def process_audio(audio_path, instrument, output_dir):
    pitches, _ = extract_features(audio_path)
    base_name = f"{os.path.basename(audio_path).split('.')[0]}_{instrument}"
    output_path = os.path.join(output_dir, base_name)
    midi_path = convert_to_midi(pitches, instrument, output_path)
    return generate_sheet_music(midi_path, output_path=os.path.join(output_dir, f"{base_name}.pdf"))

def convert_mp3_to_wav(mp3_path):
    wav_path = mp3_path.replace(".mp3", ".wav")
    audio = AudioSegment.from_mp3(mp3_path)
    audio.export(wav_path, format="wav")
    return wav_path

# PySimpleGUI UI Setup
def create_window():
    sg.theme('DarkBlue')  # Apply blue theme

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

    layout = [
        [sg.Text('Musicify your Audio File', size=(30, 1), font=('Helvetica', 20), text_color='white', justification='center')],
        [sg.Text()],
        [sg.Text()],
        [sg.Text('Upload Audio File (.mp3):', size=(20, 1), font=('Helvetica', 12), justification='right'),
        sg.InputText('', key='-MP3_PATH-', size=(40, 1), font=('Helvetica', 12)),
        sg.FileBrowse(file_types=(('MP3 Files', '*.mp3'),), font=('Helvetica', 12))],

        [sg.Text('Select Instrument:', size=(20, 1), font=('Helvetica', 12), justification='right'),
        sg.Combo(instrument_list, default_value='(Select)', key='-INSTRUMENT-', font=('Helvetica', 12),
                size=(40, 1), auto_size_text=False, readonly=False)],

        [sg.Text('Select Output Folder:', size=(20, 1), font=('Helvetica', 12), justification='right'),
        sg.InputText('', key='-OUTPUT_PATH-', size=(40, 1), font=('Helvetica', 12)),
        sg.FolderBrowse(font=('Helvetica', 12))],
        [sg.Text()],

        [sg.Button('Submit', font=('Helvetica', 12)), sg.Button('Exit', font=('Helvetica', 12))]
    ]

    layout = [[sg.Column(layout, element_justification='center', justification='center', vertical_alignment='center')]]

    window = sg.Window('Musicify', layout, size=(700, 300), finalize=True)
    return window

def main():
    window = create_window()

    while True:
        event, values = window.read()

        if event == sg.WINDOW_CLOSED or event == 'Exit':
            break

        if event == 'Submit':
            audio_path = values['-MP3_PATH-']
            instrument = values['-INSTRUMENT-']
            output_dir = values['-OUTPUT_PATH-']

            if audio_path and instrument and output_dir:
                song_name = os.path.basename(audio_path).split('.')[0]
                project_folder = os.path.join(output_dir, f"{song_name}_Musicified")

                if not os.path.exists(project_folder):
                    os.makedirs(project_folder)

                wav_path = convert_mp3_to_wav(audio_path)
                sheet_music_file = process_audio(wav_path, instrument, project_folder)
                sg.popup(f"Conversion complete!!!\n\nMIDI and PDF files saved to {project_folder}\n\n", title="Success")

            else:
                sg.popup("Please provide all required inputs (MP3 file, instrument, output folder).", title="Failed")

    window.close()

if __name__ == "__main__":
    main()