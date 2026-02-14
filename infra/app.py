#!/usr/bin/env python3
"""CDK app entry point for Sentinel infrastructure."""

import aws_cdk as cdk
from stack import SentinelStack

app = cdk.App()

SentinelStack(
    app,
    "SentinelStack",
    env=cdk.Environment(
        account="392746353271",
        region="us-east-1",
    ),
)

app.synth()
