# Senate Matching Data Loader

A tool to load data from a CSV file into a Senate Matching Contributor Node.
This tool needs to be run on a computer that has access to the Internet.

**Note**
This tool has only been tested with MacOS and we assume it works with Linux and Windows too. Please report any issues back to [Data Republic](support@datarepublic.com).

# Description

The tool accepts a CSV file that uses pre-defined column names supported by Senate Matching and Westpac Databank, hashes and loads the data into a Contributor Node, and outputs the mapping between *natural_key* and *token*.

**Note**
If the data is already hashed, set flag `--hashed` to True to avoid double hashing which will affect matching results.

The endpoint of the Contributor Node is expected to be in the environment variable *HITCH_CONTRIBUTOR_NODE*.

**For customers migrating from Westpac Databank projects:** valid Databank column names will be converted to the equivalent Senate Matching ones.

The following process is followed:
1. Input CSV is parsed. A header row is required.
2. Westpac Databank column names (e.g. *contact_email_address*) is mapped to the equivalent Senate Matching column name (e.g. *email*).
3. In Senate Matching, a field may have multiple values, so sometimes multiple Westpac Databank columns are mapped to the same Senate Matching field.
4. The program will then salt and hash the PI fields before uploading the data to the Contributor Node.
5. Uploads are synchronous, the program will wait until the upload has completed successfully and return 0 on success, non-zero on failure (see EXIT CODES).
6. Optionally, the mapping between *natural_key* (Senate Matching uses the field name *person_id*) and *token* will be fetched and saved in CSV format to the file specified by **-o**.

# Prerequisite
- [Python3](https://www.python.org/)
- [pipenv version 2018.11.26](https://pipenv.kennethreitz.org/en/latest/)
- **Optionally** if you need to convert Asian wide character strings to narrow character strings
  - [Go 1.13.4](https://golang.org/)
  - [GNU Make](https://www.gnu.org/software/make/)

# Installation
## Dependencies
Run `pipenv install` to install all dependencies.

## Environmental Variables
Run `cp .env{.sample,}` and set the variables correctly in `.env` file.

- **HITCH_CONTRIBUTOR_NODE**
: URL to your Contributor Node.

- **HITCH_API_KEY**
:	The API key for the Contributor Node you are uploading to.

## Wide character strings
If your csv file contains Asian wide character strings you will need to convert them to the narrow format. A separate tool is provided to make it easier.
Make sure you have `make` and correct `Go` runtime working then run `make go` to generate the tool. You should see a binary file called `tonarrow` generated in
the root folder. It will automatically be called by the Python script when it is necessary.

# Running
Simply run `pipenv run python ./dataloader.py` with following options:

- -u, --uuid
: **Required** To specify UUID of the Senate Matching database to write data to.

- -i, --input
: To specify the file to read from. The file must be readable and in CSV format (see INPUT FORMAT below). Default to stdin.

- -o, --output
:	To specify the file to Write the token mapping to when upload is complete. The mapping file will be in CSV format. Default to stdout.

- -d, --delimiter
: To specify the CSV delimiter. Default to comma.

- --hashed
: Set to True if the non-primary fields in source file have been hashed to prevent double hashing, which could cause poor matching rate. Default to False.

# Input Format

The input file should be formatted in CSV (comma separated, double quote escape character, Unix or Windows line endings). String encoding is expected to be UTF-8.

The first line must be a header row. Column names are case insensitive. The order of columns is not significant, and both Senate Matching and Westpac Databank column names are accepted.

**For customers migrating from Westpac Databank projects:**

Note that one difference between Databank and Senate Matching is that the latter accepts multiple values per field. So both *contact_email_address* and *alternate_email_address* are mapped to the Senate Matching field *email*. Both values will then be used in later match requests.

Not all Databank fields have a Senate Matching equivalent. For example the multiple fields for tracking an address (street, suburb, state, etc.) are replaced by the single field *DPID*. Some other fields with low cardinality (e.g. gender) are not used at all.

Unexpected column names will produce a warning (printed on stderr) and their values will be ignored, but the program will otherwise continue.

Standard column names and their Databank aliases are given below:

* personid: natural_key
* family_name: family_names
* given_name: first_name
* email: contact_email_address, alternate_email_address
* phone: contact_mobile_number, alternate_mobile_number, 
  contact_landline_number, alternate_landline_number
* dpid: contact_aus_dpid, alternate_aus_dpid

Ignored fields are:

* initial
* middle_names
* gender
* date_of_birth
* contact_suburb_name, contact_state, contact_postcode, contact_country_code
* alternate_suburb_name, alternate_state, alternate_postcode, 
  alternate_country_code

# Exit Codes
- 0
:	All data successfully uploaded to Contributor Node.

- 1
:	Error encountered in the input CSV. For example, malformed CSV
	or missing header row. Input must be fixed before trying again.

- 2
:	Error returned by Contributor Node when uploading data. Check
	stderr for details. Could be caused by Contributor Node not
	having access to the Matcher Node network.

- 3
:	Any other error (e.g. incorrect API key, or cannot connect to
    Contributor Node).

# Contact

Contact [Data Republic](support@datarepublic.com) for any questions, feedbacks or bugs.

# License

This library is distributed under the Data Republic Senate Matching License.
