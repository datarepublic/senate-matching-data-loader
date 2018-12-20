#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""unit tests for databank2hitch.py"""

import os
import unittest
from requests.auth import HTTPBasicAuth
import databank2hitch
import responses


def list_of_aliases():
    """list_of_aliases from DATABANK_SENATE_MATCHING_MAPPING"""
    res = []
    for field_def in databank2hitch.DATABANK_SENATE_MATCHING_MAPPING:
        for alias in databank2hitch.DATABANK_SENATE_MATCHING_MAPPING[field_def]['aliases']:
            res.append((alias, field_def))
    return res


def is_int(value):
    """is_int"""
    try:
        int(value)
    except ValueError:
        return False
    return True


class TestDatabank2Hitch(unittest.TestCase):
    """Databank2Hitch Test Class"""

    def test_find_matching_field(self):
        """test_find_matching_field"""
        for al_tuple in list_of_aliases():
            self.assertEqual(databank2hitch.find_matching_field(al_tuple[0]), al_tuple[1])
        for fake_element in ['invalid_test', 'my_email', 'a_phone_number', 123]:
            self.assertEqual(databank2hitch.find_matching_field(fake_element), None)

    def test_mandatory_field(self):
        """test_mandatory_field makes sure personid and natural_key are
        the only two mandatory aliases"""
        self.assertEqual(databank2hitch.list_mandatory_field_aliases(), {'personid': 'personid',
                                                                         'natural_key': 'personid'})

    def test_filter_and_translator(self):
        """test_filter_and_translator tests the normalization of a phone number and numeric"""
        convert_from = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        convert_to = "01234567892223334445556667777888999922233344455566677778889999"
        self.assertEqual(databank2hitch.filter_and_translator('+61468732838abc32',
                                                              convert_from,
                                                              convert_to),
                         '6146873283822232')
        self.assertEqual(databank2hitch.filter_and_translator('123abc456def',
                                                              '0123456789', ''),
                         '123456')

    def test_normalization(self):
        """test_normalization"""
        emails = [('test+DR@datarepublic.COM', 'test+dr@datarepublic.com'),
                  ('test+lower@datarepublic.com', 'test+lower@datarepublic.com'),
                  ('TEST+UPPER@DATAREPUBLIC.COM', 'test+upper@datarepublic.com')]
        for email in emails:
            self.assertEqual(databank2hitch.normalize(email[0], 'email'), email[1])

        uppers = [('testup', 'TESTUP'), ('TESTUP2', 'TESTUP2'), ('test3UP', 'TEST3UP')]
        for upper in uppers:
            self.assertEqual(databank2hitch.normalize(upper[0], 'uppercase'), upper[1])

        phones = [('+61468733920', '61468733920'), ('0130545029', '0130545029'),
                  ('+01AB0302CD', '0122030223')]
        for phone in phones:
            self.assertEqual(databank2hitch.normalize(phone[0], 'phone'), phone[1])

        integers = [('01032134209', '01032134209'), ('0102ABC03KF', '010203'), ('ABCdef0GHi', '0')]
        for integer in integers:
            out = databank2hitch.normalize(integer[0], 'int')
            self.assertEqual(out, integer[1])
            self.assertEqual(is_int(out), True)

        any_values = ['can_be_anything_012', 123, []]
        for value in any_values:
            self.assertEqual(databank2hitch.normalize(value, 'anything'), str(value))

    @responses.activate
    def test_retrieve_salts(self):
        """test_retrieve_salts"""
        hostname = 'http://localhost/'
        global_config = {
            "Databases": {
                "26e1587a-6a64-4d78-b7f5-fa3efbdebe67": {
                    "Fields": {
                        "1": {},
                        "2": {}
                    },
                    "DBName": "Database Two"
                }
            },
            "Fields": {
                "1": {
                    "FieldName": "email",
                    "NormalizationMethod": "email",
                    "HashSalt": "9da8b01a3ab64fcc8e39ebd5c4cf21e7"
                },
                "2": {
                    "FieldName": "phone",
                    "NormalizationMethod": "phone",
                    "HashSalt": "ff14d4eff61149c193d5b212f2c2d15b"
                }
            }
        }
        responses.add(responses.GET, hostname + 'GlobalConfig',
                      json=global_config, status=200)
        auth = HTTPBasicAuth('api', 'passw0rd')
        databank2hitch.retrieve_salts(hostname, auth, False)
        for tpl in [('email', '9da8b01a3ab64fcc8e39ebd5c4cf21e7'),
                    ('phone', 'ff14d4eff61149c193d5b212f2c2d15b')]:
            self.assertEqual(databank2hitch.DATABANK_SENATE_MATCHING_MAPPING[tpl[0]]['salt'],
                             tpl[1])

    def test_senate_hash(self):
        """test_senate_hash"""
        self.assertEqual(databank2hitch.senate_hash('email', 'anything'),
                         'H8RshG0mb5TVWhHKl28aH7xNZkLg23R/F6akSpHkS9E0joL'
                         'TPh4ueA0U19a0PzLyWZ8HhPbgPUnfosv4ncmePg==')

    def test_hitch_contributor_node_url(self):
        """test_hitch_contributor_node_url"""

        urls = [('https://localhost:5000', 'https://localhost:5000/api/Contributor/v1/'),
                ('contributor.datarepublic.com.au', 'https://contributor.datarepublic.com.au'
                                                    '/api/Contributor/v1/')]
        for url in urls:
            os.environ['HITCH_CONTRIBUTOR_NODE'] = url[0]
            self.assertEqual(databank2hitch.hitch_contributor_node_url(), url[1])

    def test_parse_headers(self):
        """test_parse_headers"""
        databank_headers = ['natural_key', 'phone', 'email', 'contact_email_address',
                            'fake_phone', 'contact_mobile_number']
        self.assertEqual(databank2hitch.parse_headers(databank_headers),
                         ['personid', 'phone:0', 'email:0', 'email:1', 'phone:1'])
        self.assertEqual(databank2hitch.MATCH, {'natural_key': 'personid', 'phone': 'phone:0',
                                                'email': 'email:0',
                                                'contact_email_address': 'email:1',
                                                'contact_mobile_number': 'phone:1'})


if __name__ == '__main__':
    unittest.main()
