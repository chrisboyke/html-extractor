## Hippo HTML Extractor (Python3 version)

Python3 version of https://github.com/robbertkauffman/html-extractor

with a couple of additional features:
- Uses an .INI file for options
- Writes files directly to hippo repository-path locations
- Uses filecmp to test for file collisions / overwrites rather than a filename hashing scheme
- Handles relative paths in references in .css files
- Handles 'srcset' in img tags
- Handles a few other types of filenames / urls that might crop up in javascript in the base HTML file
- Option to prevent downloading of assets from specified URLs - use this if images aren't being served
correctly from Hippo (missing extension in filename, for example)


### Requirements

Requires https://github.com/chrisboyke/config_util

Also, install standard requirements via:

pip3 install -r requirements.txt

## Usage
extract.py <ini_file>

