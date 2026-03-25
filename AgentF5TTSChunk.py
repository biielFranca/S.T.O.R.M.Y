import os
import re
import time
import logging
import subprocess
from f5_tts.api import F5TTS 



logging.basicConfig(level=logging.INFO)


class AgentF5TTS:
    def __init__(self, ckpt_file, vocoder_name="vocos", delay=0, device="cpu"):
        self.model = F5TTS(ckpt_file=ckpt_file, device=device)
        self.delay = delay

    def generate_emotion_speech(self, text_file, output_audio_file, speaker_emotion_refs, convert_to_mp3=False):
        try:
            with open(text_file, "r", encoding="utf-8") as file:
                lines = [line.strip() for line in file if line.strip()]
        except FileNotFoundError:
            logging.error(f"Text file not found: {text_file}")
            return

        if not lines:
            logging.error("Input text file is empty.")
            return

        temp_files = []
        os.makedirs(os.path.dirname(output_audio_file), exist_ok=True)

        for i, line in enumerate(lines):
            speaker, emotion = self._determine_speaker_emotion(line)
            ref_audio = speaker_emotion_refs.get((speaker, emotion))
            line = re.sub(r'\[speaker:.*?\]\s*', '', line)
            if not ref_audio or not os.path.exists(ref_audio):
                logging.error(f"Reference audio not found for speaker '{speaker}', emotion '{emotion}'.")
                continue

            ref_text = ""
            temp_file = f"{output_audio_file}_line{i + 1}.wav"

            try:
                logging.info(f"Generating speech for line {i + 1}: '{line}' with speaker '{speaker}', emotion '{emotion}'")
                self.model.infer(
                    ref_file=ref_audio,
                    ref_text=ref_text,
                    gen_text=line,
                    file_wave=temp_file,
                    remove_silence=True,
                )
                temp_files.append(temp_file)
                time.sleep(self.delay)
            except Exception as e:
                logging.error(f"Error generating speech for line {i + 1}: {e}")

        self._combine_audio_files(temp_files, output_audio_file, convert_to_mp3)

    def generate_speech(self, text_file, output_audio_file, ref_audio, convert_to_mp3=False):
        try:
            with open(text_file, 'r', encoding='utf-8') as file:
                lines = [line.strip() for line in file if line.strip()]
        except FileNotFoundError:
            logging.error(f"Text file not found: {text_file}")
            return

        if not lines:
            logging.error("Input text file is empty.")
            return

        temp_files = []
        os.makedirs(os.path.dirname(output_audio_file), exist_ok=True)

        for i, line in enumerate(lines):
            if not ref_audio or not os.path.exists(ref_audio):
                logging.error(f"Reference audio not found for speaker.")
                continue
            temp_file = f"{output_audio_file}_line{i + 1}.wav"

            try:
                logging.info(f"Generating speech for line {i + 1}: '{line}'")
                self.model.infer(
                    ref_file=ref_audio,
                    ref_text="",
                    gen_text=line,
                    file_wave=temp_file,
                )
                temp_files.append(temp_file)
            except Exception as e:
                logging.error(f"Error generating speech for line {i + 1}: {e}")

        self._combine_audio_files(temp_files, output_audio_file, convert_to_mp3)

    def _determine_speaker_emotion(self, text):
        speaker, emotion = "speaker1", "neutral"
        match = re.search(r"\[speaker:(.*?), emotion:(.*?)\]", text)
        if match:
            speaker = match.group(1).strip()
            emotion = match.group(2).strip()
        logging.info(f"Determined speaker: '{speaker}', emotion: '{emotion}'")
        return speaker, emotion

    def _combine_audio_files(self, temp_files, output_audio_file, convert_to_mp3):
        if not temp_files:
            logging.error("No audio files to combine.")
            return

        list_file = "file_list.txt"
        with open(list_file, "w") as f:
            for temp in temp_files:
                f.write(f"file '{temp}'\n")

        try:
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_audio_file], check=True)
            if convert_to_mp3:
                mp3_output = output_audio_file.replace(".wav", ".mp3")
                subprocess.run(["ffmpeg", "-y", "-i", output_audio_file, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_output], check=True)
                logging.info(f"Converted to MP3: {mp3_output}")
            for temp in temp_files:
                os.remove(temp)
            os.remove(list_file)
        except Exception as e:
            logging.error(f"Error combining audio files: {e}")