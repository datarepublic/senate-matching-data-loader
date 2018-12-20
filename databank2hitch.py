#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""databank2hitch.py converts a Databank format CSV into a hashed Hitch Senate Matching CSV
and uploads it into the specified Contributor Node"""

from __future__ import print_function
import csv
import argparse
import sys
import os
import re
from distutils.util import strtobool
import base64
import hashlib
import requests
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3.exceptions import InsecureRequestWarning


DATABANK_SENATE_MATCHING_MAPPING = {
    'personid': {
        'aliases': ['personid', 'natural_key'],
        'mandatory': True,
        'multivalue': False,
        'normalization': 'str',
        'primary': True
        },
    'family_name': {
        'aliases': ['family_name', 'family_names'],
        'mandatory': False,
        'multivalue': True,
        'normalization': 'uppercase'
        },
    'given_name': {
        'aliases': ['given_name', 'first_name'],
        'mandatory': False,
        'multivalue': True,
        'normalization': 'uppercase'
        },
    'email': {
        'aliases': ['email', 'contact_email_address', 'alternate_email_address'],
        'mandatory': False,
        'multivalue': True,
        'normalization': 'email'
        },
    'phone': {
        'aliases': ['phone', 'contact_mobile_number', 'alternate_mobile_number',
                    'contact_landline_number', 'alternate_landline_number'],
        'mandatory': False,
        'multivalue': True,
        'normalization': 'phone'
        },
    'dpid': {
        'aliases': ['dpid', 'contact_aus_dpid', 'alternate_aus_dpid'],
        'mandatory': False,
        'multivalue': True,
        'normalization': 'int'
        }
}


# DATABANK_HEADERS is used to retrieve general details regarding the databank header given
# It will provide the position of the header, the Senate matching equivalent and the number
# of matching occurences
# Ex: {'natural_key': {'pos': 0, 'match': 'personid', 'multivalue':
#     {'multi_pos': 1, 'multi_max': 1}}}
DATABANK_HEADERS = {}

# MATCH gives direct equivalent of in-context DATABANK_FIELD to Senate Matching field
# Ex: {'natural_key': 'personid', 'phone': 'phone:0', 'email': 'email:0'}
MATCH = {}

MANDATORY_ENVIRONMENT_FIELDS = ['HITCH_CONTRIBUTOR_NODE', 'HITCH_API_KEY']
HITCH_BUF_FILENAME = '.buf_hitch.csv'


def requests_ca_verify():
    """requests_ca_verify follows requests verify option.
    The value can be either a boolean
    or a path to a CA public key certificate
    """
    raw_verify = os.environ.get('REQUESTS_CA_VERIFY', 'True')
    try:
        return bool(strtobool(raw_verify))
    except ValueError:
        if os.path.exists(raw_verify):
            return raw_verify
        eprint('Invalid value for REQUESTS_CA_VERIFY. Either set it to a path for '
               'a CA certificate key or to a boolean')
        exit(3)


def retrieve_salts(hostname, static_auth, ca_verify=True):
    """retrieve salt value per field from GlobalConfig"""
    try:
        salt_req = requests.get(hostname + 'GlobalConfig', auth=static_auth, verify=ca_verify)
        salt_req.raise_for_status()
        payload = salt_req.json()

        for field_def in [('Fields', 'FieldName'), ('FieldQualifiers', 'Name')]:
            type_def, name_def = field_def
            for field in payload[type_def]:
                name = payload[type_def][field][name_def]
                if name in DATABANK_SENATE_MATCHING_MAPPING:
                    DATABANK_SENATE_MATCHING_MAPPING[name]['salt'] = payload[type_def][field][
                        'HashSalt']

    except requests.exceptions.SSLError:
        eprint("Error: Invalid certificate. Update your environment variables "
               "by either using your system's trusted CAs with "
               "REQUESTS_CA_BUNDLE or set REQUESTS_CA_VERIFY to false")
        exit(2)
    except requests.exceptions.ConnectionError:
        eprint('Error: contributor node is unreachable')
        exit(2)
    except requests.HTTPError as ex:
        print(ex)
        eprint('Error {}: {}'.format(salt_req.status_code, salt_req.text.rstrip()))
        exit(2)
    except ValueError:
        eprint('Error: error decoding the response')
        exit(2)
    except KeyError as ex:
        eprint('Error: invalid payload received. KeyError: {}'.format(ex))
        exit(2)


def eprint(*args, **kwargs):
    """print message to stderr"""
    print(*args, file=sys.stderr, **kwargs)


def read_csv(input_type):
    """read_csv_stdin processes CSV from stdin line by line"""
    for row in csv.DictReader(iter(input_type.readline, ''),
                              skipinitialspace=True, delimiter=',', quoting=csv.QUOTE_NONE):
        if row:
            yield row


def find_matching_field(header):
    """find_matching_field returns the exact matching field for an alias"""
    for field in DATABANK_SENATE_MATCHING_MAPPING:
        if header in DATABANK_SENATE_MATCHING_MAPPING[field]['aliases']:
            return field
    return None


def list_mandatory_field_aliases():
    """list_mandatory_field_aliases returns a dict of mandatory aliases to their primary key"""
    aliases = {}
    for field in DATABANK_SENATE_MATCHING_MAPPING:
        if DATABANK_SENATE_MATCHING_MAPPING[field]['mandatory']:
            for alias in DATABANK_SENATE_MATCHING_MAPPING[field]['aliases']:
                aliases[alias] = field
    return aliases


def parse_headers(headers):
    """parse_headers check for the validity of the headers
    basically update DATABANK_HEADERS"""

    mandatory_fields = [f for f in DATABANK_SENATE_MATCHING_MAPPING
                        if DATABANK_SENATE_MATCHING_MAPPING[f]['mandatory']]
    aliases_mandatory_fields = list_mandatory_field_aliases()
    multivalue_matching_fields = {}
    # Ordered list of valid headers
    valid_headers = []

    # First loop looking at match equivalent, mandatory fields and multi value position
    for header in headers:
        matching_field = find_matching_field(header)
        # Print a warning if the field is not expected
        if matching_field is None:
            eprint('Warning: [{}] header is not expected and will be ignored'.format(header))
            continue

        # Curated list of mandatory fields
        if header in aliases_mandatory_fields:
            mandatory_fields.remove(aliases_mandatory_fields[header])

        # Collision hashmap of matching fields
        if matching_field in multivalue_matching_fields:
            multivalue_matching_fields[matching_field] += 1
        else:
            multivalue_matching_fields[matching_field] = 1

        DATABANK_HEADERS[header] = {'match': matching_field,
                                    'multi_pos': multivalue_matching_fields[matching_field],
                                    'multi_max': -1}
        valid_headers.append(header)

    # Force quit for missing mandatory fields
    if mandatory_fields:
        eprint('Missing mandatory headers: {}'.format(', '.join(mandatory_fields)))
        exit(1)

    # Count of max multi value field per header
    for header in DATABANK_HEADERS:
        db_hdr = DATABANK_HEADERS[header]
        collision_field = db_hdr['match']
        if collision_field in multivalue_matching_fields:
            db_hdr['multi_max'] = multivalue_matching_fields[collision_field]

    # Make of MATCH map using multi values previously generated
    for header in DATABANK_HEADERS:
        if DATABANK_HEADERS[header]['multi_max'] > 1:
            MATCH[header] = DATABANK_HEADERS[header]['match'] + ':' \
                    + str(DATABANK_HEADERS[header]['multi_pos'] - 1)
        else:
            MATCH[header] = DATABANK_HEADERS[header]['match']

    return [MATCH[hd] for hd in valid_headers]


def normalize(value, normalization_method):
    """normailze performs operations of value parameter
    to transform it in a normalized senate matching format"""
    if normalization_method == 'email':
        return value.lower()
    elif normalization_method == 'uppercase':
        return value.upper()
    elif normalization_method == 'phone':
        convert_from = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        convert_to = "01234567892223334445556667777888999922233344455566677778889999"
        return filter_and_translator(value, convert_from, convert_to)
    elif normalization_method == 'int':
        return re.sub("[^0-9]", "", value)
    return str(value)


def filter_and_translator(input_str, filters, translate_to_chars):
    """filter_and_translator replace characters from input_str by
    equivalent from filters array on translate_to_chars"""
    new_buf = ''
    for c_input_str in input_str:
        f_count = 0
        for c_filter in filters:
            if c_input_str == c_filter:
                if f_count < len(translate_to_chars):
                    new_buf += translate_to_chars[f_count]
                else:
                    new_buf += c_input_str
            f_count += 1
    return new_buf


def parse_line(parsing_line):
    """parse_line is the base function for every single line
    read by the program."""
    newline = {}
    for tpl in parsing_line.items():
        key_tpl, value_tpl = tpl

        if key_tpl not in MATCH:
            continue

        # Get the original properties from DATABANK_SENATE_MATCHING_MAPPING
        databank_element = DATABANK_HEADERS[key_tpl]
        field = databank_element['match']
        norm_method = DATABANK_SENATE_MATCHING_MAPPING[field]['normalization']
        normalized_element = normalize(value_tpl, norm_method)

        if not normalized_element:
            eprint('Warning: {} is not from the expected format [{}] for {} '
                   'and will be ignored.'.format(value_tpl, norm_method, key_tpl))
            return None

        # The primary key_tpl must not be hashed
        match_key = MATCH[key_tpl]
        if 'primary' in DATABANK_SENATE_MATCHING_MAPPING[field] \
                and DATABANK_SENATE_MATCHING_MAPPING[field]['primary']:
            newline[match_key] = normalized_element
        else:
            newline[match_key] = senate_hash(match_key, normalized_element)
    return newline


def senate_hash(base_field, value):
    """senate_hash is hashing given field as the contributor node"""
    salt = DATABANK_SENATE_MATCHING_MAPPING[base_field]['salt']
    hsh = hashlib.sha512((value + salt).encode('utf-8'))
    return base64.b64encode(hsh.digest()).decode('utf-8')


def validate_env():
    """validate_env validates the environment variables to make sure the request
    to Contributor node will be possible after the data has been processed"""
    for env_field in MANDATORY_ENVIRONMENT_FIELDS:
        if env_field not in os.environ:
            eprint('Error: {} mandatory environment variable is not set.'.format(env_field))
            exit(3)


def clean_buf_env():
    """clean_buf_env makes sure the buffer file does not exists"""
    try:
        os.remove(HITCH_BUF_FILENAME)
    except IOError:
        pass


def hitch_contributor_node_url():
    """hitch_contributor_node_url performs a scheme and trailing slash clean up"""
    hcn = os.environ['HITCH_CONTRIBUTOR_NODE']
    if hcn.endswith('/'):
        hcn = hcn[:-1]
    if hcn.startswith('https://'):
        return '{}/api/Contributor/v1/'.format(hcn)
    return 'https://{}/api/Contributor/v1/'.format(hcn)


def generate_hitch_csv(iterator):
    """generate_hitch_csv reads from iterator and writes to temporary buffer"""
    # Use of a tempoary file to avoid storing the entire file in memory
    parsed_headers = False
    with open(HITCH_BUF_FILENAME, 'wt', encoding='UTF8') as hitch_buf_fd:
        for raw_line in iterator:
            # One time header parse
            if not parsed_headers:
                writer = csv.DictWriter(hitch_buf_fd, fieldnames=parse_headers(raw_line.keys()))
                writer.writeheader()
                parsed_headers = True

            parsed_line = parse_line(raw_line)
            if parsed_line:
                writer.writerow(parsed_line)


def contributor_loaded_tokens(hostname, parameters, static_auth, ca_verify=True):
    """generate_tokens_csv makes a CSV file with personid,tokens"""
    try:
        token_req = requests.get(hostname + 'GetPersonTokens',
                                 params=parameters,
                                 auth=static_auth,
                                 headers={'accept': 'application/json'},
                                 verify=ca_verify)
        token_req.raise_for_status()
        return token_req.json()
    except requests.exceptions.SSLError:
        eprint("Error: Invalid certificate. Update your environment variables "
               "by either using your system's trusted CAs with "
               "REQUESTS_CA_BUNDLE or set REQUESTS_CA_VERIFY to false")
        exit(2)
    except requests.exceptions.ConnectionError:
        eprint('Error: contributor node is unreachable')
        exit(2)
    except requests.HTTPError as ex:
        print(ex)
        eprint('Error {}: {}'.format(load_req.status_code, load_req.text.rstrip()))
        exit(2)
    except ValueError:
        eprint('Error: error decoding the response')
        exit(2)


def write_output(output, tokens):
    """write_output writes on the specified output the resulting CSV"""
    if output == sys.stdout:
        print('personid,token')
        for row in tokens:
            print('{},{}'.format(row['PersonId'], row['Token']))
        return

    csvwriter = csv.writer(output, skipinitialspace=True,
                           delimiter=',', quoting=csv.QUOTE_NONE)
    csvwriter.writerow(['personid', 'token'])
    for row in tokens:
        csvwriter.writerow([row['PersonId'], row['Token']])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Loads a CSV that uses Databank column names into "
                                                 "Senate Matching Contributor Node")
    parser.add_argument('-u', '--uuid', help='UUID to write data into', required=True)
    parser.add_argument('-i', '--input', help='Read from filename. The file must be readable '
                                              'and in CSV format encoded in UTF-8',
                        type=argparse.FileType('rt', encoding='UTF-8'),
                        default=sys.stdin,
                        required=False)
    parser.add_argument('-o', '--output', help='Write the mapping file to filename when upload is '
                                               'complete. The mapping file will be in CSV format',
                        type=argparse.FileType('wt', encoding='UTF-8'),
                        default=sys.stdout,
                        required=False)
    args = parser.parse_args()

    validate_env()
    clean_buf_env()

    host = hitch_contributor_node_url()
    params = {'DBUUID': args.uuid}
    auth = HTTPBasicAuth('api', os.environ['HITCH_API_KEY'])
    req_ca_verify = requests_ca_verify()
    if isinstance(req_ca_verify, bool) and not req_ca_verify:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    retrieve_salts(host, auth, req_ca_verify)
    generate_hitch_csv(read_csv(args.input))

    try:
        load_req = requests.post(host + 'LoadHashedRecords', params=params,
                                 auth=auth,
                                 files={'file': (HITCH_BUF_FILENAME, open(HITCH_BUF_FILENAME, 'rb'),
                                                 'text/csv')},
                                 verify=req_ca_verify)
        load_req.raise_for_status()
    except requests.exceptions.SSLError:
        eprint("Error: Invalid certificate. Update your environment variables "
               "by either using your system's trusted CAs with "
               "REQUESTS_CA_BUNDLE or set REQUESTS_CA_VERIFY to false")
        exit(2)
    except requests.exceptions.ConnectionError:
        eprint('Error: contributor node is unreachable')
        exit(2)
    except requests.HTTPError:
        eprint('Error {}: {}'.format(load_req.status_code, load_req.text.rstrip()))
        exit(2)
    else:
        token_tuples = contributor_loaded_tokens(host, params, auth, req_ca_verify)
        if not token_tuples:
            eprint('Error: no loaded tokens found after load')
            exit(2)
        write_output(args.output, token_tuples)
    finally:
        clean_buf_env()
