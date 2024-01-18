#!/usr/bin/env python3

import argparse
import csv
import dataclasses
import datetime
import io
import logging
import pathlib
import subprocess
import urllib.request

import pytz
from jinja2 import Environment, FileSystemLoader, select_autoescape

MAX_PARTICIPANTS = 84

EMA_COUNTRIES = {
    "Austria",
    "Belgium",
    "Czech Republic",
    "Denmark",
    "Finland",
    "France",
    "Germany",
    "Hungary",
    "Ireland",
    "Italy",
    "Netherlands",
    "Norway",
    "Poland",
    "Portugal",
    "Romania",
    "Slovakia",
    "Spain",
    "Sweden",
    "Switzerland",
    "Ukraine",
    "United Kingdom",
}

COUNTRIES_PL = {
    "Austria": "Austria",
    "Belarus": "Białoruś",
    "Belgium": "Belgia",
    "Canada": "Kanada",
    "Czech Republic": "Czechy",
    "Denmark": "Dania",
    "Finland": "Finlandia",
    "France": "Francja",
    "Germany": "Niemcy",
    "Hungary": "Węgry",
    "Ireland": "Irlandia",
    "Italy": "Włochy",
    "Netherlands": "Holandia",
    "Norway": "Norwegia",
    "Poland": "Polska",
    "Portugal": "Portugalia",
    "Romania": "Rumunia",
    "Slovakia": "Słowacja",
    "Spain": "Hiszpania",
    "Sweden": "Szwecja",
    "Switzerland": "Szwajcaria",
    "Ukraine": "Ukraina",
    "United Kingdom": "Wielka Brytania",
}

COUNTRIES_MAPPING = {v: k for k, v in COUNTRIES_PL.items()}

log = logging.getLogger("website_updater")


@dataclasses.dataclass
class PlayerRecord:
    first_name: str
    last_name: str
    nickname: str
    ema_id: str
    country_pl: str
    country_en: str
    paid: bool


def process_response(val) -> PlayerRecord:
    country = val["Państwo/Country"].strip().title()
    country = COUNTRIES_MAPPING.get(country, country)

    return PlayerRecord(
        first_name=val["Imię/First name"].strip(),
        last_name=val["Nazwisko/Last name"].strip(),
        nickname=val["Pseudonim/Nickname"].strip(),
        ema_id=val["EMA ID"].strip(),
        country_pl=COUNTRIES_PL.get(country, country),
        country_en=country,
        paid=val["Wpisowe"] == "TRUE",
    )


def request_csv(data_url: str) -> str:
    with urllib.request.urlopen(data_url) as response:
        return response.read().decode("utf-8")


def execute_cmd(cmd: list[str], cwd: str, dry_run: bool):
    log.info("Executing %s in %s", cmd, cwd)
    if dry_run:
        log.info("Dry run enabled; doing nothing")
    else:
        subprocess.check_call(cmd, cwd=cwd, stdout=subprocess.DEVNULL)


def execute_cmd_with_stdout(cmd: list[str], cwd: str) -> bytes:
    log.info("Executing %s in %s", cmd, cwd)
    return subprocess.check_output(cmd, cwd=cwd)


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        prog="website_updater",
        description="Automatically updates the chombo.club website using CSV data",
    )
    parser.add_argument("--data", required=True, help="CSV data URL")
    parser.add_argument("--template", required=True, help="Template directory path")
    parser.add_argument("--repository", required=True, help="git repository path")
    parser.add_argument("--dry-run", action="store_true", help="Only print the changes and don't modify any files")
    parser.add_argument("--force", action="store_true", help="Always create a PR, even with no new changes.")
    args = parser.parse_args()

    process(args.data, args.template, args.repository, args.dry_run, args.force)


def process(data_url: str, template_dir: str, repo: str, dry_run: bool, force: bool):
    responses = request_responses(data_url)
    participants = responses[:MAX_PARTICIPANTS]
    waiting_list = responses[MAX_PARTICIPANTS:]
    num_countries = calc_countries(participants)
    num_mers = calc_mers(participants)

    env = Environment(loader=FileSystemLoader("."), autoescape=select_autoescape())

    now = datetime.datetime.now(pytz.timezone("Europe/Warsaw"))
    datetime_str = now.strftime("%Y%m%d_%H%M%S")
    branch_name = f"update_{datetime_str}"

    cleanup_repo(repo, branch_name, dry_run)

    path = pathlib.Path(template_dir)
    for file in path.rglob("*.tmpl"):
        template = env.get_template(str(file))

        relative_path = file.relative_to(path)
        new_path = pathlib.Path(repo) / relative_path
        log.info("Writing to: %s", new_path)

        new_path = new_path.resolve()
        with (new_path.parent / new_path.stem).open("w") as f:
            rendered = template.render(
                participants=participants,
                waiting_list=waiting_list,
                num_countries=num_countries,
                num_mers=num_mers,
                now=now,
            )
            if dry_run:
                log.info("%s", rendered)
            else:
                f.write(rendered)

    create_pr(repo, branch_name, now, dry_run, force)


def request_responses(data_url: str) -> list[PlayerRecord]:
    csv_data = request_csv(data_url)
    responses = list(csv.DictReader(io.StringIO(csv_data)))
    responses = list(map(process_response, responses))
    return responses


def cleanup_repo(repo: str, branch_name: str, dry_run: bool):
    execute_cmd(["git", "restore", "."], repo, dry_run)
    execute_cmd(["git", "checkout", "master"], repo, dry_run)
    execute_cmd(["git", "reset", "--hard", "HEAD"], repo, dry_run)
    execute_cmd(["git", "pull"], repo, dry_run)
    execute_cmd(["git", "checkout", "-b", branch_name], repo, dry_run)


def create_pr(repo: str, branch_name: str, now: datetime.datetime, dry_run: bool, force: bool):
    title = f"chore: update to {now.strftime('%Y-%m-%d %H:%M')}"
    body = f"Automatic update of the website posts. Data retrieval timestamp: {now}"

    if not force and not has_new_changes(repo):
        log.info("No new changes, skipping PR creation")
        return

    execute_cmd(["git", "commit", "-a", "-m", title], repo, dry_run)
    execute_cmd(["git", "push", "-u", "origin", branch_name], repo, dry_run)
    execute_cmd(["gh", "pr", "create", "--title", title, "--body", body], repo, dry_run)


def has_new_changes(repo: str) -> bool:
    diff = execute_cmd_with_stdout(["git", "difftool", "--extcmd=diff", "--no-prompt"], repo).decode()
    for line in diff.splitlines():
        if not line.startswith(("> ", "< ")):
            continue
        stripped_line = line[2:]
        if stripped_line.startswith("last_modified_at: "):
            continue
        return True
    return False


def calc_countries(responses: list[PlayerRecord]):
    countries = set(val.country_en for val in responses)
    ema_countries = countries.intersection(EMA_COUNTRIES)
    return len(ema_countries)


def calc_mers(responses: list[PlayerRecord]):
    num_players = len(responses)
    num_countries = calc_countries(responses)

    mers = 2

    if 40 < num_players <= 80:
        mers += 0.5
    elif num_players > 80:
        mers += 1

    if 5 < num_countries <= 9:
        mers += 0.5
    elif num_countries > 9:
        mers += 1

    return mers


if __name__ == "__main__":
    main()
