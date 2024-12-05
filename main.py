import os
import re
import shutil
import subprocess
import zipfile

from videolingo.core import (
    step2_whisperX,
    step3_1_spacy_split,
    step3_2_splitbymeaning,
    step4_1_summarize,
    step4_2_translate_all,
    step5_splitforsub,
    step6_generate_final_timeline,
)
from videolingo.core.config_utils import load_key
from videolingo.core.onekeycleanup import cleanup
from videolingo.core.step1_ytdlp import download_video_ytdlp, find_video_files

SUB_VIDEO = "output/output_sub.mp4"


def prepare_video():
    """
    Command-line interface for downloading or uploading videos.
    """
    # Handle the output folder
    if os.path.exists("output"):
        print("Existing 'output' folder found. Do you want to delete it? (y/n)")
        user_choice = input().strip().lower()
        if user_choice == "y":
            shutil.rmtree("output")
            print("'output' folder deleted.")
        else:
            print("Continuing with the existing 'output' folder.")
    else:
        os.makedirs("output", exist_ok=True)

    try:
        # Check if a unique video file exists in the 'output' folder
        video_file = find_video_files()
        print(f"Found video: {video_file}")
        print("Options:")
        print("1. Delete and reselect video")
        print("2. Use existing video")
        choice = input("Enter your choice (1/2): ").strip()
        if choice == "1":
            os.remove(video_file)
            shutil.rmtree("output")
            os.makedirs("output", exist_ok=True)
            print("Previous video deleted. You can now reselect.")
            return prepare_video()
        else:
            print(f"Using existing video: {video_file}")
            return video_file
    except ValueError as e:
        print(f"Error: {e}")
        print("Proceeding to download or upload a video.")

    print("Choose an action:")
    print("1. Download a video from YouTube")
    print("2. Upload a video or audio file from your disk")
    action = input("Enter 1 or 2: ").strip()

    if action == "1":
        # YouTube video download
        url = input("Enter YouTube link: ").strip()
        res_dict = {"360p": "360", "1080p": "1080", "Best": "best"}
        print("Choose resolution:")
        for i, key in enumerate(res_dict.keys(), start=1):
            print(f"{i}. {key}")
        try:
            res_choice = int(input("Enter the number for the desired resolution: ").strip())
            res = list(res_dict.values())[res_choice - 1]
        except (IndexError, ValueError):
            print("Invalid choice. Defaulting to 'best' resolution.")
            res = "best"

        print("Downloading video...")
        download_video_ytdlp(url, resolution=res)
        print("Download completed. Video saved in the 'output' folder.")
    elif action == "2":
        # File upload
        file_path = input("Enter the full path of the video or audio file: ").strip()
        if not os.path.isfile(file_path):
            print("Invalid file path. Please try again.")
            return

        raw_name = os.path.basename(file_path).replace(" ", "_")
        name, ext = os.path.splitext(raw_name)
        clean_name = re.sub(r"[^\w\-_\.]", "", name) + ext.lower()

        dest_path = os.path.join("output", clean_name)
        if os.path.exists(dest_path):
            print(f"File '{clean_name}' already exists in the output folder.")
            overwrite = input("Do you want to overwrite it? (y/n): ").strip().lower()
            if overwrite != "y":
                print("Upload skipped. Retaining the existing file.")
                return

        shutil.copy2(file_path, dest_path)
        print(f"File uploaded and saved as {clean_name} in the 'output' folder.")

        # Check if the file is an audio file
        if clean_name.split(".")[-1] in load_key("allowed_audio_formats"):
            convert_audio_to_video(dest_path)
            print("Audio file converted to video.")
    else:
        print("Invalid action. Please try again.")


def convert_audio_to_video(audio_file: str) -> str:
    output_video = "output/black_screen.mp4"
    if not os.path.exists(output_video):
        print(f"🎵➡️🎬 Converting audio <{audio_file}> to video with FFmpeg ......")
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360",
            "-i",
            audio_file,
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            output_video,
        ]
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, encoding="utf-8")
        print(f"🎵➡️🎬 Converted <{audio_file}> to <{output_video}> with FFmpeg\n")
        # delete audio file
        os.remove(audio_file)
    return output_video


def create_subtitle_zip(output_dir="output", zip_file_name="subtitles.zip"):
    """
    Creates a zip file containing all .srt subtitle files in the output directory.

    Args:
        output_dir (str): Directory containing the subtitle files.
        zip_file_name (str): Name of the zip file to create.

    Returns:
        str: Path to the created zip file.
    """
    zip_path = os.path.join(output_dir, zip_file_name)
    with zipfile.ZipFile(zip_path, "w") as zip_file:
        for file_name in os.listdir(output_dir):
            if file_name.endswith(".srt"):
                file_path = os.path.join(output_dir, file_name)
                zip_file.write(file_path, arcname=file_name)
    return zip_path


def text_processing():
    """
    Command-line interface for the text processing section.
    """
    print("==== Translate and Generate Subtitles ====")
    print(
        """
        This stage includes the following steps:
        1. WhisperX word-level transcription
        2. Sentence segmentation using NLP and LLM
        3. Summarization and multi-step translation
        4. Cutting and aligning long subtitles
        5. Generating timeline and subtitles
        6. Merging subtitles into the video
        """
    )

    # Check if the subtitle video already exists
    if not os.path.exists(SUB_VIDEO):
        user_choice = input("Start processing subtitles? (y/n): ").strip().lower()
        if user_choice == "y":
            process_text()
        else:
            print("Skipping text processing.")
    else:
        # Display information about the generated subtitle video
        print(f"Subtitle video already exists: {SUB_VIDEO}")
        resolution = load_key("resolution")
        if resolution != "0x0":
            print(f"Generated subtitle video available at: {SUB_VIDEO}")

        # Provide an option to download subtitle files
        print("Do you want to create a zip file for the subtitles? (y/n)")
        zip_choice = input().strip().lower()
        if zip_choice == "y":
            zip_path = create_subtitle_zip()
            print(f"Subtitles zipped successfully: {zip_path}")

        # Option to archive and clean up
        user_choice = input("Archive and clean up the 'output' folder? (y/n): ").strip().lower()
        if user_choice == "y":
            cleanup()
            print("'output' folder archived and cleaned up.")
        else:
            print("Output folder remains unchanged.")


def process_text():
    """
    Core text processing pipeline with detailed status messages.
    """
    print("Starting transcription with WhisperX...")
    step2_whisperX.transcribe()
    print("Transcription completed.")

    print("Splitting long sentences using NLP...")
    step3_1_spacy_split.split_by_spacy()
    step3_2_splitbymeaning.split_sentences_by_meaning()
    print("Sentence segmentation completed.")

    print("Summarizing and translating...")
    step4_1_summarize.get_summary()
    if load_key("pause_before_translate"):
        input(
            "⚠️ PAUSE_BEFORE_TRANSLATE is enabled. Go to `output/log/terminology.json` to edit terminology. Press ENTER to continue after editing..."
        )
    step4_2_translate_all.translate_all()
    print("Summarization and translation completed.")

    print("Processing and aligning subtitles...")
    step5_splitforsub.split_for_sub_main()
    step6_generate_final_timeline.align_timestamp_main()
    print("Subtitles processing and alignment completed.")


def main():
    prepare_video()
    text_processing()


if __name__ == "__main__":
    main()
