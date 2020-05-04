#!/usr/bin/env python
#
# csv2hitchcsv.py
#
# Usage: 
#   $ csv2hitchcsv.py --salt SALT --input original.csv --output hashedfile.csv
#
# Assumptions:
#   - This script assumes data has been normalized already
#     (i.e. leading and trailing spaces trimmed, case changed, etc).
#   - This script assumes the first column is always PersonID which 
#     will NOT be hashed.
#   - This script assumes the last column is always Operation which
#     will NOT be hashed.
#   - Empty values (blank, undefined, null) should not be
#     hashed. This script assumes such values evaluate to False
#     in Python. 
#   - Values such as "-" should also NOT be hashed and replaced
#     instead with blank (empty string).
#   

import argparse
import hashlib
import base64
import csv
import sys

parser = argparse.ArgumentParser(description="A tool to hash records in a csv file so it can be used by Senate Matching")
parser.add_argument('-u', '--salt', help='Salt value', required=True)
parser.add_argument('-i', '--input', help='Read from filename. The file must be readable '
                                          'and in CSV format encoded in UTF-8',
                    type=argparse.FileType('rt', encoding='UTF-8'),
                    default=sys.stdin,
                    required=False)
parser.add_argument('-o', '--output', help='Write the hashed results to filename in CSV format',
                    type=argparse.FileType('wt', encoding='UTF-8'),
                    default=sys.stdout,
                    required=False)
args = parser.parse_args()

csvreader = csv.reader(args.input, delimiter=',')

csvwriter = csv.writer(args.output, skipinitialspace=True,
                        delimiter=',', quoting=csv.QUOTE_NONE)

row_count = 0
for row in csvreader:
    row_count += 1
    if row_count > 1:
        for i in range(1, len(row) - 1):
            # Do not hash empty strings
            if row[i] and row[i] not in ['-', 'NA', ' ']:
                hsh = hashlib.sha512((row[i] + args.salt).encode('utf-8'))
                row[i] = base64.b64encode(hsh.digest()).decode('utf-8')
            else:
                row[i] = ''
            
    csvwriter.writerow(row)