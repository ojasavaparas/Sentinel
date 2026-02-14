"""Sentinel ECS Fargate stack — VPC, ALB, ECS, ECR, Route 53, auto-scaling."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_certificatemanager as acm,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecr as ecr,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_elasticloadbalancingv2 as elbv2,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_route53 as route53,
)
from aws_cdk import (
    aws_route53_targets as targets,
)
from constructs import Construct


class SentinelStack(Stack):
    """AWS CDK stack deploying Sentinel on ECS Fargate with ALB, ECR, and Route 53."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        domain_name = self.node.try_get_context("domain_name") or "agent.ojasavaparas.com"
        hosted_zone_name = self.node.try_get_context("hosted_zone_name") or "ojasavaparas.com"

        # ----------------------------------------------------------------------
        # VPC — 2 AZs, public + private subnets, 1 NAT gateway
        # ----------------------------------------------------------------------
        vpc = ec2.Vpc(
            self,
            "SentinelVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # ----------------------------------------------------------------------
        # ECS Cluster
        # ----------------------------------------------------------------------
        cluster = ecs.Cluster(
            self,
            "SentinelCluster",
            vpc=vpc,
            cluster_name="sentinel-cluster",
        )

        # ----------------------------------------------------------------------
        # ECR Repository (import existing — created outside CDK)
        # ----------------------------------------------------------------------
        repository = ecr.Repository.from_repository_name(
            self, "SentinelRepo", "sentinel"
        )

        # ----------------------------------------------------------------------
        # CloudWatch Log Group
        # ----------------------------------------------------------------------
        log_group = logs.LogGroup(
            self,
            "SentinelLogs",
            log_group_name="/ecs/sentinel",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ----------------------------------------------------------------------
        # Route 53 Hosted Zone + ACM Certificate
        # ----------------------------------------------------------------------
        hosted_zone = route53.HostedZone.from_lookup(
            self,
            "HostedZone",
            domain_name=hosted_zone_name,
        )

        certificate = acm.Certificate(
            self,
            "SentinelCert",
            domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # ----------------------------------------------------------------------
        # Fargate Task Definition
        # ----------------------------------------------------------------------
        task_definition = ecs.FargateTaskDefinition(
            self,
            "SentinelTask",
            cpu=512,
            memory_limit_mib=1024,
        )

        container = task_definition.add_container(
            "sentinel-api",
            image=ecs.ContainerImage.from_ecr_repository(repository, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="sentinel",
                log_group=log_group,
            ),
            environment={
                "LLM_PROVIDER": "anthropic",
                "LLM_MODEL": "claude-sonnet-4-20250514",
                "ANTHROPIC_API_KEY": self.node.try_get_context("anthropic_api_key") or "",
                "LOG_FORMAT": "json",
            },
            health_check=ecs.HealthCheck(
                command=[
                    "CMD-SHELL",
                    "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')\"",
                ],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
        )

        # ----------------------------------------------------------------------
        # Security Groups
        # ----------------------------------------------------------------------
        alb_sg = ec2.SecurityGroup(
            self,
            "AlbSg",
            vpc=vpc,
            description="ALB security group - allow HTTP/HTTPS from anywhere",
            allow_all_outbound=True,
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP")
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS")

        fargate_sg = ec2.SecurityGroup(
            self,
            "FargateSg",
            vpc=vpc,
            description="Fargate security group - allow traffic only from ALB",
            allow_all_outbound=True,
        )
        fargate_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8000), "From ALB")

        # ----------------------------------------------------------------------
        # Application Load Balancer
        # ----------------------------------------------------------------------
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "SentinelAlb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
            idle_timeout=Duration.seconds(120),
        )

        # HTTPS listener
        https_listener = alb.add_listener(
            "HttpsListener",
            port=443,
            certificates=[certificate],
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404, content_type="text/plain", message_body="Not found"
            ),
        )

        # HTTP → HTTPS redirect
        alb.add_listener(
            "HttpRedirect",
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True,
            ),
        )

        # ----------------------------------------------------------------------
        # Fargate Service
        # ----------------------------------------------------------------------
        fargate_service = ecs.FargateService(
            self,
            "SentinelService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
            security_groups=[fargate_sg],
            assign_public_ip=False,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # Register with ALB target group
        https_listener.add_targets(
            "SentinelTargets",
            port=8000,
            targets=[fargate_service],
            health_check=elbv2.HealthCheck(
                path="/api/v1/health",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                healthy_http_codes="200",
            ),
            priority=1,
            conditions=[elbv2.ListenerCondition.path_patterns(["/*"])],
        )

        # ----------------------------------------------------------------------
        # Auto-Scaling — min 0, max 2, scale on CPU > 70%
        # ----------------------------------------------------------------------
        scaling = fargate_service.auto_scale_task_count(
            min_capacity=0,
            max_capacity=2,
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(60),
        )

        # ----------------------------------------------------------------------
        # Route 53 A Record
        # ----------------------------------------------------------------------
        route53.ARecord(
            self,
            "SentinelDns",
            zone=hosted_zone,
            record_name=domain_name,
            target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb)),
        )

        # ----------------------------------------------------------------------
        # Outputs
        # ----------------------------------------------------------------------
        cdk.CfnOutput(self, "AlbDnsName", value=alb.load_balancer_dns_name)
        cdk.CfnOutput(self, "EcrRepoUri", value=repository.repository_uri)
        cdk.CfnOutput(self, "ServiceUrl", value=f"https://{domain_name}")
