import subprocess
import requests


def fetch_and_run(url: str) -> None:
    response = requests.get(url)
    subprocess.run(response.text, shell=True)

