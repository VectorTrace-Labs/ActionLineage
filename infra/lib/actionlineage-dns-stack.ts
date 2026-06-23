import * as cdk from 'aws-cdk-lib';
import { Stack, StackProps } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as route53 from 'aws-cdk-lib/aws-route53';
import { Construct } from 'constructs';
import { enableHostedZoneQueryLogging } from './route53-query-logging.js';

export interface ActionLineageDnsStackProps extends StackProps {
  domainName: string;
}

export class ActionLineageDnsStack extends Stack {
  public readonly hostedZone: route53.PublicHostedZone;

  constructor(scope: Construct, id: string, props: ActionLineageDnsStackProps) {
    super(scope, id, props);

    this.hostedZone = new route53.PublicHostedZone(this, 'HostedZone', {
      zoneName: props.domainName,
      comment: `DNS zone for ${props.domainName}.`
    });
    enableHostedZoneQueryLogging(this, 'ActionLineageDns', this.hostedZone, props.domainName, {
      logGroupName: `/aws/route53/${props.domainName}-v2`
    });

    new route53.CaaAmazonRecord(this, 'AmazonCertificateAuthorityAuthorization', {
      zone: this.hostedZone,
      recordName: props.domainName,
      ttl: cdk.Duration.hours(1)
    });

    new route53.TxtRecord(this, 'GitHubOrgDomainVerification', {
      zone: this.hostedZone,
      recordName: `_gh-vectortrace-labs-o.${props.domainName}`,
      values: ['e9bfe04ed4'],
      ttl: cdk.Duration.minutes(5)
    });

    const dnssecHostedZoneArn = `arn:${cdk.Aws.PARTITION}:route53:::hostedzone/${this.hostedZone.hostedZoneId}`;
    const dnssecKey = new kms.Key(this, 'DnssecKey', {
      alias: `alias/${props.domainName.replaceAll('.', '-')}-dnssec-ksk-v2`,
      description: `DNSSEC key-signing key backing key for ${props.domainName}.`,
      keySpec: kms.KeySpec.ECC_NIST_P256,
      keyUsage: kms.KeyUsage.SIGN_VERIFY,
      removalPolicy: cdk.RemovalPolicy.RETAIN
    });

    const route53DnssecPrincipal = new iam.ServicePrincipal('dnssec-route53.amazonaws.com');

    dnssecKey.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'AllowRoute53DNSSECService',
        principals: [route53DnssecPrincipal],
        actions: ['kms:DescribeKey', 'kms:GetPublicKey', 'kms:Sign'],
        resources: ['*'],
        conditions: {
          StringEquals: {
            'aws:SourceAccount': cdk.Aws.ACCOUNT_ID
          },
          ArnEquals: {
            'aws:SourceArn': dnssecHostedZoneArn
          }
        }
      })
    );

    dnssecKey.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'AllowRoute53DNSSECGrant',
        principals: [route53DnssecPrincipal],
        actions: ['kms:CreateGrant'],
        resources: ['*'],
        conditions: {
          Bool: {
            'kms:GrantIsForAWSResource': true
          },
          StringEquals: {
            'aws:SourceAccount': cdk.Aws.ACCOUNT_ID
          },
          ArnEquals: {
            'aws:SourceArn': dnssecHostedZoneArn
          }
        }
      })
    );

    const keySigningKey = new route53.CfnKeySigningKey(this, 'DnssecKeySigningKey', {
      hostedZoneId: this.hostedZone.hostedZoneId,
      keyManagementServiceArn: dnssecKey.keyArn,
      name: `${props.domainName.replaceAll('.', '_')}_ksk_2026_v2`,
      status: 'ACTIVE'
    });

    const dnssec = new route53.CfnDNSSEC(this, 'DnssecSigning', {
      hostedZoneId: this.hostedZone.hostedZoneId
    });
    dnssec.node.addDependency(keySigningKey);

    new cdk.CfnOutput(this, 'Route53NameServers', {
      value: cdk.Fn.join(', ', this.hostedZone.hostedZoneNameServers ?? []),
      description: `Set these as the authoritative nameservers at Namecheap for ${props.domainName}.`
    });

    new cdk.CfnOutput(this, 'DnssecKeySigningKeyName', {
      value: keySigningKey.name,
      description: `Route 53 DNSSEC KSK name for ${props.domainName}.`
    });
  }
}
