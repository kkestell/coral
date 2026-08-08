# Readable agent progress

Roadmap: item `22`, `Readable agent progress`.

## Goal

Make the streaming output from the reviewer and verifier describe the work they are doing. A tool
call must print its public tool name and the arguments the model supplied. The stream must not
print OpenRouter HTTP request diagnostics or DeepAgents' internal `sync_` function names.

For example, the stream should read like this:

```
Calling read_file(file_path='coral/agent.py', offset=0, limit=100).
read_file finished in 0.0 seconds.
Calling execute(command='uv run pytest tests/test_agent.py').
execute finished in 5.4 seconds.
```

The same reporting applies to the main-push verifier's `search_open_issues` and `view_issue`
tools. It also applies to `coral rehearse`, because it uses the same agent construction.

## Decisions

- Use LangChain's tool callbacks instead of DeepAgents' private function names. `on_tool_start`
  receives the public `StructuredTool` name and an `inputs` dictionary with injected values such
  as `runtime` already removed.
- Log the call at start and its duration at finish. Pair both records by the callback run id, so
  calls in one model turn remain correctly named if the framework runs them concurrently.
- Render argument names and values on one escaped line. Keep paths, patterns, commands, numbers,
  booleans, and short strings intact. Replace a long string with a bounded preview that states its
  full character count. A scratch file's complete contents and a large edit replacement are not
  useful streaming output.
- Log no tool result. Tool output can be a source file or command transcript, and the agent already
  receives it. Progress output must show the action without duplicating its potentially large
  result.
- Keep the existing behavior that returns filesystem-tool exceptions to the model. Its log line
  will use the public tool name. Timing moves out of that wrapper and into the progress callback.
- Leave Coral's own `INFO` messages enabled. Set the `httpx` logger to `WARNING` when the CLI
  configures logging, which suppresses its per-request `HTTP Request` lines without hiding Coral's
  failure and progress messages.

## Approach

### Report public tool calls

Add a small `ToolProgressHandler` beside `SpendHandler` in `coral/agent.py`. It subclasses
`BaseCallbackHandler`, records a monotonic start time and the serialized public tool name in
`on_tool_start`, and emits the formatted call. Its `on_tool_end` removes the saved state and logs
the named completion with elapsed seconds. Its error path names the same tool and error if an
uncaught tool exception reaches LangChain.

Give the handler a formatter for the `inputs` mapping. The formatter handles the tool schemas
Coral exposes, uses a deterministic argument order, escapes line breaks, and limits individual
string previews with their original length. It must never inspect a tool's result or the injected
`runtime` object.

Change `caught()` to accept the `StructuredTool`'s public name. `forgiving()` supplies `tool.name`
when it wraps each filesystem function. The wrapper keeps converting an exception to the existing
model observation, but logs a named failure and no longer logs the function's private
`sync_<tool>` name or timing.

### Install the handler for each agent run

Build one progress handler for each `_run()` invocation and add it beside `SpendHandler` in the
callback configuration passed to `bounded.invoke()`. This covers filesystem tools and verifier-only
issue tools without exposing a new capability or changing any prompt, tool schema, sandbox, spend,
or deadline behavior.

Keep the existing review-start and review-finished messages. The start, action, completion, and
finished messages together describe both agent passes without model request noise.

### Silence HTTP transport diagnostics

Update `coral/cli.py`'s logging setup to raise `httpx` from the root `INFO` level to `WARNING`.
`httpx` is the logger that emits the current request lines. Do not change the root formatter,
stderr destination, or Coral logger levels.

Update the architecture's review-run description with the tool-progress and HTTP-noise boundary.
This is the one document that owns how the workflow runs. Do not add the implementation detail to
the functional requirements or README.

## Related code

- `coral/agent.py` — public-name progress callback, bounded argument formatting, named filesystem
  errors, and callback installation.
- `coral/cli.py` — suppress `httpx` request diagnostics while retaining Coral `INFO` logs.
- `tests/test_agent.py` — callback event, argument rendering, failure, and construction coverage.
- `tests/test_cli.py` — logging configuration coverage if the setup is factored into a testable
  helper.
- `.agents/docs/architecture.md` and `.agents/docs/roadmap.md` — current workflow logging behavior
  and item state.

## Test plan

### Unit tests

- Invoke a real `StructuredTool` with `ToolProgressHandler`. Assert that its start record uses the
  public tool name, contains the supplied argument names and values, omits an injected runtime
  value, and contains no `sync_` name.
- Complete that call and assert that the matching public name and a duration are logged. Exercise
  an error callback too, so a failed tool keeps a usable tool name and does not leave stale timing
  state.
- Pass a multiline, overlong string argument through the formatter. Assert that the output stays
  on one line, identifies the argument and original size, and does not log the full value.
- Wrap a failing filesystem-style function through `caught()`. Assert that its observation still
  reaches the model as an error string and its log names the public tool rather than the private
  function.
- Intercept agent construction as the existing tests do. Assert that every `_run()` installs one
  progress callback alongside the spend callback, while the reviewer and verifier retain their
  existing tool lists.
- If logging setup becomes a helper, assert that `httpx` resolves to `WARNING` and that Coral's
  logger still emits at `INFO`.

### Static checks

Run `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, and
`uv run pytest` after the code and documentation changes.

### Live check

Push the implementation to Coral's `main` branch and request a review in `kkestell/coral-test`.
Read the review job's streamed log while it runs and after it finishes. Confirm that each observed
agent action identifies a public tool and useful input, including readable paths or commands;
completion lines use the same names; no line contains `sync_`; and no `HTTP Request:` line appears.
Confirm the run remains green and the normal review or failure output reaches the pull request.

## Documentation updates

- Add one architecture bullet describing action-level progress logs and suppressed HTTP transport
  diagnostics.
- Update roadmap item 22 to `built` only after the live check succeeds and its evidence is read.
  Keep its dependency and done condition, and leave only constraints for later work under the
  item.

## Not doing

- Streaming model requests, model responses, tool results, token counts, or provider URLs.
- Changing which tools the reviewer or verifier can call.
- Adding a logging input, a new dependency, or a second output channel.
