import json
from pathlib import Path
import re
import fitz
from multi_column import column_boxes
from io_utils import get_files_from_folder

def replace_newlines(text: str) -> str:
    return re.sub("\s+", " ", text)

def extract_metadata(first_page: dict[int, str]) -> dict[str, str]:

    if re.search("Official communiqué of the \d+\w+ \(closed\) meeting", first_page[0]):
        # * In case of official communiqué. Would still want to extract some metadata in other function
        return {}
    # ! Use pages here doesn't work. Maybe best to combine all together ?

    # ! Note: Can extract more info from here still
    speaker_to_country = {} # Not comprehensive, can have unlisted speakers such as Mr. Wennesland at S/PV.9556
    text = first_page[2]

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
    president_match = re.search("(?<=President:\n)(?P<Title>Mrs?\.|Dame) ?(?P<Person>[A-Za-zÀ-ȕ-]+)", president_text)
    president = president_match.group("Title") + " " + president_match.group("Person")
    president_country = re.search("\(([A-Za-zÀ-ȕ- ]+)\)", president_text).group(1).strip()

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
        "president": (president, president_country)
    }
    
    return metadata


def get_pages(doc) -> list[str]:
    pages = []

    for page in doc:
        bboxes = column_boxes(page, footer_margin=80, header_margin=80, no_image_text=True)
        page_text = []

        for rect in bboxes:
            text = page.get_text(clip=rect, sort=True)
            page_text.append(text)
        
        pages.append(page_text)

    return pages
    

def split_text_by_speakers(text: str) -> list[dict[str, str]]:
    speaker_regex = f"\\n((?P<Title>Mrs?\.|Dame) (?P<Person>[A-Za-zÀ-ȕ\\ ]+) ?(?P<Country>\([A-Za-zÀ-ȕ\\ ]+\))? ?(?P<Language>\([A-Za-zÀ-ȕ\\ ]+\))?|The President):"
    matches = re.finditer(speaker_regex, text)

    # * Messy, will improve later
    parts = []
    start_index = 0
    name = "Intro"
    for match in matches:
        # Get the start index of the match
        match_start_index = match.start()
        
        # Split the input string from the last match to the current match
        split_part = text[start_index:match_start_index].strip()
        
        # Output the split part
        if split_part:
            parts.append({
                "speaker": name.replace("\n", ""),
                "text": replace_newlines(split_part)
                }
    )
            print(split_part)
            print("\n-------------\n")
        
        # Update the start index for the next split
        start_index = match.end()
        name = match[0]
    return parts


def process_doc(doc) -> dict:
    pages = get_pages(doc)

    metadata = extract_metadata(pages[0])
    # TODO: Extract text cleaning (newlines, etc.) into own function and apply to text_full as well...
    text_full = "".join(["".join(page) for page in pages[1:]])
    parts = split_text_by_speakers(text_full)

    report_dict = {** metadata, "by_speaker": parts, "text": replace_newlines(text_full)}
    return report_dict


if __name__ == "__main__":
    files = get_files_from_folder("source_subset")
    extracted_folder = Path("extracted")
    
    for filename in files:
        doc = fitz.open(f"source_subset/{filename}")

        report_dict = process_doc(doc)
        output_path = extracted_folder / f"{str(Path(filename).stem)}{'.json'}"

        with open(output_path, "w") as f:
            dump = json.dumps(report_dict, indent = 4, ensure_ascii=False).encode('utf-8')
            f.write(dump.decode())

# TODO: Want some mechanism for combining text correctly. 
# Might want to join with a space and then squash extra spaces with \s+ replacement