from datetime import datetime
import json
from pathlib import Path
import re
import fitz
from multi_column import get_pages
from io_utils import get_files_from_folder

country_uk_gb_ni = "United Kingdom of Great Britain\nand Northern Ireland"

def _str_contains_binary(text: str) -> bool:
    return bool(re.search(r"(\\x\d{2}){2,}", text))

def get_time_str(text: str) -> str:
    # ! NOT USED YET, NEEDS TO BE CALLED IN GET_METADATA
    re_day = r"(?P<day>\d{1,2})"
    re_month = r"(?P<month>(\w+))"
    re_year = r"(?P<year>\d{4})"
    re_hour = r"(?P<hour>\d{1,2})"
    re_minute = r"(?P<minute>\d{1,2})"
    re_daytime = r"(?P<daytime>a|p)"

    time_regex = re.compile(
        f"{re_day} {re_month} {re_year}(, {re_hour}\.?{re_minute} {re_daytime})?"
    )

    match = re.search(time_regex, text)

    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    day = int(match.group("day"))
    month_str = match.group("month")
    month = months.index(month_str) + 1
    year = int(match.group("year"))

    if match.group("hour"):
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        if match.group("daytime") == "p":
            hour += 12
    else:
        hour = 0
        minute = 0

    time = datetime(year, month, day, hour, minute)

    return str(time)


def replace_newlines(text: str) -> str:
    return re.sub("\s+", " ", text)


def _is_communique_of_closed_meeting(page_zero) -> bool:
    text = " ".join(page_zero)
    if re.search("Official communiqu[ée]", text, re.I):
        return True
    return False

def _get_metadata_substring_indices(text: str) -> dict[str, tuple[int, int]]:
    metadata_to_regex = {
        "president": r"President:(\n)?",
        "members": r"Members:(\n)?",
        "agenda": r"Agenda(\n)?",
        "disclaimer": "This record .+",
    }

    matches = {}
    for name, regex in metadata_to_regex.items():
        matches[name] = re.search(regex, text)
    
    matches_indices = {}
    matches_indices["header"] = (0, matches["president"].start())
    matches_indices["president"] = (matches["president"].end(), matches["members"].start())
    matches_indices["members"] = (matches["members"].end(), matches["agenda"].start())
    matches_indices["agenda"] = (matches["agenda"].end(), matches["disclaimer"].start())
    return matches_indices
    

def extract_metadata(first_page: dict[int, str]) -> dict[str, str]:
    text = "\n".join(first_page)
    # text = text.replace(
    #     "United Kingdom of Great Britain\nand Northern Ireland",
    #     "United Kingdom of Great Britain and Northern Ireland",
    # )
    text = text.replace(" \n", "\n")
    # ! Note: Can extract more info from here still
    speaker_to_country = {}

    substring_indices = _get_metadata_substring_indices(text)

    # Duplicates from below. Would be nice to have those in one place
    # This will be the more up to date version of the two
    regex_meeting_number = r"(?P<Meeting_Nr>\d{1,4})(st|nd|rd|th) [Mm]eeting"
    title = r"(?P<Title>((Mr|Mr|Ms|Mrs).|Dame|Miss|Sir))"
    person = r"(?P<Person>([A-Za-zÀ-ȕ-]+)( [A-Za-zÀ-ȕ-]+)*)"
    country = fr"(?P<Country>[A-Za-zÀ-ȕ-\ ’()]+|{country_uk_gb_ni})"
    aligner = r"( .)+ ?"
    person_with_title = f"{title} ?{person}"

    
    # Other metadata:
    header_text = text[substring_indices["header"][0]: substring_indices["header"][1]]
    meeting_number_match = re.search(regex_meeting_number, header_text)
    meeting_number = meeting_number_match.group("Meeting_Nr")

    # President:
    president_text = text[substring_indices["president"][0]: substring_indices["president"][1]]
    president_match = re.search(person_with_title, president_text)
    president = president_match.group(0)
    president_country_match = re.search(f"\({country}\)", president_text)
    president_country = president_country_match.group("Country")

    speaker_to_country["The President"] = president_country

    # Members:
    members_text = text[substring_indices["members"][0]: substring_indices["members"][1]]
    members_regex = f"{country}{aligner}\n?{person_with_title}"
    for match in re.finditer(members_regex, members_text):
        speaker_country = match.group("Country").strip()
        speaker_name = match.group("Title") + " "+ match.group("Person")
        speaker_to_country[speaker_name] = speaker_country

    # Agenda:
    # ! Probably the entire agenda_text
    agenda_text = text[substring_indices["agenda"][0]: substring_indices["agenda"][1]]
    agenda_match = re.search("((.|\n)+)($|\n)", agenda_text)
    agenda = agenda_match.group(1)


    metadata = {
        "agenda": agenda,
        "meeting_number": meeting_number,
        "members": speaker_to_country,
        "president": (president, president_country),
    }

    return metadata


def extract_metadata_old(first_page: dict[int, str]) -> dict[str, str]:
    text = "\n".join(first_page)
    text = text.replace(
        "United Kingdom of Great Britain\nand Northern Ireland",
        "United Kingdom of Great Britain and Northern Ireland",
    )
    text = text.replace(" \n", "\n")
    # ! Note: Can extract more info from here still
    speaker_to_country = (
        {}
    )  # Not comprehensive, can have unlisted speakers such as Mr. Wennesland at S/PV.9556

    regex_meeting_number = "(\d{1,4})(st|nd|rd|th) [Mm]eeting"
    regex_president = "President:(\n)?"
    regex_members = "Members:(\\n)?"
    regex_agenda = "Agenda(\\n)?"
    regex_disclaimer = "This record .+"
    regex_person_and_country = "(?P<Title>Mr?s?\.|Dame|Miss|Sir) (?P<Person>([A-Za-zÀ-ȕ-]+)( [A-Za-zÀ-ȕ-]+)*)(\\n)(?P<Country>[A-Za-zÀ-ȕ ]+)"

    meeting_number = re.search(regex_meeting_number, text).group(1)

    # TODO: Separate getting indices from actual matching in text
    # TODO: Move all the regexes out of the code below
    meta_str_index = re.search(regex_president, text).start()
    meta_text = text[:meta_str_index]

    president_str_index = re.search(regex_members, text).start()
    president_text = text[meta_str_index:president_str_index]
    president_match = re.search(
        "(?<=President:\n)(?P<Title>Mr?s?\.|Dame|Miss|Sir) ?(?P<Person>([A-Za-zÀ-ȕ-]+)( [A-Za-zÀ-ȕ-]+)*)",
        president_text,
    )
    president = president_match.group("Title") + " " + president_match.group("Person")
    president_country = (
        re.search("\(([A-Za-zÀ-ȕ- ]+)\)", president_text).group(1).strip()
    )

    members_str_index = re.search(regex_agenda, text).start()
    members_text = text[president_str_index:members_str_index]

    agenda_str_index = re.search(regex_disclaimer, text).start()
    agenda_text = text[members_str_index:agenda_str_index]
    agenda = re.search("(?<=Agenda\n)((.|\n)+)($|\n)", agenda_text).group(1)

    for match in re.finditer(regex_person_and_country, members_text):
        speaker = match.group("Title") + " " + match.group("Person")
        speaker_to_country[speaker] = match.group("Country").strip()

    speaker_to_country["The President"] = president_country

    metadata = {
        "agenda": agenda,
        "meeting_number": meeting_number,
        "members": speaker_to_country,
        "president": (president, president_country),
    }

    return metadata


def get_text_indices_with_speakers(matches, text) -> list[tuple[str, str, str]]:
    matches = list(matches)

    if not matches:
        return []

    text_indices_with_speakers = []
    text_indices_with_speakers.append((0, matches[0].start(), "Intro"))

    for match_index, match in enumerate(matches):
        # + 1 to offset space after. Could bake into regex
        text_start = match.end() + 1

        if match_index + 1 < len(matches):
            text_end = matches[match_index + 1].start()
        else:
            text_end = len(text)

        # Can be done more nicely
        name = match[0].replace("\n", "")
        name = name.replace(":", "")

        text_indices_with_speakers.append((text_start, text_end, name))

    return text_indices_with_speakers


def split_text_by_speakers(text: str) -> list[dict[str, str]]:
    title = r"(?P<Title>((Mr|Mr|Ms|Mrs).|Dame|Miss|Sir))"
    person = r"(?P<Person>([A-Za-zÀ-ȕ-]+)( [A-Za-zÀ-ȕ-]+)*)"
    country = r"(?P<Country>\([A-Za-zÀ-ȕ\ ]+\))" # surrounded by brackets
    language = r"(?P<Language>\(spoke in [A-Za-zÀ-ȕ\ ]+\))"

    speaker_regex = f"\n?(({title} ?{person} ?{country}?|The President) ?{language}?):"
    matches = re.finditer(speaker_regex, text)

    text_indices_with_speakers = get_text_indices_with_speakers(matches, text)
    parts = []

    for start, end, speaker in text_indices_with_speakers:
        part = text[start:end]
        part = part.strip()

        parts.append({"speaker": speaker, "text": replace_newlines(part)})

        # print(part)
        # print("\n-------------\n")

    return parts


def get_pdf_type(title: str, first_page: list[str]) -> str:
    if re.search("Corr", title):
        return "correction"

    if re.search("Resumption", title):
        return "resumption"

    if re.search(r"S_\d{4}_\d+", title):
        return "letter"

    if re.search("Agenda", title):
        return "agenda"

    if _is_communique_of_closed_meeting(first_page):
        return "communique"

    return "transcript"


def process_doc(doc) -> dict:
    pages = get_pages(doc)

    pdf_type = get_pdf_type(doc.name, pages[0])

    if not pages[0]:
        print(f"Failed to extract {doc.name}")
        return {}
    
    if pages[0][0] and _str_contains_binary(pages[0][0]):
        print(f"{doc.name} contains binary str")
        return {}

    if pdf_type in ["transcript", "resumption"]:
        # TODO: Make metadata extraction dependent on PDF type
        metadata = extract_metadata(pages[0])

        # TODO: Extract text cleaning (newlines, etc.) into own function and apply to text_full as well...
        text_full = "".join(["".join(page) for page in pages[1:]])
        parts = split_text_by_speakers(text_full)

        report_dict = {
            "type": pdf_type,
            **metadata,
            "by_speaker": parts,
            "text": replace_newlines(text_full),
        }
    else:
        report_dict = {"type": pdf_type}

    return report_dict


if __name__ == "__main__":
    files = get_files_from_folder("source")
    # files = ["S_PV.9533.pdf"]
    extracted_folder = Path("extracted")

    for filename in files:
        doc = fitz.open(f"source/{filename}")

        report_dict = process_doc(doc)
        output_path = extracted_folder / f"{str(Path(filename).stem)}{'.json'}"
        print(output_path)

        with open(output_path, "w") as f:
            dump = json.dumps(report_dict, indent=4, ensure_ascii=False).encode("utf-8")
            f.write(dump.decode())

# TODO: Want some mechanism for combining text correctly.
# Might want to join with a space and then squash extra spaces with \s+ replacement
