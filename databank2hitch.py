#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""databank2hitch.py converts a Databank format CSV into a hashed Hitch Senate Matching CSV
and uploads it into the specified Contributor Node"""

import argparse
import base64
import csv
import hashlib
import os
import re
import subprocess
import sys
import logging
from distutils.util import strtobool
from collections import OrderedDict

import regex
import requests
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Fields without salt are NOT going to be encrypted.
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
        'normalization': 'name'
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
    },
    'frequent_flyer_number': {
        'aliases': ['frequent_flyer_number'],
        'mandatory': False,
        'multivalue': False,
        'normalization': 'uppercase'
    },
    'nationalid': {
        'aliases': ['nationalid'],
        'mandatory': False,
        'multivalue': False,
        'normalization': 'uppercase'
    },
    'operation': {
        'aliases': ['operation'],
        'mandatory': False,
        'multivalue': False,
        'normalization': 'uppercase',
        'salt': False
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
HITCH_BUF_FILENAME = '.databank2hitch_script.csv'
UPLOAD_FILENAME = HITCH_BUF_FILENAME


# A logger that will print DEBUG and INFO to stdout, WARNING and ERROR to stderr
class InfoFilter(logging.Filter):
    def filter(self, rec):
        return rec.levelno in (logging.DEBUG, logging.INFO)

class InvalidFileHeadersError(Exception):
   """Raised when the file contains invalid headers"""
   pass

class InvalidLineError(Exception):
   """Raised when the file contains an invalid line"""
   pass

class DuplicatedColumnError(Exception):
   """Raised when the file contains multiple columns with the same name"""
   pass


logger = logging.getLogger('__name__')
logger.setLevel(logging.DEBUG)

h1 = logging.StreamHandler(sys.stdout)
h1.setLevel(logging.DEBUG)
h1.addFilter(InfoFilter())
h2 = logging.StreamHandler()
h2.setLevel(logging.WARNING)

logger.addHandler(h1)
logger.addHandler(h2)


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
        logger.error('Invalid value for REQUESTS_CA_VERIFY. Either set it to a path for '
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
                if name in DATABANK_SENATE_MATCHING_MAPPING and \
                        DATABANK_SENATE_MATCHING_MAPPING[name].get('salt', True):
                    DATABANK_SENATE_MATCHING_MAPPING[name]['salt'] = payload[type_def][field][
                        'HashSalt']
        return True
    except requests.exceptions.SSLError:
        logger.error("Error: Invalid certificate. Update your environment variables "
               "by either using your system's trusted CAs with "
               "REQUESTS_CA_BUNDLE or set REQUESTS_CA_VERIFY to false")
        return False
    except requests.exceptions.ConnectionError:
        logger.error('Error: contributor node is unreachable')
        return False
    except requests.HTTPError as ex:
        logger.error('Error {}: {}'.format(salt_req.status_code, salt_req.text.rstrip()))
        return False
    except ValueError:
        logger.error('Error: error decoding the response')
        return False
    except KeyError as ex:
        logger.error('Error: invalid payload received. KeyError: {}'.format(ex))
        return False


def override_temp_buffer_name(some_input):
    """override_temp_buffer_name change the library temporary buffer
       Does nothing for STIN
       Change to filename if it's given a file descriptor
       Or set to string elsewise"""
    global UPLOAD_FILENAME
    if some_input != sys.stdin:
        if 'name' in dir(some_input):
            UPLOAD_FILENAME = some_input.name.split('/')[-1]
        else:
            UPLOAD_FILENAME = str(some_input)

def recover_temp_buffer_name():
    """simply recover the buffer name after override"""
    global HITCH_BUF_FILENAME
    global UPLOAD_FILENAME
    UPLOAD_FILENAME = HITCH_BUF_FILENAME

def read_csv(input_type, delimiter, exit_on_failure=False):
    """read_csv_stdin processes CSV from stdin line by line"""
    csvReader = csv.reader(iter(input_type.readline, ''), skipinitialspace=True, delimiter=delimiter, quoting=csv.QUOTE_NONE)
    try:
        headers = next(csvReader)
    except StopIteration:
        logger.debug("The file you're trying to upload is empty")
        if exit_on_failure:
            exit(1)
        return

    if len(headers) != len(set(headers)):
        logger.error("The file you're trying to upload contains duplicated headers")
        if exit_on_failure:
            exit(1)
        raise DuplicatedColumnError

    for row in csvReader:
        odict = OrderedDict()
        for idx, field in enumerate(row):
            try:
                odict[headers[idx]] = field
            except IndexError:
                logger.error("The file you're trying to upload has more fields compared to the header row")
                if exit_on_failure:
                    exit(1)
                raise InvalidFileHeadersError
        if len(odict) < len(headers):
            logger.error("The file you're trying to upload has less fields compared to the header row")
            if exit_on_failure:
                exit(1)
            raise InvalidLineError
        yield odict

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
        if matching_field is None:
            logger.warning('Warning: [{}] header is not expected and will be ignored'.format(header))
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
        logger.error('Missing mandatory headers: {}'.format(', '.join(mandatory_fields)))
        raise InvalidFileHeadersError

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
    """normalize performs operations of value parameter
    to transform it in a normalized senate matching format"""

    # optional conversion of Asian wide strings to narrow. See Makefile and toNarrow.go
    exe = os.path.dirname(os.path.realpath(__file__)) + "/tonarrow"
    if os.path.isfile(exe) and os.access(exe, os.X_OK):
        the_bytes = value.encode('utf-8')
        result = subprocess.run(exe, stdout=subprocess.PIPE, input=the_bytes)
        value = result.stdout.decode('utf-8').rstrip()

    if value is None:
        return ''

    if normalization_method == 'email':
        whitespace = regex.compile('\p{Z}')
        return whitespace.sub('', value.lower())
    elif normalization_method == 'uppercase':
        return value.upper().strip()
    elif normalization_method == 'phone':
        convert_from = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        convert_to = "01234567892223334445556667777888999922233344455566677778889999"
        return filter_and_translator(value, convert_from, convert_to)
    elif normalization_method == 'numeric':
        return re.sub("[^0-9]", "", value)
    elif normalization_method == 'name':
        nonLetters = regex.compile('\P{L}')
        return nonLetters.sub('', value.lower())
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
            continue

        # The primary key_tpl must not be hashed
        match_key = MATCH[key_tpl]
        if 'primary' in DATABANK_SENATE_MATCHING_MAPPING[field] \
                and DATABANK_SENATE_MATCHING_MAPPING[field]['primary']:
            newline[match_key] = normalized_element
        else:
            newline[match_key] = senate_hash(field, normalized_element)
    return newline


def senate_hash(base_field, value):
    """senate_hash is hashing given field as the contributor node"""
    # Do not hash fields that do not have salt. e.g. operation type
    if not DATABANK_SENATE_MATCHING_MAPPING[base_field].get('salt', False):
        return base_field
    salt = DATABANK_SENATE_MATCHING_MAPPING[base_field]['salt']
    hsh = hashlib.sha512((value + salt).encode('utf-8'))
    return base64.b64encode(hsh.digest()).decode('utf-8')


def validate_env():
    """validate_env validates the environment variables to make sure the request
    to Contributor node will be possible after the data has been processed"""
    for env_field in MANDATORY_ENVIRONMENT_FIELDS:
        if env_field not in os.environ:
            logger.error('Error: {} mandatory environment variable is not set.'.format(env_field))
            exit(3)


def clean_buf_env():
    """clean_buf_env makes sure the buffer file does not exists"""
    # HIT-923: disable file removal to debugging file size issue
    # try:
    #     os.remove(HITCH_BUF_FILENAME)
    # except IOError:
    #     pass


def hitch_contributor_node_url(hcn=None):
    """hitch_contributor_node_url performs a scheme and trailing slash clean up"""
    if not hcn:
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
    clean_buf_env()

    with open(HITCH_BUF_FILENAME, 'wt', encoding='UTF8') as hitch_buf_fd:
        for raw_line in iterator:
            # One time header parse
            if not parsed_headers:
                try:
                    writer = csv.DictWriter(hitch_buf_fd, fieldnames=parse_headers(raw_line.keys()))
                    writer.writeheader()
                except InvalidFileHeadersError:
                    clean_buf_env()
                    return False
                parsed_headers = True

            try:
                parsed_line = parse_line(raw_line)
            except InvalidLineError:
                clean_buf_env()
                return False
            if parsed_line:
                writer.writerow(parsed_line)
    return True


def contributor_loaded_tokens(hostname, dbuuid, static_auth, ca_verify=True):
    """generate_tokens_csv makes a CSV file with personid,tokens"""

    params = {'DBUUID': dbuuid}
    try:
        token_req = requests.get(hostname + 'GetPersonTokens',
                                 params=params,
                                 auth=static_auth,
                                 headers={'accept': 'application/json'},
                                 verify=ca_verify)
        token_req.raise_for_status()
        token_json = token_req.json()
        if not token_json:
            logger.error('Error: no loaded tokens found after load')
        return token_json, True
    except requests.exceptions.SSLError:
        logger.error("Error: Invalid certificate. Update your environment variables "
               "by either using your system's trusted CAs with "
               "REQUESTS_CA_BUNDLE or set REQUESTS_CA_VERIFY to false")
        return [], False
    except requests.exceptions.ConnectionError:
        logger.error('Error: contributor node is unreachable')
        return [], False
    except requests.HTTPError as ex:
        logger.error(ex)
        logger.error('Error {}: {}'.format(token_req.status_code, token_req.text.rstrip()))
        return [], False
    except ValueError:
        logger.error('Error: error decoding the response')
        return [], False


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

def load_hashed_records(host, dbuuid, auth, ca_verify=True, hashedFile=''):
    """load_hashed_records() loads the data and return the token/id mapping"""

    params = {'DBUUID': dbuuid}
    src = HITCH_BUF_FILENAME if hashedFile == '' else hashedFile
    try:
        load_req = requests.post(host + 'LoadHashedRecords', params=params,
                                 auth=auth,
                                 files={'file': (UPLOAD_FILENAME, open(src, 'rb'),
                                                 'text/csv')},
                                 verify=ca_verify)
        load_req.raise_for_status()
    except requests.exceptions.SSLError:
        logger.error("Error: Invalid certificate. Update your environment variables "
               "by either using your system's trusted CAs with "
               "REQUESTS_CA_BUNDLE or set REQUESTS_CA_VERIFY to false")
    except requests.exceptions.ConnectionError:
        logger.error('Error: contributor node is unreachable')
    except requests.HTTPError:
        try:
            format_error = load_req.json()
            logger.error('Error {}: {} ({})'.format(load_req.status_code, format_error['error'], format_error['code']))
        except:
            logger.error('Error {}: {}'.format(load_req.status_code, load_req.text.rstrip()))
    except OverflowError as e:
        statinfo = os.stat(src)
        logger.error('Error: File size {:3d} GB is too large', statinfo.st_size / ( 1024 * 1024 * 1024 )) # bytes to GB
    finally:
        clean_buf_env()
        if 'load_req' in locals():
            return load_req.status_code
        return 500

def get_chunk_file_list(filename, delimiter=","):
    fileList = []
    # Check the file size and split it to 50k line chunks if it's larger than single file size limit
    singleFileSizeLimit = 2 * 1024  * 1024 * 1024 
    statinfo = os.stat(filename)
    if statinfo.st_size > singleFileSizeLimit :
        chunkFolder = "chunks"
        try:
            os.makedirs(chunkFolder)
        except FileExistsError:
            pass
        fileList.extend(splitFile(filename))
    else :
        fileList.append(filename)

    return fileList

def splitFile(filename, chunkSize = 50 * 1000):    
    fileList = []
    chunkFile = None
    header = None

    with open(filename,'rt') as f:
        csv_reader = csv.reader(f)
        try:
            header = next(csv_reader)
        except StopIteration:
            logger.error("Failed to load header from source file {}".format(filename))
            exit(1)
        for lineno, line in enumerate(csv_reader):
            if lineno % chunkSize == 0 :
                if chunkFile:
                    chunkFile.close() # reach chunk size, close the current chunk file and start a new one
                chunkFile_Name = f'chunks/{filename.split("/")[-1]}_chunk_{len(fileList):03d}.csv'
                fileList.append(chunkFile_Name)
                chunkFile = open(chunkFile_Name, 'w+')
                chunkFileWriter = csv.writer(chunkFile)
                chunkFileWriter.writerow(header)
            chunkFileWriter.writerow(line)
        if chunkFile: # close the last chunk file
            chunkFile.close()

    return fileList

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
    parser.add_argument('-d', '--delimiter',
                        help='CSV Delimiter on the input file. Comma by default. To use tab, enter: $\'\\t\'',
                        default=',',
                        required=False)
    parser.add_argument('--hashed',
                        type=strtobool,
                        help='Specify True if the file has hashed to skip second hashing',
                        default=False,
                        required=False)
    args = parser.parse_args()

    validate_env()

    host = hitch_contributor_node_url()
    auth = HTTPBasicAuth('api', os.environ['HITCH_API_KEY'])
    req_ca_verify = requests_ca_verify()
    if isinstance(req_ca_verify, bool) and not req_ca_verify:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    override_temp_buffer_name(args.input)
    if args.hashed:
        status = load_hashed_records(host, args.uuid, auth, req_ca_verify, args.input)
    else:
        if not retrieve_salts(host, auth, req_ca_verify):
            exit(2)
        if not generate_hitch_csv(read_csv(args.input, args.delimiter, exit_on_failure=True)):
            exit(1)
        status = load_hashed_records(host, args.uuid, auth, req_ca_verify)
    
    if status > 399:
        if status < 500:
            exit(1)
        else:
            exit(2)

        exit(2)
    token_tuples, status = contributor_loaded_tokens(host, args.uuid, auth, req_ca_verify)
    if not (status and token_tuples):
        exit(2)
    write_output(args.output, token_tuples)
