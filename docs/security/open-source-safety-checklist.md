# Open-Source Safety Checklist

1. Revoke and rotate every key that appeared in commits (even if history is rewritten).
2. Ensure `.env` and `.venv/` are ignored in `.gitignore`.
3. Run `./scripts/scan_secrets.sh` and inspect results.
4. Run `./scripts/sanitize_git_history.sh` to rewrite history.
5. Re-run `./scripts/scan_secrets.sh` and verify leaked literals are gone.
6. Force-push rewritten history:
   - `git push --force --all origin`
   - `git push --force --tags origin`
7. Tell collaborators to delete old clones and re-clone.
8. Enable GitHub secret scanning and push protection on the repository.
9. Keep only placeholders in `.env.example`; never real values.
