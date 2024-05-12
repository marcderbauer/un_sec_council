import json
from pathlib import Path
import re
import fitz
from multi_column import get_pages
from io_utils import get_files_from_folder


def replace_newlines(text: str) -> str:
    return re.sub("\s+", " ", text)


def _is_communique_of_closed_meeting(page_zero) -> bool:
    text = " ".join(page_zero)
    if re.search("Official communiqué of the \d+\w+ \(closed\) meeting", text):
        return True
    return False


def extract_metadata(first_page: dict[int, str]) -> dict[str, str]:
    text = "\n".join(first_page)

    # ! Note: Can extract more info from here still
    speaker_to_country = (
        {}
    )  # Not comprehensive, can have unlisted speakers such as Mr. Wennesland at S/PV.9556
    # text = first_page[2]

    regex_meeting_number = "(\d{1,4})(st|rd|th) meeting"
    regex_president = "President:(\n)?"
    regex_members = "Members:(\\n)?"
    regex_agenda = "Agenda(\\n)?"
    regex_disclaimer = "This record .+"
    regex_person_and_country = "(?P<Title>Mrs?\.|Dame) (?P<Person>[A-Za-zÀ-ȕ ]+)(\\n)(?P<Country>[A-Za-zÀ-ȕ ]+)"

    meeting_number = re.search(regex_meeting_number, first_page[0]).group(1)

    # TODO: Separate getting indices from actual matching in text
    # TODO: Move all the regexes out of the code below
    meta_str_index = re.search(regex_president, text).start()
    meta_text = text[:meta_str_index]

    president_str_index = re.search(regex_members, text).start()
    president_text = text[meta_str_index:president_str_index]
    president_match = re.search(
        "(?<=President:\n)(?P<Title>Mrs?\.|Dame) ?(?P<Person>[A-Za-zÀ-ȕ-]+)",
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
    agenda = re.search("(?<=Agenda\n)(.+)($|\n)", agenda_text).group(1)

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
    title = r"(?P<Title>((Mr|Mr|Ms).|Dame))"
    person = r"(?P<Person>[A-Za-zÀ-ȕ\ ]+)"
    country = r"(?P<Country>\([A-Za-zÀ-ȕ\ ]+\))"
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

    if pdf_type == "transcript":
        # TODO: Make metadata extraction dependent on PDF type
        metadata = extract_metadata(pages[0])

        # TODO: Extract text cleaning (newlines, etc.) into own function and apply to text_full as well...
        text_full = "".join(["".join(page) for page in pages[1:]])
        parts = split_text_by_speakers(text_full)

        report_dict = {
            **metadata,
            "by_speaker": parts,
            "text": replace_newlines(text_full),
        }
        return report_dict

    return {}


if __name__ == "__main__":
    # files = get_files_from_folder("source_subset")
    files = ["S_PV.4521.pdf", "S_PV.4541.pdf"]
    extracted_folder = Path("extracted")

    for filename in files:
        doc = fitz.open(f"source_subset/{filename}")

        report_dict = process_doc(doc)
        output_path = extracted_folder / f"{str(Path(filename).stem)}{'.json'}"

        with open(output_path, "w") as f:
            dump = json.dumps(report_dict, indent=4, ensure_ascii=False).encode("utf-8")
            f.write(dump.decode())

# TODO: Want some mechanism for combining text correctly.
# Might want to join with a space and then squash extra spaces with \s+ replacement
