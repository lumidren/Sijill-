# Contributing the PDPL framework to Prowler

[`compliance/prowler/pdpl_egypt_aws.json`](../compliance/prowler/pdpl_egypt_aws.json) is written as a Prowler compliance
framework so that Prowler itself could report on Egypt's Personal Data Protection Law. These notes cover what was
checked, how to try it locally, and what has to happen before it is proposed upstream.

## What was verified (Prowler 5.50.0)

The format was read from the Prowler 5.50.0 package, not written from memory:

- `prowler/lib/check/compliance_models.py`: a framework is `Framework`, `Name`, `Provider`, optional `Version`,
  `Description` and `Requirements`; a requirement is `Id`, `Description`, optional `Name`, `Attributes` and `Checks`.
  Frameworks without a dedicated attribute model use `Generic_Compliance_Requirement_Attribute`
  (`ItemId`, `Section`, `SubSection`, `SubGroup`, `Service`, `Type`, `Comment`), which is what this file uses.
- Built-in frameworks live in `prowler/compliance/<provider>/` and the framework name is the file name without
  `.json` (`Compliance.get_bulk`), so this file would be selected with `--compliance pdpl_egypt_aws`.
- The file loads with Prowler's own `load_compliance_framework` (52 requirements, 131 check references). This was a
  one-off run against the unpacked wheel, because Prowler cannot be installed on the Windows development machine
  (see [DECISIONS.md](DECISIONS.md) #8).
- Every check ID exists in Prowler 5.50.0. `backend/tests/test_mapping.py` checks this against a committed snapshot of
  the 678 AWS check IDs on every run, and the CI job `prowler-mapping` installs Prowler on Linux and checks again
  against the live package.

## Try it locally

On a machine where Prowler is installed:

```bash
cp compliance/prowler/pdpl_egypt_aws.json "$(python -c 'import prowler, os; print(os.path.dirname(prowler.__file__))')/compliance/aws/"
prowler aws --compliance pdpl_egypt_aws -M json-ocsf
```

The JSON-OCSF output can then be imported into Sijill (Automated checks → Import findings). Prowler 5.50.0 also
loads external frameworks registered under the `prowler.compliance` entry-point group (`Compliance.get_bulk`);
packaging the file that way would avoid copying it into site-packages, but that route has not been tested here.

## Before proposing it upstream

1. **Legal review first.** All 52 requirements are plain-language drafts marked unverified
   ([LEGAL-REVIEW.md](LEGAL-REVIEW.md)). A framework that names a law should cite it; add article references to the
   `Description` or `Attributes.Comment` once a lawyer has confirmed them, and remove the "not yet verified" comment.
2. **Decide the shape Prowler maintainers want.** This file keeps all 52 requirements, with organisational ones as
   `Type: Manual` and no checks, which mirrors how frameworks such as CIS list manual items. Maintainers may prefer
   only the 16 technical requirements.
3. **Naming.** Existing files follow `<framework>[_<version>]_<provider>.json` (for example `gdpr_aws.json`,
   `iso27001_2022_aws.json`). `pdpl_egypt_aws.json` fits; a version suffix could be added once the regulations'
   reference is confirmed.
4. **Run Prowler's own test suite** with the file in place. Its contribution guide and tests were not checked here.
5. **Other providers.** Only AWS is mapped. Azure and GCP mappings would follow the same requirement IDs.

## Keeping it current

When Prowler renames or retires checks, the CI job fails. Update the mapping, then refresh the snapshot by
regenerating `compliance/prowler/prowler-<version>-aws-checks.json` from the new package's
`prowler/providers/aws/services/*/*/*.metadata.json` files.
