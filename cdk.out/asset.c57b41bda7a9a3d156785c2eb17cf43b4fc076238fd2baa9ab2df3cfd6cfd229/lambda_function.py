# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import json
import boto3
import os
import re
from datetime import datetime, timedelta, timezone

# -------------------------------------------
# setup global variable data
# -------------------------------------------
utc = timezone.utc

# make today timezone aware
today = datetime.now()
# set up time window for alert - default to 15 if its missing
if os.environ.get('CERT_EXPIRY_DAYS') is None:
    expiry_days = 15
else:
    expiry_days = int(os.environ['CERT_EXPIRY_DAYS'])

print(f'The configured cert expiration days is {expiry_days}')

expiry_window = today + timedelta(days = expiry_days)

print(f'The expiry window is {expiry_window}')

def lambda_handler(event, context):
    
    response = handle_apns_cert_expiration (event)
    
    return {
        'statusCode': 200,
        'body': response 
    }


def handle_apns_cert_expiration(event):
    
    # sns client  
    sns_client = boto3.client('sns')
    try:
        paginator = sns_client.get_paginator('list_platform_applications')
        # creating a PageIterator from the paginator
        page_iterator = paginator.paginate().build_full_result()
        platform_application_list = []
        # loop through each page from page_iterator
        for page in page_iterator['PlatformApplications']:
         if page['PlatformApplicationArn'] is not None:
            if re.search('/APNS/', page['PlatformApplicationArn']) or re.search('/APNS_SANDBOX/', page['PlatformApplicationArn']): 
               print('The platform application is ' + page['PlatformApplicationArn'])
               if(page['Attributes']['Enabled'] and page['Attributes']['Enabled'] == 'true'):
                    cert_expiry_date = datetime.strptime(page['Attributes']['AppleCertificateExpirationDate'], '%Y-%m-%dT%H:%M:%SZ')
                    print(f'The certificate expiry date for this platform application is {cert_expiry_date}')
                    if cert_expiry_date < expiry_window and cert_expiry_date > today:
                        result = 'The APNS certificate is about to expiry for the platform application' + ' - ' + page['PlatformApplicationArn'] + ' within ' + str(expiry_days) + ' days.'
                        # if there's an SNS topic, publish a notification to it
                        if os.environ.get('SNS_TOPIC_ARN') is None: 
                            response = result
                        else:
                            response = sns_client.publish(TopicArn=os.environ['SNS_TOPIC_ARN'], Message=result, Subject='Certificate Expiration Notification')
                        
                        # create new finding in security hub 
                        create_security_hub_finding(event, page['PlatformApplicationArn'])

    except:
        raise
        logger.exception(f'Could not list SNS platform applications.')
    return 'success'

# function to create a finding in security hub 
# BatchImportFindings API operation used to create new findings
def create_security_hub_finding(event, sns_apns_application_arn):
    
    # security hub parameters 
    security_hub_region = event['region']
    security_hub_arn = "arn:aws:securityhub:{0}:{1}:hub/default".format(security_hub_region, event['account'])
    security_hub_product_arn = "arn:aws:securityhub:{0}:{1}:product/{1}/default".format(security_hub_region, event['account'])

    # check if security hub is enabled 
    security_hub_client = boto3.client('securityhub', region_name = security_hub_region)
    try:
        security_hub_enabled = security_hub_client.describe_hub(HubArn = security_hub_arn)

    # if security hub is not enabled throw an error
    except Exception as error:
        security_hub_enabled = None
        print ('Default Security Hub product doesn\'t exist')
        response = 'Security Hub disabled'

    if security_hub_enabled:
        # findings list
        findings_list = []

        # add SNS platform application to finding list
        findings_list.append({
            "SchemaVersion": "2018-10-08",
            "AwsAccountId": event['account'],
            "Title": "APNS Certificate Expiration",
            "Description": "Apple Push Notification Certificate Expirations used in Amazon SNS Platform Application",
            "GeneratorId": "Amazon SNS APNS Certificate Expiration Lambda Function ARN",
            "Id": sns_apns_application_arn,
            "ProductArn": security_hub_product_arn,
            "CompanyName": "AWS",
            "ProductName": "Amazon SNS",
            "CreatedAt": event['time'],
            "UpdatedAt": event['time'],
            "Types": [
                "Software and Configuration Checks/Amazon SNS APNS Certificate"
            ],
            "Resources": [{
                "Id": sns_apns_application_arn,
                "Partition": "aws",
                "Region": event['region'],
                "Type": "Amazon SNS APNS Platform Application"
            }],
            "Severity": {
                "Label": "HIGH"
            },
            "Compliance": {
                "Status": "WARNING"
            },
            "Remediation": {
                "Recommendation": {
                    "Text": "Please update certificate of Amazon SNS APNS Platform Application",
                    "Url": "https://console.aws.amazon.com/sns/home?region=" + event['region'] + "#/mobile/app/" + sns_apns_application_arn
                }
            }
        })
    
        # create a finding in security hub
        if findings_list:
            try:
                response = security_hub_client.batch_import_findings(Findings=findings_list)
                print('The security findings are published now')
                if response['FailedCount'] > 0:
                    print("Failed to import {} findings".format(response['FailedCount']))
    
            except Exception as error:
                print("Error: ", error)
                raise
            
    return json.dumps(response)
