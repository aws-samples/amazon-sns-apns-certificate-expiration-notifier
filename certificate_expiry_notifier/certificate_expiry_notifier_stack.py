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

from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions
)
from constructs import Construct

import os

# Permissions required by Lambda function
lambda_permissions = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "sns:ListPlatformApplications",
                "sns:Publish",
                "securityhub:DescribeHub",
                "securityhub:BatchImportFindings"
            ],
            "Resource": "*"
        }
    ]
}


class CertificateExpiryNotifierStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get CERT_EXPIRY_DAYS from cdk.json configuration file
        environment_variables = self.node.try_get_context("environment_variables")
        CERT_EXPIRY_DAYS = environment_variables.get("CERT_EXPIRY_DAYS")
        SNS_TOPIC_NAME = environment_variables.get("SNS_TOPIC_NAME")
        NOTIFY_EMAIL_ADDRESS = environment_variables.get("NOTIFY_EMAIL_ADDRESS")

        # Creating Lambda Execution Role
        notifier_lambda_role = iam.Role(self, "NotifierLambdaRole",
                                        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                                        description="Lambda Execution Role for Notifier Lambda",
                                        )

        # Creating Lambda Execution Policy
        notifier_lambda_policy = iam.Policy(self, "NotifierLambdaPolicy",
                                            document=iam.PolicyDocument.from_json(lambda_permissions)
                                            )

        notifier_lambda_policy.attach_to_role(notifier_lambda_role)

        # Adding email subscriber to SNS topic
        notifier_sns_topic = sns.Topic(self, "NotifierSNSTopic", topic_name=SNS_TOPIC_NAME)
        notifier_sns_topic.add_subscription(subscriptions.EmailSubscription(NOTIFY_EMAIL_ADDRESS))

        # Creating Lambda Function
        notifier_lambda = lambda_.Function(self, "NotifierLambda",
                                           code=lambda_.Code.from_asset(os.path.join("./", "notifier_lambda")),
                                           handler="lambda_function.lambda_handler",
                                           runtime=lambda_.Runtime.PYTHON_3_9,
                                           role=notifier_lambda_role,
                                           timeout=Duration.minutes(3),
                                           environment={
                                               "CERT_EXPIRY_DAYS": str(CERT_EXPIRY_DAYS),
                                               "SNS_TOPIC_ARN": notifier_sns_topic.topic_arn
                                           }
                                           )

        # Creating Event Rule that serves as a cron job
        notifier_rule = events.Rule(self, "NotifierRule",
                                    schedule=events.Schedule.rate(Duration.days(CERT_EXPIRY_DAYS)),
                                    targets=[targets.LambdaFunction(notifier_lambda)]
                                    )
