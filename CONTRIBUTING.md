# Contributing to PiNexo

Changes should preserve a readable 480×320 interface and moderate memory,
CPU, and network use on the Raspberry Pi 3.

## Prepare and verify a change

1. Create a branch for the change and explain the problem it solves.
2. Use `config.json.example` as the basis for your local configuration.
   `config.json` is excluded from the repository.
3. Install the development dependencies and run the offline tests:

   ```sh
   python -m pip install -r requirements-dev.txt
   python -m unittest discover -s tests -t . -v
   ```

4. If you change the interface, check both themes at 480×320, navigation,
   and returning to Home (`Inicio`). Attach a screenshot and distinguish
   simulated display results from testing on the physical LCD.
5. Describe what changed, how you verified it, and any remaining limitations
   in your proposal.

Tests must not contact live providers, run systemd, or read the user's cache.
Use fixtures, temporary directories, and simulated services. Also check
incomplete responses, timestamps, and preservation of valid data after failures.

Future modules must allow returning to Home and respect the selected theme.
Do not present accounts, credentials, or messaging integrations as already
configured. Preserve all data and image attributions.

## Documentation language

Write project documentation in English, including README files, the guides
in `docs/`, contribution instructions, and release notes. When referring to
the current Spanish interface, quote the actual control label and explain
its meaning in English where needed.

## Commit scope and messages

Each commit should describe one coherent change. Group files that serve the
same purpose, and use separate commits for independent topics. For example,
a hardware guide update and a notification feature belong in separate commits;
an implementation and its directly related tests can share a commit.

Write concise English commit messages that state what changed. A scope helps
identify the affected topic, for example:

```text
docs(hardware): translate the GPIO display setup guide into English
docs(upgrade): translate migration and update instructions into English
fix(weather): preserve the last valid forecast after a download failure
```

Before committing, review the staged diff and make sure every included change
belongs to the stated purpose. Keep unrelated changes in separate commits.

## Report an issue

Avoid publishing passwords, tokens, email addresses, device IP addresses, or
personal files. Include only the output needed to reproduce the issue.
