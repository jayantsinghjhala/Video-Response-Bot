import os
import sys
import uuid
import psutil
from dotenv import load_dotenv
from hugchat import hugchat
from hugchat.login import Login
import requests
import json
import urllib.request
from time import sleep

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
RAPID_TTS_API_KEY = os.getenv("RAPID_TTS_API_KEY")


def generate_unique_filename(directory, extension):
    unique_filename = f"{uuid.uuid4()}{extension}"
    return os.path.join(directory, unique_filename)


def clean_directory(directory):
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                for proc in psutil.process_iter(["open_files", "name"]):
                    try:
                        for open_file in proc.open_files():
                            if open_file.path == file_path:
                                print(
                                    f"File {file_path} is in use by {proc.name()}, skipping."
                                )
                                break
                        else:
                            continue
                        break
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        continue
                else:
                    os.unlink(file_path)
                    print(f"Deleted {file_path}")
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


def generate_response(prompt, email, password, max_token=150):
    try:
        sign = Login(email, password)
        cookies = sign.login(cookie_dir_path="./cookies/", save_cookies=True)
        chatbot = hugchat.ChatBot(cookies=cookies.get_dict())
        prompt = (
            prompt
            + " Answer this question as if you are USA's President Joe Biden, in less than 70 words, Don't salutate yourself while answering just direcltly answer."
        )
        response = chatbot.chat(prompt)
        return response.wait_until_done()
    except Exception as e:
        return f"An error occurred: {str(e)}"


def text_to_speech(
    text_prompt,
    api_key,
    tts_provider="OPEN_AI",
    openai_voice_name="onyx",
    openai_tts_model="tts_1",
):
    try:
        url = "https://api.gooey.ai/v3/TextToSpeech/async/form/"
        payload = {
            "functions": None,
            "variables": None,
            "text_prompt": text_prompt,
            "tts_provider": tts_provider,
            "openai_voice_name": openai_voice_name,
            "openai_tts_model": openai_tts_model,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        # Send the request to Gooey API
        response = requests.post(
            url, headers=headers, data={"json": json.dumps(payload)}
        )
        assert response.ok, response.content

        # Monitor the status of the request
        status_url = response.headers["Location"]
        while True:
            response = requests.get(
                status_url, headers={"Authorization": f"Bearer {api_key}"}
            )
            assert response.ok, response.content
            result = response.json()
            if result["status"] == "completed":
                print(response.status_code, result)
                break
            elif result["status"] == "failed":
                print(response.status_code, result)
                return None
            else:
                sleep(3)

        # Get the audio URL from the result and save the audio file
        audio_url = result["output"]["audio_url"]
        if audio_url:
            audio_directory = os.path.join(BASE_DIR, "audio")
            clean_directory(audio_directory)
            output_path = generate_unique_filename(audio_directory, ".mp3")
            audio_response = requests.get(audio_url)
            if audio_response.ok:
                with open(output_path, "wb") as f:
                    f.write(audio_response.content)
                print(f"Audio saved successfully at {output_path}")
                return output_path
            else:
                print(f"Failed to download audio: {audio_response.text}")
                return None
        else:
            print("No audio URL found in the response.")
            return None
    except Exception as e:
        print(f"Unexpected error in text_to_speech_gooey: {e}")
        return None


def lipsync_request(video_path, audio_path, api_key):
    files = [
        ("input_face", open(video_path, "rb")),
        ("input_audio", open(audio_path, "rb")),
    ]
    payload = {
        "functions": None,
        "variables": None,
        "face_padding_top": 0,
        "face_padding_bottom": 18,
        "face_padding_left": 0,
        "face_padding_right": 0,
        "sadtalker_settings": None,
        "selected_model": "Wav2Lip",
    }
    response = requests.post(
        "https://api.gooey.ai/v3/Lipsync/async/form/",
        headers={"Authorization": f"Bearer {api_key}"},
        files=files,
        data={"json": json.dumps(payload)},
    )
    response.raise_for_status()
    status_url = response.headers["Location"]

    while True:
        response = requests.get(
            status_url, headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        result = response.json()
        if result["status"] in ["completed", "failed"]:
            return result
        sleep(3)


def download_video(result):
    if result["status"] == "completed":
        video_url = result["output"]["output_video"]
        output_directory = os.path.join(BASE_DIR, "output")
        clean_directory(output_directory)
        output_path = generate_unique_filename(output_directory, ".mp4")

        urllib.request.urlretrieve(video_url, output_path)
        print(f"Video downloaded as {output_path}")
        return output_path
    else:
        print("Lipsync job failed")
        return None


import psutil
import nest_asyncio
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError, TimedOut

nest_asyncio.apply()


def get_script_name():
    try:
        return os.path.basename(__file__)
    except NameError:
        return "model.py"


def terminate_previous_instances(script_name):
    current_process = psutil.Process(os.getpid())
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] == current_process.pid:
            continue
        if (
            proc.info["name"] == current_process.name()
            and "python" in proc.info["cmdline"][0]
        ):
            if len(proc.info["cmdline"]) > 1 and proc.info["cmdline"][1].endswith(
                script_name
            ):
                proc.terminate()
                proc.wait()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! Now Mr. President will answer your questions."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Please Wait! Mr. President is Thinking, you can come back after 2 Minutes."
    )
    question = update.message.text
    ai_ans = generate_response(question, EMAIL, PASSWORD)

    api_key_gooey = os.getenv("GOOEY_API_KEY")
    audio_path = text_to_speech(ai_ans, api_key_gooey)
    if audio_path is None:
        await update.message.reply_text(
            "I apologize, but there was an issue generating the speech. Please try again later."
        )
        return

    video_path = os.path.join(BASE_DIR, "raw_vid", "Joe_Biden_HD_HEVC.mp4")

    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        await update.message.reply_text(
            "Interview Terminated! Mr. President is not Available Anymore."
        )
        return

    if not os.path.exists(audio_path):
        print(f"Audio file not found: {audio_path}")
        await update.message.reply_text(
            "Interview Terminated! Mr. President is not Available Anymore."
        )
        return

    job_response = lipsync_request(video_path, audio_path, api_key_gooey)
    output_video_path = download_video(job_response)

    if output_video_path and os.path.exists(output_video_path):
        try:
            with open(output_video_path, "rb") as video_file:
                await update.message.reply_video(video=video_file)
        except TimedOut:
            await update.message.reply_text(
                "Your Answer will be here Shortly. Thank Your For being Patience"
            )
        except TelegramError as e:
            await update.message.reply_text(f"An error occurred: {str(e)}")
        except Exception as e:
            await update.message.reply_text(f"An error occurred: {str(e)}")
    else:
        await update.message.reply_text(
            "I apologize, but there was an issue generating the video. Please try again later."
        )


async def main() -> None:
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.run_polling()


if __name__ == "__main__":
    script_name = get_script_name()
    terminate_previous_instances(script_name)
    try:
        asyncio.run(main())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(main())
