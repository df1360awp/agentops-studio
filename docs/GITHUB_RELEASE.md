# Publish to your own GitHub

No repository is created until you authenticate with GitHub and run these commands.

## GitHub CLI (after signing in)

```bash
gh auth login
cd AgentOps_Studio_GitHub
git init -b main
git add .
git commit -m "Initial open-source AgentOps Studio"
gh repo create agentops-studio --public --source=. --remote=origin --push
```

Or, create an empty `agentops-studio` repo at GitHub, then:

```bash
git init -b main
git add .
git commit -m "Initial open-source AgentOps Studio"
git remote add origin https://github.com/YOUR_USERNAME/agentops-studio.git
git push -u origin main
```

**Before publication**: check `git status`, search tracked files for secrets, review README and license, and remove local databases. Sample files are fictional. No GitHub credentials should ever be pasted into ChatGPT.

GitHub Actions CI will run tests for every push and pull request. A green build validates tests, **not** real commercial performance, model accuracy or production security.
