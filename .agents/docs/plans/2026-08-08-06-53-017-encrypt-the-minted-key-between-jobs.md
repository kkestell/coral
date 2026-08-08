# Encrypt the minted key between jobs

Roadmap: item `17`, `Encrypt the minted key between jobs`.

## What Was Checked

- Resolve writes the minted OpenRouter API key through `runner.write_output`. The resolve action
  maps that step output to `minted-key`, and the workflow maps it to a job output. The review job
  receives the cleartext in the environment of its first step before that step registers a mask.
- A GitHub Actions job gets a unique `GITHUB_TOKEN` at its start. Resolve and review therefore
  have no shared automatic token from which they can derive an encryption key. Repository and
  organization secrets are read when the run is queued, so one caller secret is stable across
  both jobs in the run. GitHub documents both facts in its
  [`GITHUB_TOKEN`](https://docs.github.com/en/actions/concepts/security/github_token) and
  [secrets](https://docs.github.com/en/actions/reference/security/secrets) references.
- A caller must pass a secret explicitly into a reusable workflow. An unset secret evaluates to
  an empty string. Both behaviors are documented in GitHub's
  [reusable-workflow](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
  and [using-secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
  pages.
- GitHub refuses a job output that its masker recognizes as a secret. A ciphertext does not match
  the cleartext secret, so it can remain the small one-line job output that YAML already reads.
  No artifact is needed.
- `cryptography.fernet.Fernet` is the library's high-level authenticated-encryption recipe. A
  token cannot be read or altered without its 32-byte key. The token is URL-safe base64 text, so
  it can be a one-line Actions output. The library documents these properties in its
  [Fernet reference](https://cryptography.io/en/latest/fernet/).
- The locked environment already contains `cryptography` through `deepagents`, `google-genai`,
  and `google-auth`. Coral does not declare it directly. Implementation must use
  `uv add cryptography` so the package manager records Coral's direct dependency.
- A local check with the locked `cryptography` package encrypted a 73-byte OpenRouter-shaped key
  into a 184-byte one-line token. The plaintext and its URL-safe base64 encoding were absent from
  the token. Changing one token byte made decryption fail.
- `coral review` pops `OPENROUTER_API_KEY` before any other work. The model client keeps the key in
  the runner process. `shell_environment` builds the container environment from fixed values and
  the toolcache without reading the runner process environment.
- `architecture.md` has 1,499 words. Any implementation edit must trim it before adding facts.
  `functional-requirements.md` also has 1,499 words and needs no change for this item.
- `roadmap.md` has an uncommitted user edit that introduces items 17 through 19. Implementation
  must preserve that edit and change only item 17 when its done condition has been met.

## Goal

Resolve still mints one capped, expiring OpenRouter API key after the gates pass. It registers the
minted key with the resolve runner's masker and publishes only authenticated ciphertext. Review
decrypts the ciphertext in Coral's runner process. Neither the minted key nor the encryption key
enters an agent container, the checkout, an artifact, or an unmasked log field.

Plain API-key mode keeps its existing path. The caller's OpenRouter API key goes directly from a
GitHub secret to the review action, and GitHub masks it.

## Approach

### One handoff secret

Add one optional `workflow_call` secret named `coral_key_encryption_key`. The repository-level
name shown to installers is `CORAL_KEY_ENCRYPTION_KEY`. It is a Fernet key generated independently
of both OpenRouter credentials.

The caller passes this secret only when it passes `openrouter_management_key`. Plain API-key mode
does not require it. A repository may leave the encryption secret installed while switching back
to plain mode; Coral ignores it in that mode.

Resolve receives the encryption secret because it encrypts. Review receives the same secret
because it decrypts. The management key still reaches resolve alone. The encryption secret grants
no OpenRouter or GitHub authority.

Fernet is symmetric. An asymmetric key pair would keep the decryption half out of resolve, but it
would add two installation values and use the library's hazardous-material layer. Resolve already
holds the more powerful management key. A second secret and the recipe-layer API are the smaller
implementation for the boundary this item protects.

The README gives one command that generates 32 random bytes and encodes them as a Fernet key with
Python's standard library. It also shows how to save the result as `CORAL_KEY_ENCRYPTION_KEY`.
The generated value is never committed to the caller file.

### Authenticated ciphertext

Add `coral/handoff.py` with four small functions:

```python
def encryption_key(value: str) -> str:
    """Validate the caller's Fernet key and return it."""

def encrypt(key: str, plaintext: str) -> str:
    """Encrypt one API key into the one-line token that crosses jobs."""

def decrypt(key: str, token: str) -> str:
    """Authenticate and decrypt the token in the receiving runner process."""

def review_key(plain: str, token: str, key: str) -> str:
    """Select the plain path or open the encrypted path for review."""
```

`encryption_key` rejects an absent, malformed, or wrong-length value with a `RuntimeError` that
names `CORAL_KEY_ENCRYPTION_KEY`. Resolve validates it after the pull request gates and before it
mints. Forks therefore keep their current decline path, where GitHub withholds caller secrets.
An invalid installation does not leave an unused minted OpenRouter key behind.

`encrypt` converts the minted key to bytes and returns the Fernet token as text. `decrypt` catches
`InvalidToken` and reports that the ciphertext and `CORAL_KEY_ENCRYPTION_KEY` do not match. It does
not print either value.

No Fernet time-to-live check is added. OpenRouter's `expires_at` remains the authority that
revokes the API key. The ciphertext exists only within the workflow run. GitHub snapshots the
encryption secret when it queues the run, so rotating the repository secret cannot split one run
across two encryption keys.

### Resolve

`actions/resolve/action.yml` gains the `coral-key-encryption-key` input and passes it as
`CORAL_KEY_ENCRYPTION_KEY`. The workflow passes the caller secret to that input.

After the gates, `resolve()` keeps its existing exactly-one choice between a plain API key and a
management key. When it selects management mode, it validates the encryption key before calling
OpenRouter. A missing encryption key goes through `reported`, writes `reason.txt`, and fails before
minting.

After minting, resolve immediately registers the minted key with `::add-mask::`. Add a small
`runner.mask(value)` helper for that workflow command. Resolve then encrypts the key and writes an
`encrypted-key` step output. The old `minted-key` output is removed at all three mapping levels.

The encryption key is already a GitHub secret, so GitHub masks it before either job starts. The
minted key becomes a dynamic masked value before any later operation could log it. The ciphertext
is the only new job output. Its Fernet token is not a reversible text encoding without the caller
secret.

### Review

The workflow removes the first masking step. That step is the current cleartext exposure and has
no purpose once the job output is ciphertext.

`actions/review/action.yml` keeps `openrouter-api-key` for pass-through mode, but makes it optional
because it is empty in management mode. It adds optional `encrypted-openrouter-api-key` and
`coral-key-encryption-key` inputs. The workflow passes the plain caller secret only to the first
input. It passes resolve's `encrypted-key` output and the encryption secret to the other two
inputs.

At the top of `review()`, pop all three environment values before any other work. If the plain key
is present, use it unchanged and require no ciphertext. If the plain key is absent, require both
the ciphertext and the encryption key, decrypt in memory, and immediately call `runner.mask` on
the plaintext. Both modes then continue through the existing `api_key` local variable.

The decrypted key is never written to disk. It remains in the Coral process and is passed to the
model client as it is today. `shell_environment` still contains only `CI`, `HOME`, `LANG`, and
`PATH`, so neither the decrypted key nor the encryption key reaches either container.

### Failure behavior

The workflow should make the intended combinations, but the Python boundary still rejects broken
ones clearly. Management mode without an encryption secret fails in resolve. Review rejects both
a plain key and ciphertext, neither one, ciphertext without an encryption key, and a token that
does not authenticate.

These are `RuntimeError` messages for a person. No exception taxonomy is added. Resolve's existing
`reported` wrapper and review's existing top-level failure handler carry the messages to the one
failure comment.

## Related Code

- `pyproject.toml`, `uv.lock` — `cryptography` becomes a direct dependency through `uv add`.
- `coral/handoff.py` — new; Fernet key validation, encryption, and decryption.
- `coral/runner.py` — the workflow-command helper that registers a dynamic mask.
- `coral/resolve.py` — validate the encryption key, mint, mask, encrypt, and output ciphertext.
- `coral/review.py` — select the plain path or decrypt the minted path before review work.
- `.github/workflows/coral.yml` — the caller secret, ciphertext output, and new action inputs. The
  cleartext masking step is removed.
- `actions/resolve/action.yml`, `actions/review/action.yml` — the new environment values and the
  renamed output.
- `tests/test_handoff.py`, `tests/test_resolve.py`, `tests/test_runner.py`,
  `tests/test_environment.py` — the unit coverage below.
- `README.md`, `examples/coral.yml`, `.agents/docs/architecture.md`,
  `.agents/docs/development.md`, `.agents/docs/roadmap.md` — the current facts after the change.

## Current State

- Management mode needs one caller secret and exposes its minted child key in the review job's
  first logged environment block.
- Resolve publishes `minted-key` as cleartext at the step, action, and job-output layers.
- Review receives one action input that chooses the plain secret or the minted output with `||`.
- The first review step masks a minted key after the runner has already evaluated that step.
- The agent containers receive no environment value from the runner process.
- `kkestell/coral-test` and `kkestell/coral` currently hold only `OPENROUTER_API_KEY`. Their caller
  files use plain mode.

## Test Plan

### Unit tests

- `encryption_key` accepts a generated Fernet key. It rejects empty text, malformed base64, and a
  decoded value of the wrong length with a message naming `CORAL_KEY_ENCRYPTION_KEY`.
- `encrypt` and `decrypt` round-trip an OpenRouter-shaped key. The ciphertext is one line, differs
  across two encryptions of the same plaintext, and contains neither the plaintext nor its
  URL-safe base64 encoding.
- `decrypt` rejects a changed token and the wrong encryption key with the same clear boundary
  message. The exception text contains no plaintext, ciphertext, or encryption key.
- The review-key selection accepts a plain key without an encryption key. It accepts ciphertext
  only with a valid encryption key. It rejects both credentials, neither credential, and missing
  encryption material.
- `runner.mask` writes exactly one `::add-mask::` workflow command and refuses a value containing a
  newline. A newline would turn one command into runner-controlled extra commands.
- Resolve's management-mode validation requires the encryption secret before the minting path.
  Plain mode remains valid when the encryption secret is absent or installed but unused.
- `shell_environment`'s existing process-environment test adds `CORAL_KEY_ENCRYPTION_KEY` and an
  encrypted token. The returned container environment remains exactly its four fixed names.

Do not unit-test Fernet's primitives or GitHub's expression evaluation. The round trip tests
Coral's encoding and error boundary. The real runs test the workflow mapping and runner masking.

### Live checks

1. Keep `kkestell/coral-test` in plain mode and run a review after the implementation lands on
   `main`. The run is green and the review posts. This is the control for the roadmap's unchanged
   plain-key path.
2. Pass `openrouter_management_key` without `coral_key_encryption_key` and ask on an open pull
   request. Resolve fails before a key is minted. One failure comment names the missing
   `CORAL_KEY_ENCRYPTION_KEY`.
3. Generate and install `CORAL_KEY_ENCRYPTION_KEY`, pass both management-mode secrets, and ask
   again. The review posts and the run is green. OpenRouter's key list carries a capped, expiring
   key named with that run's URL.
4. Download the complete log for check 3 outside the repository. Scan without printing matches for
   the OpenRouter key prefix and the base64 and hexadecimal encodings of that prefix. Inspect the
   resolve output mapping and the downloaded log to confirm that only the Fernet token crossed.
   The old first-step cleartext line is absent.
5. For check 3, temporarily add a fixed runner-side probe after each container starts. Inspect the
   container's configured environment and fail without printing values unless its names are
   exactly `CI`, `HOME`, `LANG`, and `PATH`. Log only that the probe passed, then revert the probe.

Restore `kkestell/coral-test` to its ordinary management-mode caller after the checks. Keep the
encryption secret installed. The repository is then available for later encrypted-handoff checks.

## Implementation Plan

1. Save this plan without changing the user's roadmap edit.
2. Run `uv add cryptography` so the package manager records the direct dependency.
3. Write `coral/handoff.py` and `tests/test_handoff.py`.
4. Add `runner.mask` and its tests. Wire encryption-key validation, masking, encryption, and the
   renamed output through `coral/resolve.py` and its tests.
5. Change `coral/review.py` to pop the three inputs, select the mode, and decrypt only the minted
   path. Extend the handoff and environment tests.
6. Wire both composite actions and `.github/workflows/coral.yml`. Remove every `minted-key`
   reference and the receiving job's first masking step.
7. Update `examples/coral.yml`, the README, and the current-fact documents below.
8. Run `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, and
   `uv run pytest` until all five are clean.
9. Run live checks 1 through 5 and read the review, complete log, OpenRouter key record, failure
   comment, and container-probe line.
10. Change roadmap item 17 to `built` only after every part of its done condition has direct
    evidence. Keep the item's dependency and done condition, and remove mechanics now owned by
    the code and architecture document.

## Not Doing

- An asymmetric key pair. It adds an installation value and lower-level cryptographic code without
  reducing authority in the resolve job, which already holds the management key.
- Deriving a shared key from `GITHUB_TOKEN`. GitHub creates a different token for every job.
- Passing the encryption key as an output. That would make the ciphertext reversible by the same
  readers this item removes from the key's audience.
- Moving ciphertext to an artifact. The one-line job output is already the smaller channel, and an
  artifact adds retention and download surface.
- Writing the decrypted key to a temporary file. The model client already accepts the value in
  memory.
- A Fernet time-to-live or `MultiFernet` rotation list. OpenRouter expires the credential itself,
  and GitHub snapshots the shared secret for the whole queued run.
- Deleting a minted key after review. Expiry remains the cleanup mechanism, and deletion would put
  the management key in another job.
- The external broker and microVM work in roadmap items 18 and 19.

## Documentation Updates

`.agents/docs/architecture.md` must stay at or below 1,500 words. Trim before adding the following
facts:

- "Installation and Packaging": management mode also takes one generated encryption secret. It
  has no provider authority and is shared by resolve and review.
- "The Run": resolve masks and encrypts the minted key, ciphertext crosses as the job output, and
  review decrypts in its own process before starting either container.
- "The Run" job-boundary bullet: replace the minted key with its ciphertext.
- "Rules That Hold Everywhere": remove the public cleartext-log risk. Keep the fact that the
  container receives no credential.
- "The Codebase": add `coral/handoff.py` as the key-encryption boundary.

`.agents/docs/development.md`, "Environment": add `CORAL_KEY_ENCRYPTION_KEY`. It is required for a
local management-mode resolve, ignored in plain mode, and never enters the agent container. Add
the exact standard-library command used to generate one.

`README.md`: management-mode installation creates and passes both `OPENROUTER_MANAGEMENT_KEY` and
`CORAL_KEY_ENCRYPTION_KEY`. Remove the remaining-risk bullet about a cleartext minted key. State
that ciphertext crosses the job boundary and the decrypted key remains in the review runner
process.

`examples/coral.yml`: keep plain mode as the active example. Add commented management-key and
encryption-key lines together so the two cannot look independently optional.

`.agents/docs/roadmap.md`: preserve the uncommitted additions. Change item 17 only after the live
checks. No change to items 18 or 19.

`.agents/docs/testing.md`: no change. It already states that every done-condition claim needs a
live run and explains how to use the test repository.

`.agents/docs/functional-requirements.md`: no change. This item changes credential transport, not
observable review behavior.

## Validation

- The five local commands are clean.
- Live check 1 proves plain API-key mode remains unchanged.
- Live checks 2 and 3 prove management-mode configuration fails clearly and a configured real
  review runs green.
- Live check 4 proves the complete run log carries no cleartext minted key and the workflow no
  longer exposes a reversible text encoding.
- Live check 5 proves both real review containers still carry no credential.
- The management key appears only in the resolve action's input and environment mapping.
- The decrypted API key exists only as a local value in the review runner process and the model
  client objects it constructs.
