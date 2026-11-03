# Code signing the Windows installer

**Status:** not signed yet, so Windows SmartScreen warns on first run.

**Decision needed:**
- which signing route to use;
- who appears as the publisher.

The CI change takes about an hour once an account exists. The identity check is done by the provider and can take days.

## What signing does and does not do

- Signing puts a verified publisher name on `ProductivitySuite.exe` and the `.msi`. It also proves the files were not altered after the build.
- It does **not** remove the SmartScreen warning immediately. Reputation builds as more people download and run the signed files.
- EV certificates no longer skip that step. Vendors such as DigiCert now say both OV- and EV-signed files have to build reputation.
- Since June 2023, publicly trusted code-signing keys must live on a hardware security module or a cloud signing service. A key file stored in a GitHub secret is no longer an option.

## Options

| Option | Cost (verify before buying) | Publisher shown | Who can use it | Fits this repo |
|---|---|---|---|---|
| **Azure Artifact Signing** (formerly Trusted Signing), Microsoft's managed service | About US$9.99/month (Basic: 5,000 signatures) | Your verified name or company | Individuals in the USA and Canada only. Organisations in more countries, after identity validation. Needs a pay-as-you-go Azure subscription. | Yes. It has a GitHub Action, so no hardware is needed. |
| **SignPath Foundation** (free for open source) | Free | "SignPath Foundation" (not your name) | Projects under an OSI-approved license (Apache-2.0 qualifies) with the source in a **public** repository and no proprietary components. Builds must be traceable to the public repo. The team needs MFA. | Only if the repository becomes public. |
| **OV certificate on a cloud HSM** from a commercial CA (for example Certum, Sectigo, DigiCert) | Roughly US$100–400 per year; varies by vendor | Your verified name or company | Any country. Individual or company validation. | Yes. Signing runs in CI through the vendor's cloud signing tool. |

Linux: `.deb` files installed directly with `apt install ./file.deb` are not checked for signatures. Signing matters only if you later publish an apt repository, which is signed with a GPG key.

## Recommendation

1. **You are an individual in the USA or Canada, or a company that passes Microsoft's validation:** use Azure Artifact Signing. It is the cheapest option that shows your own name, and it is built for CI.
2. **You plan to make the repository public and accept "SignPath Foundation" as publisher:** apply to SignPath Foundation. It is free.
3. **Neither applies:** use an OV certificate on a cloud HSM.

## Steps once an option is chosen

1. **You:** create the account and complete identity validation with the provider. Nobody else can do this for you.
2. **You:** add the credentials as GitHub Actions secrets in the repository settings. With Azure, for example, that is the tenant, client and subscription IDs for a federated (OIDC) identity, plus the account and certificate profile names.
3. **Claude, in a PR:**
   - sign `ProductivitySuite.exe` after PyInstaller and before WiX;
   - sign the `.msi` after WiX;
   - verify both with `signtool verify /pa`;
   - make the release job refuse to publish unsigned files once signing is configured.

   Pull-request builds from forks stay unsigned.
4. Publish the next release. The SmartScreen warning fades as downloads build reputation.

## Sources

- [Microsoft: code signing options for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Azure Artifact Signing pricing tiers (Microsoft docs on GitHub)](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/artifact-signing/how-to-change-sku.md)
- [SignPath Foundation](https://signpath.org/) and its [terms](https://signpath.org/terms)
- [DigiCert: EV-signed applications showing SmartScreen warnings](https://knowledge.digicert.com/alerts/ev-signed-application-showing-microsoft-defender-smartscreen-warnings)

Prices, eligibility and service names change. Check each provider's current page before buying.
