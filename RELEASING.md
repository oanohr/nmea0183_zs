# Releasing

HACS only offers full GitHub releases by default; a pre-release is only shown to users who enable beta versions.

1. Make sure `main` is green (tests, hassfest and HACS validation).
2. Set `version` in `custom_components/nmea0183/manifest.json` to the new version, merge that change, and wait for CI.
3. Create the release from `main` with a tag that matches the version, for example `v1.0.0`. Use the release-drafter draft for the notes and mention anything that changes entity ids or behaviour (see "Upgrading" in the README). Publish it as a full release, not a pre-release.
4. Install it through HACS on one site first, follow the upgrade steps in the README, and look at `State`, `Data state` and the log before rolling it out to the other sites.
