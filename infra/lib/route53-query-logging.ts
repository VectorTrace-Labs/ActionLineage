import * as cdk from 'aws-cdk-lib';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as route53 from 'aws-cdk-lib/aws-route53';
import { Construct } from 'constructs';

export function enableHostedZoneQueryLogging(
  scope: Construct,
  id: string,
  hostedZone: route53.PublicHostedZone,
  zoneName: string,
  options: { logGroupName?: string } = {}
) {
  const logGroup = new logs.LogGroup(scope, `${id}LogGroup`, {
    logGroupName: options.logGroupName ?? `/aws/route53/${zoneName}`,
    retention: logs.RetentionDays.ONE_YEAR,
    removalPolicy: cdk.RemovalPolicy.RETAIN
  });

  const hostedZoneArnPattern = `arn:${cdk.Aws.PARTITION}:route53:::hostedzone/*`;

  const resourcePolicy = new logs.CfnResourcePolicy(scope, `${id}LogResourcePolicy`, {
    policyName: `${id}Route53QueryLogs`,
    policyDocument: JSON.stringify({
      Version: '2012-10-17',
      Statement: [
        {
          Sid: 'AllowRoute53QueryLogDelivery',
          Effect: 'Allow',
          Principal: {
            Service: 'route53.amazonaws.com'
          },
          Action: ['logs:CreateLogStream', 'logs:PutLogEvents'],
          Resource: `${logGroup.logGroupArn}:*`,
          Condition: {
            StringEquals: {
              'aws:SourceAccount': cdk.Aws.ACCOUNT_ID
            },
            ArnLike: {
              'aws:SourceArn': hostedZoneArnPattern
            }
          }
        }
      ]
    })
  });

  const hostedZoneResource = hostedZone.node.defaultChild as route53.CfnHostedZone;
  hostedZoneResource.queryLoggingConfig = {
    cloudWatchLogsLogGroupArn: logGroup.logGroupArn
  };
  hostedZoneResource.node.addDependency(logGroup);
  hostedZoneResource.node.addDependency(resourcePolicy);

  return logGroup;
}
