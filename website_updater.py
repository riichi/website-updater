#!/usr/bin/env python3

import argparse
import datetime
import io
import logging
import pathlib
import subprocess
import urllib.request
from typing import List, Dict

import pytz
from jinja2 import Environment, select_autoescape, FileSystemLoader
import csv

COUNTRIES = {
    'Polska': 'Poland',
}

COUNTRIES_PL = {
    'Poland': 'Polska',
    'Portugal': 'Portugalia',
}


def process_response(val) -> Dict[str, str]:
    country = val["Państwo/Country"].strip()
    country = COUNTRIES.get(country, country)

    return {
        'first_name': val["Imię/First name"].strip(),
        'last_name': val["Nazwisko/Last name"].strip(),
        'ema_id': val["EMA ID"].strip(),
        'country_pl': COUNTRIES_PL.get(country, country),
        'country_en': country,
    }


def request_csv(data_url: str) -> str:
    with urllib.request.urlopen(data_url) as response:
        return response.read().decode('utf-8')


def execute_cmd(cmd, cwd):
    logging.info("Executing %s in %s", cmd, cwd)
    subprocess.check_call(cmd, cwd=cwd, stdout=subprocess.DEVNULL)


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        prog='website_updater',
        description='Automatically updates the chombo.club website using CSV data')
    parser.add_argument('--data', required=True, help='CSV data URL')
    parser.add_argument('--template', required=True, help='Template directory path')
    parser.add_argument('--repository', required=True, help='git repository path')
    args = parser.parse_args()

    process(args.data, args.template, args.repository)


def process(data_url: str, template_dir: str, repo: str):
    responses = request_responses(data_url)

    env = Environment(
        loader=FileSystemLoader("."),
        autoescape=select_autoescape()
    )

    now = datetime.datetime.now(pytz.timezone('Europe/Warsaw'))
    datetime_str = now.strftime("%Y%m%d_%H%M%S")
    branch_name = f"update_{datetime_str}"

    cleanup_repo(repo, branch_name)

    path = pathlib.Path(template_dir)
    for file in path.rglob('*.tmpl'):
        template = env.get_template(str(file))

        relative_path = file.relative_to(path)
        new_path = pathlib.Path(repo) / relative_path
        logging.info("Writing to: %s", new_path)

        with open(str(new_path)[:-len(".tmpl")], 'w') as f:
            f.write(template.render(data=responses, now=now))

    create_pr(repo, branch_name, now)


def request_responses(data_url: str) -> List[Dict[str, str]]:
    csv_data = request_csv(data_url)
    responses = list(csv.DictReader(io.StringIO(csv_data)))
    responses = list(map(process_response, responses))
    responses.sort(key=lambda val: (val['last_name'], val['first_name']))
    return responses


def cleanup_repo(repo: str, branch_name: str):
    execute_cmd(["git", "restore", "."], repo)
    execute_cmd(["git", "checkout", "master"], repo)
    execute_cmd(["git", "reset", "--hard", "HEAD"], repo)
    execute_cmd(["git", "pull"], repo)
    execute_cmd(["git", "checkout", "-b", branch_name], repo)


def create_pr(repo, branch_name, now):
    title = f"chore: update to {now.strftime('%Y-%m-%d %H:%M')}"
    body = f"Automatic update of the website posts. Data retrieval timestamp: {now}"
    execute_cmd(["git", "commit", "-a", "-m", title], repo)
    execute_cmd(["git", "push", "-u", "origin", branch_name], repo)
    execute_cmd(["gh", "pr", "create", "--title", title, "--body", body], cwd=repo)


if __name__ == '__main__':
    main()
