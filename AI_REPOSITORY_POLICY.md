# AI Repository Policy - License, Provenance, Security and Commercial Use

Repository: `oanohr/nmea0183_zs`  
Audit baseline: 2026-10-07  
Primary license: Apache-2.0

This is a mandatory policy for AI agents and human contributors. It is a technical compliance policy, not legal advice.

## Mandatory rules

1. Preserve the repository's Apache-2.0 LICENSE and all applicable third-party attribution.
2. Treat this repository as a derivative of `tomer-w/ha-nmea2000` (Apache-2.0), not as a clean-room original work.
3. Preserve provenance for upstream-derived files even after later refactoring. AI rewriting must never be used to conceal known origin.
4. Never copy code, documentation, tables, datasets or other material with unknown or incompatible licensing.
5. Never copy protected text, tables or PDFs from the commercially licensed NMEA 0183 standard unless redistribution rights are documented.
6. Verify every new runtime/build dependency's source, version, license and commercial compatibility before adding it.
7. Preserve copyright, patent, trademark, license and attribution notices that remain relevant.
8. Modified upstream-derived files must carry a prominent notice that they were changed.
9. Do not add GPL, AGPL, SSPL, custom/source-available or unknown-license code/dependencies without explicit human license review.
10. Never commit passwords, tokens, private keys, customer credentials, private certificates or production secrets.
11. Treat all TCP/NMEA input as untrusted. Do not feed received fields to eval/exec, shell commands, dynamic imports or unsafe file paths.
12. If provenance or licensing cannot be established, fail closed: do not merge and report `LICENSE-REVIEW-REQUIRED`.
13. Do not change the repository license, remove NOTICE/THIRD_PARTY_NOTICES, or weaken this policy without explicit human approval.
14. Run relevant tests and validation before merge.

## Confirmed provenance

The Git history contains commits from `tomer-w`. The README identifies this project as a fork of `tomer-w/ha-nmea2000`, rewritten for NMEA 0183.

Audit comparison confirmed substantial upstream ancestry, including:
- `custom_components/nmea0183/sensor.py`
- `custom_components/nmea0183/update_integration.sh`
- `custom_components/nmea0183/NMEA0183Sensor.py`
- ancestry/architecture in `hub.py` and `config_flow.py`

Upstream license: Apache-2.0.

Runtime parser:
- `pynmea2==1.19.0`
- license: MIT

## Commercial-use baseline

Apache-2.0 permits commercial use, modification and distribution subject to its conditions. Commercial releases must retain the license, applicable attribution/notices, and modification notices required for derivative files.

The software license is separate from rights in the NMEA 0183 standard. Do not redistribute protected NMEA standard content merely because this code parses NMEA messages.

## Dependency gate

Before adding a dependency, record:
- package and version
- authoritative upstream source
- license
- runtime/test/build role
- why it is needed
- whether it is bundled/distributed
- relevant security concerns

Normally acceptable after verification: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC.

Human review required: MPL, LGPL, EPL, CDDL, Creative Commons on code, custom/source-available licenses, dual-license ambiguity, vendor EULAs, unlicensed snippets, Stack Overflow/forum/gist code without verified permission, GPL/AGPL/SSPL.

## NMEA intellectual-property gate

AI MUST NOT:
- copy text or tables from the official NMEA 0183 standard;
- commit licensed NMEA PDFs;
- reconstruct large proprietary field tables from licensed documentation for redistribution;
- treat access to a licensed standard as permission to publish it.

If a feature requires proprietary standard material, report `NMEA-LICENSE-REVIEW-REQUIRED` and stop before copying it.

## Security gate

Network input is untrusted. Consider malformed/oversized sentences, encoding errors, checksum failures, missing fields, invalid numerics, high message rates, reconnect loops and resource exhaustion.

Plain TCP does not provide transport encryption or peer authentication. Do not describe it as secure transport; protect untrusted-network deployments at an appropriate network layer.

No secrets may enter source, tests, examples, logs or release packages.

## Supply-chain gate

Prefer official registries/repositories, pinned or controlled versions, reviewed dependency updates and tagged releases. Be cautious with arbitrary branch downloads, curl-pipe-shell installation, unverified assets, typo-squatted packages, ownership/license changes and direct Git dependencies.

## PR checklist

Before merge answer:
- Is any external code/material used? Source and license?
- Is attribution or a modified-file notice required?
- Are dependencies added/changed and licenses verified?
- Was official NMEA standard content used? If yes, is redistribution permission documented?
- Are secrets absent?
- Is network input handled defensively?
- Are update/download endpoints controlled?
- Do tests pass and documentation match behavior?

## Commercial release gate

Block release unless:
- LICENSE is present;
- NOTICE and THIRD_PARTY_NOTICES.md are current;
- upstream provenance is preserved;
- third-party dependencies are documented;
- no incompatible/unknown-license material is known;
- no protected NMEA standard material is redistributed without rights;
- manifest/docs/issues point to the maintained repository;
- updater uses an approved repository/release source;
- no secrets/customer data are present;
- tests/validation pass;
- project-specific copyright ownership has been confirmed by the responsible human/organization.

## Compliance finding format

```
COMPLIANCE FINDING
Severity: LOW | MEDIUM | HIGH | BLOCKER
Type: LICENSE | PROVENANCE | NMEA-IP | DEPENDENCY | SECURITY | SUPPLY-CHAIN
File:
Finding:
Evidence:
Required action:
Can merge: YES | NO
```

## AI prohibited actions

Without explicit human approval, never:
- relicense the project;
- remove upstream attribution;
- remove applicable copyright notices;
- claim the project is 100% original;
- claim a legal guarantee of non-infringement;
- copy unlicensed/GPL/AGPL code to solve a task;
- copy NMEA standard documentation;
- commit secrets;
- disable tests/security controls to make CI pass;
- redirect updates to an uncontrolled external source;
- self-approve an unknown license.

## Current audit actions

Completed/targeted by compliance hardening:
- preserve Apache-2.0 LICENSE;
- add NOTICE;
- add THIRD_PARTY_NOTICES.md;
- correct manifest ownership/docs/issues;
- correct updater repository;
- add explicit provenance notices to clearly derivative files;
- make this policy mandatory from Copilot instructions.

Still requires human/organizational confirmation before commercial release:
- identify the legal copyright owner of the project-specific 2026 modifications.

Final rule: preserve origin, verify licenses, do not trust unknown code, do not redistribute protected NMEA standard material without rights, and block merge when licensing is uncertain.
