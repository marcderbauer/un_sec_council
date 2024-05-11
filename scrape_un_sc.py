from pathlib import Path
from bs4 import BeautifulSoup
from typing import Iterator
import pandas as pd
import re
import requests


BASE_URL = "https://www.securitycouncilreport.org/un_documents_type/security-council-meeting-records/page/"
FOLDER = "source"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
}
RE_DIGITAL_LIBRARY = "https:\/\/digitallibrary\.un\.org\/record.+"
RE_MISSING_FILE = "https?:\/\/daccess-ods\.un\.org\/tmp\/.+\.html"

import logging
import sys

logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

def setup_logging():
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Create a handler for stdout (console)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create a handler for file
    file_handler = logging.FileHandler('logfile.txt')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

def get_meetings(response) -> list[dict[str, str]]:
    soup = BeautifulSoup(response.content, "html.parser")
    meeting_rows = soup.find_all("tr")[1:]  # excluding header row

    meetings = []

    for row in meeting_rows:
        name = row.find("a").text
        date = row.find("span").text.strip()
        pdf_link = row.find("a")["href"]
        description = row.find("td", class_="description").text.strip()

        meetings.append(
            {
                "name": name,
                "name_sanitized": name.replace("/", "_"),
                "date": date,
                "pdf_link": pdf_link,
                "description": description,
            }
        )

    return meetings


def get_pdf_link_from_digital_library(meeting: dict[str, str]) -> str:
    link = meeting["pdf_link"]

    with requests.Session() as session:
        response = session.get(link, headers=HEADERS)

    if not response.status_code == 200:
        return False

    base_link = link.split("?")[0]
    file_link_part = f"/files/{meeting['name_sanitized']}-EN.pdf"

    pdf_link = base_link + file_link_part
    return pdf_link


def scrape_pdfs_from_un_security_council_page(
    url: str,
) -> Iterator[tuple[dict[str, str], bytes]]:
    response = requests.get(url, headers=HEADERS)

    if not response.status_code == 200:
        logger.error(
            f"Failed to retrieve data from the website. Status code {response.status_code}" +
            f"url: {url}"
        )
        return None

    meetings = get_meetings(response)

    for meeting_dict in meetings:
        meeting_link = meeting_dict["pdf_link"]

        if re.match(RE_MISSING_FILE, meeting_link):
            logger.warning(f"FILE MISSING - Failed to download {meeting_dict['name']}")
        elif re.match(RE_DIGITAL_LIBRARY, meeting_link):
            meeting_dict["pdf_link"] = get_pdf_link_from_digital_library(meeting_dict)
            logger.info(f"Replaced link for {meeting_dict['name']}") # TODO: don't use f-strings for logging

        with requests.Session() as session:
            try:
                pdf_response = session.get(meeting_dict["pdf_link"], headers=HEADERS)
            except Exception as e:
                logger.error(f"Error when querying pdf {meeting_dict['name']}")
                logger.error("Error: %s", e)
                continue

        if not pdf_response.status_code == 200:
            logger.warning(f"failed to query pdf {meeting_dict['name']}")
            continue

        logger.info(f"Successfully downloaded {meeting_dict['name']}")
        yield (meeting_dict, pdf_response.content)


def download_pdfs_from_un_security_council_page(url: str, folder: str) -> None:
    meeting_dicts = []
    for meeting_dict, pdf_in_bytes in scrape_pdfs_from_un_security_council_page(url):
        pdf_filename = Path(folder) / f"{meeting_dict['name_sanitized']}.pdf"

        with open(pdf_filename, "wb") as f:
            f.write(pdf_in_bytes)

        meeting_dicts.append(meeting_dict)

    return meeting_dicts


def main():
    meeting_dicts_all = []
    try:
        for i in range(1, 211):  # Everything within the last 25 years (as of 23.03.2024)
            logger.info(f"============PAGE {i}============")
            url = f"{BASE_URL}{i}"
            meeting_dicts_all += download_pdfs_from_un_security_council_page(
                url, FOLDER
            )
    except Exception as e:
        logger.error(e)
    finally:
        df = pd.DataFrame(meeting_dicts_all)
        df.to_csv("meetings.csv", sep="|", index=False)


# Example usage
if __name__ == "__main__":
    logger = setup_logging()
    main()

# TODO:
# Implement loading existing meetings.csv
# Create source folder if not exists using pathlib
