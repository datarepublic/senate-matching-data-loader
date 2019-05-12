NAME
====

**databank2hitch** — Loads a CSV that uses Databank column names into a Hitch (Senate Matching) Contributor Node


SYNOPSIS
========

| **databank2hitch** \[**-i**|**--input** _file_] \[**-o**|**--output** _file_]
| **databank2hitch** \[**-h**|**--help**]


DESCRIPTION
===========

Accepts a CSV file that uses Databank column names, loads the data into
a Contributor Node, and outputs the mapping between *natural_key* and
*token*. The location of the Contributor Node is expected to be in the
environment variable *HITCH_CONTRIBUTOR_NODE* (see ENVIRONMENT, below).

The following process is followed:
1. Input CSV is parsed. A header row is required.
2. Databank column names (e.g. *contact_email_address*) is mapped to
   the equivalent Senate Matching column name (e.g. *email*).
3. In Senate Matching, a field may have multiple values, so sometimes
   multiple Databank columns are mapped to the same Senate Matching
   field.
4. The program will then salt and hash the PI fields before uploading
   the data to the Contributor Node.
5. Uploads are synchronous, the program will wait until the upload
   has completed successfully and return 0 on success, non-zero on 
   failure (see EXIT CODES).
6. Optionally, the mapping between *natural_key* (Hitch uses the field
   name *person_id*) and *token* will be fetched and saved in CSV
   format to the file specified afer **-o**,


Options
-------

-h, --help
:   Prints brief usage information.

-i, --input
:   Read from filename (otherwise reads from stdin) The file must be 
    readable and in CSV format (see INPUT FORMAT below).

-o, --output
:	Write the mapping file to filename when upload is complete. The
	mapping file will be in CSV format. Use "-" to write to stdout.


INPUT FORMAT
============

The input file should be formatted in CSV (comma separated, double 
quote escape character, Unix or Windows line endings). String encoding
is expected to be UTF-8.

The first line must be a header row. Column names are case insensitive.
The order of columns is not significant, and both Hitch and Databank
column names are accepted.

Note that one difference between Databank and Hitch is that the latter 
accepts multiple values per field. So both *contact_email_address* and
*alternate_email_address* are mapped to the Hitch field *email*. Both
values will then be used in later match requests.

Not all Databank fields have a Hitch equivalent. For example the multiple
fields for tracking an address (street, suburb, state, etc.) are replaced
by the single field DPID. Some other fields with low cardinality (e.g. gender)
are not used at all.

Unexpected column names will produce a warning (printed on stderr) and
their values will be ignored, but the program will otherwise continue.

Standard column names and their Databank aliases are given below:

* personid: natural_key
* family_name: family_names
* given_name: first_name
* email: contact_email_address, alternate_email_address
* phone: contact_mobile_number, alternate_mobile_number, 
  contact_landline_number, alternate_landline_number
* dpid: contact_aus_dpid, alternate_aus_dpid

Ignored fields:

* initial
* middle_names
* gender
* date_of_birth
* contact_suburb_name, contact_state, contact_postcode, contact_country_code
* alternate_suburb_name, alternate_state, alternate_postcode, 
  alternate_country_code



EXIT CODES
==========

0
:	All data successfully uploaded to Contributor Node.

1
:	Error encountered in the input CSV. For example, malformed CSV
	or missing header row. Input must be fixed before trying again.

2
:	Error returned by Contributor Node when uploading data. Check
	stderr for details. Could be caused by Contributor Node not
	having access to the Matcher Node network.

3
:	Any other error (e.g. incorrect API key, or cannot connect to
    Contributor Node).


ENVIRONMENT
===========

**HITCH_CONTRIBUTOR_NODE**
:   URL to your Contributor Node (eg. https://10.1.2.3/

**HITCH_API_KEY**
:	The API key for the Contributor Node you are uploading to.


BUGS
====

Zaro Boogs found.


AUTHOR
======

Data Republic <support@datarepublic.com>


LICENSE
=======

Released under the Data Republic Senate Matching License.
