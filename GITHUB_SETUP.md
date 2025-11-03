# 🚀 Push to GitHub - Complete Guide

## Step 1: Initialize Git (if not already done)

```bash
# Navigate to your project
cd "c:\Users\adity\OneDrive\Desktop\Evidentia---Multimodal-Multi-Agent-Research-Analyst-"

# Initialize git repository
git init

# Check status
git status
```

## Step 2: Configure Git (First Time Only)

```bash
# Set your name and email
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Verify configuration
git config --list
```

## Step 3: Add Remote Repository

Replace `YOUR_USERNAME` and `REPO_NAME` with your actual GitHub username and repository name:

```bash
# Add remote origin
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Verify remote
git remote -v
```

## Step 4: Stage All Files

```bash
# Add all files (respects .gitignore)
git add .

# Check what will be committed
git status
```

## Step 5: Create Initial Commit

```bash
# Commit with descriptive message
git commit -m "feat: initial commit - Evidentia AI Research Assistant

- Complete frontend with Next.js 15
- FastAPI backend with RAG architecture
- Multi-source ingestion (web, PDF, video)
- Voice input and keyboard shortcuts
- Zero generic content report generation
- Professional PDF export
- Docker compose infrastructure
- Comprehensive documentation"
```

## Step 6: Create and Push to Main Branch

```bash
# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 7: Verify on GitHub

1. Go to your GitHub repository
2. Refresh the page
3. You should see all your files!

---

## 🔐 If You Need Authentication

### Option 1: Personal Access Token (Recommended)

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a name: "Evidentia Development"
4. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Action workflows)
5. Click "Generate token"
6. **Copy the token immediately** (you won't see it again!)

When pushing, use:
```bash
# Username: your-github-username
# Password: paste-your-token-here
git push -u origin main
```

### Option 2: SSH Key (More Secure)

```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your.email@example.com"

# Start SSH agent
eval "$(ssh-agent -s)"

# Add key to agent
ssh-add ~/.ssh/id_ed25519

# Copy public key
cat ~/.ssh/id_ed25519.pub
```

Then:
1. Go to GitHub → Settings → SSH and GPG keys
2. Click "New SSH key"
3. Paste your public key
4. Change remote URL:
   ```bash
   git remote set-url origin git@github.com:YOUR_USERNAME/REPO_NAME.git
   ```

---

## 📋 Best Practices Checklist

Before pushing:

- [x] ✅ `.gitignore` created (excludes node_modules, .env, etc.)
- [x] ✅ `README.md` is comprehensive and beautiful
- [x] ✅ `CONTRIBUTING.md` added for contributors
- [x] ✅ `LICENSE` file exists (MIT)
- [x] ✅ Documentation is complete
- [ ] ⚠️ Remove sensitive data (API keys, passwords)
- [ ] ⚠️ Test that app runs after clone
- [ ] ⚠️ Add GitHub Actions (optional)

---

## 🎨 After Pushing - GitHub Repository Setup

### 1. Add Repository Description

On GitHub:
- Click "⚙️ Settings"
- Add description: "🔬 AI-Powered Research Assistant - Zero Generic Content, Evidence-Based Reports"
- Add website: Your deployment URL (if any)
- Add topics: `ai`, `research`, `fastapi`, `nextjs`, `rag`, `vector-database`, `hackathon`

### 2. Create Repository Sections

#### About Section
```
🔬 Evidentia - AI Research Assistant

✨ Features:
• Zero generic content - every sentence is evidence-based
• Voice-first design with keyboard shortcuts
• Multi-source analysis (web, PDF, video)
• Professional report generation
• Export to PDF, JSON, CSV

🚀 Quick Start: npm run dev
📖 Docs: See README.md
```

#### Topics to Add
```
ai
research-assistant
fastapi
nextjs
react
typescript
python
rag
vector-database
semantic-search
hackathon
multimodal
evidence-based
```

### 3. Enable GitHub Features

- ✅ Issues (for bug reports)
- ✅ Discussions (for community)
- ✅ Wiki (optional)
- ✅ Projects (for roadmap)

### 4. Add Branch Protection (Optional)

Settings → Branches → Add rule:
- Branch name pattern: `main`
- ✅ Require pull request reviews
- ✅ Require status checks to pass

### 5. Create Labels

Issues → Labels → New label:
- `bug` (red) - Something isn't working
- `enhancement` (blue) - New feature request
- `documentation` (green) - Documentation improvements
- `good first issue` (purple) - Good for newcomers
- `help wanted` (yellow) - Extra attention needed
- `hackathon` (orange) - Hackathon-related

---

## 🔄 Future Updates

When you make changes:

```bash
# Check status
git status

# Stage changes
git add .

# Commit with message
git commit -m "feat: add new feature"

# Push to GitHub
git push
```

---

## 🌿 Branching Strategy

For new features:

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes and commit
git add .
git commit -m "feat: implement new feature"

# Push branch
git push -u origin feature/new-feature

# Create Pull Request on GitHub
# After review, merge to main
```

---

## 🚨 Common Issues

### Issue: "fatal: remote origin already exists"
```bash
# Remove existing remote
git remote remove origin

# Add correct remote
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
```

### Issue: "Permission denied (publickey)"
```bash
# Use HTTPS instead of SSH
git remote set-url origin https://github.com/YOUR_USERNAME/REPO_NAME.git
```

### Issue: "Updates were rejected"
```bash
# Pull first, then push
git pull origin main --rebase
git push origin main
```

### Issue: Large files
```bash
# Remove from git
git rm --cached large-file.zip

# Add to .gitignore
echo "large-file.zip" >> .gitignore

# Commit
git commit -m "chore: remove large file"
```

---

## 📦 What Gets Pushed

✅ **Included**:
- Source code (frontend, backend)
- Configuration files
- Documentation
- Docker compose files
- Package.json, requirements.txt
- README, LICENSE, CONTRIBUTING

❌ **Excluded** (via .gitignore):
- node_modules/
- .venv/
- .env files
- Database files
- Build artifacts
- IDE settings
- Log files
- Cache files

---

## 🎯 Quick Command Reference

```bash
# Status
git status

# Add all
git add .

# Commit
git commit -m "message"

# Push
git push

# Pull
git pull

# Create branch
git checkout -b branch-name

# Switch branch
git checkout branch-name

# View remotes
git remote -v

# View log
git log --oneline
```

---

## ✅ Final Checklist

Before making repository public:

- [ ] README.md is complete and professional
- [ ] All sensitive data removed (.env files not committed)
- [ ] .gitignore properly configured
- [ ] LICENSE file added
- [ ] CONTRIBUTING.md added
- [ ] Documentation is clear
- [ ] Code is clean and commented
- [ ] Tests pass (if any)
- [ ] Repository description added
- [ ] Topics/tags added
- [ ] Issues enabled

---

## 🎉 You're Done!

Your repository is now on GitHub! Share it with:

```
🔗 Repository: https://github.com/YOUR_USERNAME/REPO_NAME
⭐ Star it!
🍴 Fork it!
🐛 Report issues!
🤝 Contribute!
```

---

**Delete this file after pushing to GitHub!**
