# Physical Lab Release Checklist

Use this checklist for public macOS releases. Passing source CI is necessary but not sufficient for public distribution.

## 1. Version and source identity

- `VERSION`, `package.json`, `src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json` agree.
- `python3 scripts/version_consistency.py` passes.
- All managed Lab/runtime revisions in `src-tauri/resources/modules.json` are pinned to explicit 40-character Git commit SHAs.
- `CHANGELOG.md` describes the release's scientific and software boundaries.

## 2. Deterministic/source validation

- Source Integrity is green.
- Reference validation snapshots are unchanged unless an intentional, reviewed scientific change explains the difference.
- Physical Lab self-check passes.

## 3. Native scientific acceptance

- Full-mode Acceptance is green on clean macOS.
- The pinned RADIA extension loads and produces the expected bounded native-field evidence.
- The cross-engine field-map → trajectory/radiation acceptance path passes.
- Acceptance evidence is treated as interface/runtime validation, not experimental validation of a specific device.

## 4. Universal2 packaging

- macOS Universal2 Build is green.
- Packaged executable reports both `arm64` and `x86_64` through `lipo -archs`.
- DMG filename matches the canonical version.
- SHA-256 sidecar matches the exact uploaded DMG.

## 5. Signing and notarization for public distribution

- Sign the exact release `.app`/DMG with the intended Apple Developer ID identity.
- Verify signatures on the exact packaged artifact.
- Submit the exact release artifact for Apple notarization and confirm acceptance.
- Staple/verify notarization where applicable.
- Test the distributed artifact on a separate Mac account or clean test Mac with normal Gatekeeper behavior.

Do not describe a locally built, unsigned/unnotarized DMG as a fully public-release-ready macOS package.

## 6. Release evidence

Preserve or attach:

- source commit/tag;
- Universal2 workflow run;
- Full-mode acceptance workflow run and JSON evidence artifacts;
- DMG SHA-256;
- release notes/changelog;
- signing/notarization verification for public distribution.
