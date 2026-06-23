#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { ActionLineageDnsStack } from '../lib/actionlineage-dns-stack.js';
import { ActionLineageSiteStack } from '../lib/actionlineage-site-stack.js';

const app = new cdk.App();

const account = process.env.CDK_DEFAULT_ACCOUNT ?? '925091290061';
const region = process.env.CDK_DEFAULT_REGION ?? 'us-east-1';
const domainName = app.node.tryGetContext('domainName') ?? 'actionlineage.dev';
const webAclArn = app.node.tryGetContext('webAclArn');
const env = { account, region };

const dnsStack = new ActionLineageDnsStack(app, 'ActionLineageDnsStack', {
  env,
  domainName,
  terminationProtection: true
});

new ActionLineageSiteStack(app, 'ActionLineageSiteStack', {
  env,
  domainName,
  hostedZone: dnsStack.hostedZone,
  webAclArn,
  terminationProtection: true
});
