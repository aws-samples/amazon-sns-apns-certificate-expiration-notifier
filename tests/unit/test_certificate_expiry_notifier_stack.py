import aws_cdk as core
import aws_cdk.assertions as assertions

from certificate_expiry_notifier.certificate_expiry_notifier_stack import CertificateExpiryNotifierStack

# example tests. To run these tests, uncomment this file along with the example
# resource in certificate_expiry_notifier/certificate_expiry_notifier_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = CertificateExpiryNotifierStack(app, "certificate-expiry-notifier")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
