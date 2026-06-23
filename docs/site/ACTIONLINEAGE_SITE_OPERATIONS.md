# ActionLineage Site Operations

## Canonical URLs

- `https://actionlineage.dev`
- `https://www.actionlineage.dev` redirects to the apex host.
- `https://vectortracelabs.com/actionlineage` redirects to
  `https://actionlineage.dev`.

## Current AWS ownership

- AWS account: `925091290061`
- Region: `us-east-1`
- DNS stack: `ActionLineageDnsStack`
- Website stack: `ActionLineageSiteStack`
- Hosted zone ID: `Z02252222E6DIO30TW92X`
- CloudFront distribution: `E2LIV6PK2VRHDJ`

The former website stack `ActionLineageRedirectStack` and its CloudFront
distribution `E1V9B654RDLYFX` were removed on 2026-06-23 during stack rename
maintenance. The former DNS stack `ActionLineageRedirectDnsStack` was replaced
by `ActionLineageDnsStack` and deleted on 2026-06-23.

## DNSSEC

Route 53 DNSSEC signing is enabled for `actionlineage.dev`.

Current DS record at Namecheap:

```txt
17710 13 2 BEF90FCB124C72142271229C8E30B89541A870418F938CF5B4A39A512B625063
```

Before changing DNSSEC:

1. Check Route 53 KSK status.
2. Check the registrar DS record.
3. Confirm validating resolvers return the `ad` flag.
4. Plan rollback and propagation timing.

## Routine deploy

```sh
aws sts get-caller-identity
npm run build:site
npm run cdk:diff
npm run deploy:site
npm run cdk:diff:site
```

The first diff before any deploy must include both `ActionLineageDnsStack` and
`ActionLineageSiteStack`. Stop if it would replace the hosted zone, DNSSEC
resources, ACM certificate, or CloudFront aliases. Routine website deploys use
`cdk deploy --exclusively` through `npm run deploy:site` so dependency stacks are
not updated during content-only changes.

## Routine verification

```sh
curl -I https://actionlineage.dev
curl -I https://www.actionlineage.dev
curl -I http://actionlineage.dev
curl -fsSL https://actionlineage.dev/robots.txt
curl -fsSL https://actionlineage.dev/sitemap.xml
dig +dnssec +adflag actionlineage.dev A @1.1.1.1
dig +dnssec +adflag actionlineage.dev A @8.8.8.8
```

Browser checks should confirm:

- page title and canonical metadata use `actionlineage.dev`;
- latest version resolves from GitHub tags;
- no browser console errors;
- no failed static resources;
- no horizontal overflow on mobile.

## Rollback

For content regressions, redeploy the previous static build.

For infrastructure regressions, use CloudFormation events first. If needed,
restore the previous CDK stack definition and redeploy
`ActionLineageSiteStack`. Avoid deleting the hosted zone or DNSSEC resources
unless explicitly planned.
