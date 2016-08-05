#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import sys
import json
import time
import os.path
import logging
import boto3
from utils import get_account_id
from socket import gethostbyname, gaierror

def printException():
    exc_type, exc_value = sys.exc_info()[:2]
    logging.error('Exception "%s" occured with message "%s"', exc_type.__name__, exc_value)

# Default logging config
logging.basicConfig(format='%(asctime)s - %(levelname)s : %(message)s', level=logging.INFO, datefmt='%H:%M:%S')

# Get arguments
if len(sys.argv) >= 2:
    vaultName = sys.argv[1]
else:
    # If there are missing arguments, display usage example and exit
    logging.error('Usage: %s [<vault_name>|LIST] [DEBUG]', sys.argv[0])
    sys.exit(1)

# Get custom logging level
if len(sys.argv) == 3 and sys.argv[2] == 'DEBUG':
    logging.info('Logging level set to DEBUG.')
    logging.getLogger().setLevel(logging.DEBUG)

try:
    logging.info('Connecting to Amazon Glacier...')
    glacier = boto3.resource('glacier')
except:
    printException()
    sys.exit(1)

if vaultName == 'LIST':
    try:
        logging.info('Getting list of vaults...')
        vaults = glacier.vaults.all()
    except:
        printException()
        sys.exit(1)

    for vault in vaults:
        logging.info(vault.name)
        logging.info(vault.account_id)

    exit(0)

try:
    logging.info('Getting selected vault...')
    vault = glacier.Vault('-', vaultName)
except:
    printException()
    sys.exit(1)

logging.info('Getting jobs list...')
jobList = vault.jobs.all()
jobID = ''

# Check if a job already exists
for job in jobList:
    logging.debug('Job ID: {}, action: {}'.format(job.id, job.action))
    if job.action == 'InventoryRetrieval':
        logging.info('Found existing inventory retrieval job...')
        jobID = job.id

if jobID == '':
    logging.info('No existing job found, initiate inventory retrieval...')
    try:
        jobID = vault.initiate_inventory_retrieval()
    except:
        printException()
        sys.exit(1)

logging.debug('Job ID : %s', jobID)

# Get job status
job = vault.Job(jobID)

while job.status_code == 'InProgress':
    logging.info('Inventory not ready, sleep for 30 mins...')

    time.sleep(60*30)

    job = vault.Job(jobID)

if job.status_code == 'Succeeded':
    logging.info('Inventory retrieved, parsing data...')
    resp = job.get_output()
    content = resp['body'].read()
    inventory = json.loads(content.decode('utf-8'))

    logging.info('Removing archives... please be patient, this may take some time...');
    for archive in inventory['ArchiveList']:
        if archive['ArchiveId'] != '':
            logging.debug('Remove archive ID : %s', archive['ArchiveId'])
            try:
                vault.Archive(archive['ArchiveId']).delete()
            except:
                printException()

                logging.info('Sleep 2 mins before retrying...')
                time.sleep(60*2)

                logging.info('Retry to remove archive ID : %s', archive['ArchiveId'])
                try:
                    vault.Archive(archive['ArchiveId']).delete()
                    logging.info('Successfully removed archive ID : %s', archive['ArchiveId'])
                except:
                    logging.error('Cannot remove archive ID : %s', archive['ArchiveId'])

    logging.info('Removing vault...')
    try:
        vault.delete()
        logging.info('Vault removed.')
    except:
        printException()
        logging.error('We can’t remove the vault now. Please wait some time and try again. You can also remove it from the AWS console, now that all archives have been removed.')

else:
    logging.info('Vault retrieval failed.')
