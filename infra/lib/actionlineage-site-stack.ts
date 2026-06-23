import * as path from 'node:path';
import * as cdk from 'aws-cdk-lib';
import { Stack, StackProps } from 'aws-cdk-lib';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as route53Targets from 'aws-cdk-lib/aws-route53-targets';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';

export interface ActionLineageSiteStackProps extends StackProps {
  domainName: string;
  hostedZone: route53.IHostedZone;
  webAclArn?: string;
  siteBuildPath?: string;
}

export class ActionLineageSiteStack extends Stack {
  constructor(scope: Construct, id: string, props: ActionLineageSiteStackProps) {
    super(scope, id, props);

    const siteBuildPath = props.siteBuildPath ?? 'dist';
    const siteBucket = new s3.Bucket(this, 'SiteBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      lifecycleRules: [
        {
          id: 'RetainRecentDeploymentVersions',
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
          noncurrentVersionsToRetain: 10,
          noncurrentVersionExpiration: cdk.Duration.days(30)
        }
      ],
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN
    });

    const logBucket = new s3.Bucket(this, 'LogBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      lifecycleRules: [
        {
          id: 'ExpireAccessLogs',
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
          expiration: cdk.Duration.days(180)
        }
      ],
      objectOwnership: s3.ObjectOwnership.OBJECT_WRITER,
      removalPolicy: cdk.RemovalPolicy.RETAIN
    });

    const responseHeadersPolicy = new cloudfront.ResponseHeadersPolicy(this, 'SecurityHeadersPolicy', {
      responseHeadersPolicyName: 'ActionLineageSecurityHeaders',
      comment: 'Security headers for the ActionLineage public website.',
      customHeadersBehavior: {
        customHeaders: [
          {
            header: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()',
            override: true
          },
          {
            header: 'Cross-Origin-Opener-Policy',
            value: 'same-origin',
            override: true
          },
          {
            header: 'Cross-Origin-Resource-Policy',
            value: 'same-origin',
            override: true
          }
        ]
      },
      securityHeadersBehavior: {
        contentSecurityPolicy: {
          override: true,
          contentSecurityPolicy:
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://api.github.com https://raw.githubusercontent.com; media-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests"
        },
        contentTypeOptions: { override: true },
        frameOptions: {
          frameOption: cloudfront.HeadersFrameOption.DENY,
          override: true
        },
        referrerPolicy: {
          referrerPolicy: cloudfront.HeadersReferrerPolicy.SAME_ORIGIN,
          override: true
        },
        strictTransportSecurity: {
          accessControlMaxAge: cdk.Duration.days(365),
          includeSubdomains: true,
          preload: true,
          override: true
        },
        xssProtection: {
          protection: false,
          override: true
        }
      }
    });

    const certificate = new acm.Certificate(this, 'Certificate', {
      domainName: props.domainName,
      subjectAlternativeNames: [`www.${props.domainName}`],
      validation: acm.CertificateValidation.fromDns(props.hostedZone)
    });

    const canonicalHostRedirectFunction = new cloudfront.Function(this, 'CanonicalHostRedirectFunction', {
      comment: `Redirect www.${props.domainName} to ${props.domainName}.`,
      code: cloudfront.FunctionCode.fromInline(`
function handler(event) {
  var request = event.request;
  var host = request.headers.host && request.headers.host.value;

  if (host !== 'www.${props.domainName}') {
    return routeRequest(request);
  }

  var querystring = request.querystring || {};
  var queryParts = [];

  for (var key in querystring) {
    if (!Object.prototype.hasOwnProperty.call(querystring, key)) {
      continue;
    }

    var value = querystring[key];

    if (value.multiValue) {
      for (var index = 0; index < value.multiValue.length; index += 1) {
        queryParts.push(key + (value.multiValue[index].value ? '=' + value.multiValue[index].value : ''));
      }
    } else {
      queryParts.push(key + (value.value ? '=' + value.value : ''));
    }
  }

  return {
    statusCode: 301,
    statusDescription: 'Moved Permanently',
    headers: {
      location: {
        value: 'https://${props.domainName}' + request.uri + (queryParts.length ? '?' + queryParts.join('&') : '')
      }
    }
  };
}

function routeRequest(request) {
  if (request.uri === '/robots.txt') {
    request.uri = '/actionlineage-robots.txt';
    return request;
  }

  if (request.uri === '/sitemap.xml') {
    request.uri = '/actionlineage-sitemap.xml';
    return request;
  }

  var appRoutes = {
    '/': true,
    '/actionlineage': true,
    '/actionlineage/': true
  };

  if (appRoutes[request.uri]) {
    request.uri = '/index.html';
  }

  return request;
}
`)
    });

    const webAclId =
      props.webAclArn ??
      cdk.Fn.importValue('VectorTraceEdgeSecurityStack:ExportsOutputFnGetAttEdgeWebAclArnD5C4C2FE');

    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      comment: 'ActionLineage public website',
      defaultRootObject: 'index.html',
      domainNames: [props.domainName, `www.${props.domainName}`],
      certificate,
      enableLogging: true,
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      errorResponses: [
        {
          httpStatus: 403,
          responseHttpStatus: 404,
          responsePagePath: '/index.html',
          ttl: cdk.Duration.minutes(5)
        },
        {
          httpStatus: 404,
          responseHttpStatus: 404,
          responsePagePath: '/index.html',
          ttl: cdk.Duration.minutes(5)
        }
      ],
      logBucket,
      logFilePrefix: 'cloudfront/',
      logIncludesCookies: false,
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      webAclId,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD,
        compress: true,
        functionAssociations: [
          {
            function: canonicalHostRedirectFunction,
            eventType: cloudfront.FunctionEventType.VIEWER_REQUEST
          }
        ],
        responseHeadersPolicy
      }
    });

    new s3deploy.BucketDeployment(this, 'DeployWebsite', {
      sources: [s3deploy.Source.asset(path.join(process.cwd(), siteBuildPath))],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
      prune: true,
      retainOnDelete: false
    });

    for (const recordName of [props.domainName, `www.${props.domainName}`]) {
      new route53.ARecord(this, `${recordName.replaceAll('.', '')}ARecord`, {
        zone: props.hostedZone,
        recordName,
        target: route53.RecordTarget.fromAlias(new route53Targets.CloudFrontTarget(distribution))
      });

      new route53.AaaaRecord(this, `${recordName.replaceAll('.', '')}AaaaRecord`, {
        zone: props.hostedZone,
        recordName,
        target: route53.RecordTarget.fromAlias(new route53Targets.CloudFrontTarget(distribution))
      });
    }

    new cdk.CfnOutput(this, 'ActionLineageUrl', {
      value: `https://${props.domainName}`,
      description: 'Canonical ActionLineage website URL.'
    });

    new cdk.CfnOutput(this, 'CloudFrontUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Live CloudFront URL for the ActionLineage website.'
    });

    new cdk.CfnOutput(this, 'DistributionId', {
      value: distribution.distributionId,
      description: 'CloudFront distribution ID for the ActionLineage website.'
    });
  }
}
