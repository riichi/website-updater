# website-updater

Simple script that updates tournament pages on our website using a CSV file.

This script automatically creates a PR using GitHub CLI. 

## Requirements

* Python libraries from `requirements.txt`
* git
* [GitHub CLI](https://cli.github.com/)

## Usage

Example usage:

```bash
./website_updater.py \
  --data https://docs.google.com/spreadsheets/u/1/d/<ID>/export?format=csv&... \
  --template templates/hatsumi_taikai \
  --repository chombo.club
```

The repository (`chombo.club` in this case) must be cloned first. 
