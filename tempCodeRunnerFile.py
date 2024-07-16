import os
import uuid
import openai
import psutil
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Initialize the OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_unique_filename(directory, extension):
    unique_filename = f"{uuid.uuid4()}{extension}"
    return os.path.join(directory, unique_filename)


def clean_directory(directory):
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                # Check if the file is in use
                for proc in psutil.process_iter(['open_files', 'name']):
                    try:
                        for open_file in proc.open_files():
                            if open_file.path == file_path:
                                print(f"File {file_path} is in use by {proc.name()}, skipping.")
                                break
                        else:
                            continue
                        break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                else:
                    os.unlink(file_path)
                    print(f"Deleted {file_path}")
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')
