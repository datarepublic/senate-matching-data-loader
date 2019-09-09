#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""integration tests"""

import os
import sys
import subprocess
import csv
import io

import requests
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3.exceptions import InsecureRequestWarning

ENVS = [('HITCH_API_KEY', 'mysecret'), ('HITCH_CONTRIBUTOR_NODE', 'https://localhost:8952'),
        ('REQUESTS_CA_VERIFY', '0')]
UUID = '26e1587a-6a64-4d78-b7f5-fa3efbdebe67'


def set_env():
    """set_env sets the proper environment for subprocess shell based on ENVS"""
    for env_value in ENVS:
        if env_value[0] not in os.environ:
            os.environ[env_value[0]] = env_value[1]

def verify_accessible_contributor_node_api():
    """verify_accessible_contributor_node_api check if remote host is accessible"""
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    params = {'DBUUID': UUID}
    auth = HTTPBasicAuth('api', os.environ['HITCH_API_KEY'])

    try:
        r = requests.get(os.environ['HITCH_CONTRIBUTOR_NODE'] + '/api/Contributor/v1/GlobalConfig',
                params=params,
                auth=auth,
                headers={'accept': 'application/json'},
                verify=False,
                timeout=2)
        r.raise_for_status()
    except Exception as ex:
        print('Node is not accessible:', str(ex))
        exit(1)

def has_warning(header, stderr):
    warn_line = 'Warning: [{}] header is not expected and will be ignored'.format(header)
    return warn_line in str(stderr)


def test_00(sub_result):
    """test_00"""

    # Check of unused field customer_address from STDERR
    bad_headers = ['customer_address']
    for header in bad_headers:
        if not has_warning(header, sub_result.stderr):
            print('Test_00: Fail:[{}] header warning is expected'.format(header))
            exit(1)

    # Check for record with personid and token
    output = io.StringIO(sub_result.stdout.decode('utf-8'))
    for row in csv.DictReader(output):
        if row['personid'] not in ['1', '2']:
            print('Test_00: Fail: {} not in output result'.format(natural_key))
            exit(1)
    print('Test 00: Ok')


def fixture_number(fixture_name):
    """fixture_number"""
    return fixture_name.split('/')[-1].split('_')[0]


if __name__ == '__main__':
    set_env()
    verify_accessible_contributor_node_api()

    script_path_base = os.path.dirname(sys.argv[0])
    fixture_path = script_path_base + '/fixtures/'
    fixtures = [os.path.join(fixture_path, f) for f in os.listdir(fixture_path)
                if os.path.isfile(os.path.join(fixture_path, f))]

    input_fixtures = []
    for f in fixtures:
        if f.endswith('_input.csv'):
            input_fixtures.append(f)

    databank2hitch_path = script_path_base + '/../databank2hitch.py'
    for fixture in input_fixtures:
        cmd = [databank2hitch_path, '--input', fixture, '--uuid', UUID]
        result = subprocess.run(' '.join(cmd), shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        eval('test_{}(result)'.format(fixture_number(fixture)))
