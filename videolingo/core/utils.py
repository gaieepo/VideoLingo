import os
import re
import shutil

from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from videolingo.core.all_tts_functions.estimate_duration import estimate_duration, init_estimator
from videolingo.core.ask_gpt import ask_gpt
from videolingo.core.config_utils import load_key
from videolingo.core.prompts_storage import get_subtitle_trim_prompt

console = Console()
speed_factor = load_key("speed_factor")

TRANS_SUBS_FOR_AUDIO_FILE = "output/audio/trans_subs_for_audio.srt"
SRC_SUBS_FOR_AUDIO_FILE = "output/audio/src_subs_for_audio.srt"
SOVITS_TASKS_FILE = "output/audio/tts_tasks.xlsx"
ESTIMATOR = None


def check_len_then_trim(text, duration):
    global ESTIMATOR
    if ESTIMATOR is None:
        ESTIMATOR = init_estimator()
    estimated_duration = estimate_duration(text, ESTIMATOR) / speed_factor["max"]

    console.print(
        f"Subtitle text: {text}, "
        f"[bold green]Estimated reading duration: {estimated_duration:.2f} seconds[/bold green]"
    )

    if estimated_duration > duration:
        rprint(
            Panel(
                f"Estimated reading duration {estimated_duration:.2f} seconds exceeds given duration {duration:.2f} seconds, shortening...",
                title="Processing",
                border_style="yellow",
            )
        )
        original_text = text
        prompt = get_subtitle_trim_prompt(text, duration)

        def valid_trim(response):
            if "result" not in response:
                return {"status": "error", "message": "No result in response"}
            return {"status": "success", "message": ""}

        try:
            response = ask_gpt(prompt, response_json=True, log_title="subtitle_trim", valid_def=valid_trim)
            shortened_text = response["result"]
        except Exception:
            rprint("[bold red]🚫 AI refused to answer due to sensitivity, so manually remove punctuation[/bold red]")
            shortened_text = re.sub(r"[,.!?;:，。！？；：]", " ", text).strip()
        rprint(
            Panel(
                f"Subtitle before shortening: {original_text}\nSubtitle after shortening: {shortened_text}",
                title="Subtitle Shortening Result",
                border_style="green",
            )
        )
        return shortened_text
    else:
        return text


def delete_dubbing_files():
    files_to_delete = [os.path.join("output", "dub.wav"), os.path.join("output", "output_dub.mp4")]

    for file_path in files_to_delete:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Deleted: {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {str(e)}")
        else:
            print(f"File not found: {file_path}")

    segs_folder = os.path.join("output", "audio", "segs")
    if os.path.exists(segs_folder):
        try:
            shutil.rmtree(segs_folder)
            print(f"Deleted folder and contents: {segs_folder}")
        except Exception as e:
            print(f"Error deleting folder {segs_folder}: {str(e)}")
    else:
        print(f"Folder not found: {segs_folder}")


if __name__ == "__main__":
    delete_dubbing_files()
