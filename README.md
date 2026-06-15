# Petacomm Easy

Manage your Linux server using natural language. An AI-powered terminal tool.

## Installation

```bash
pip install rich psutil
python petacomm.py help
```

Or to use globally:

```bash
pip install -e .
petacomm help
```

## Usage

```bash
# System status
petacomm status

# Health score
petacomm health

# List
petacomm ls services
petacomm ls ports
petacomm ls backups
petacomm ls processes

# Logs
petacomm logs nginx
petacomm logs nginx --follow

# Search and delete files
petacomm find "gatebell"

# Backup
petacomm backup now
petacomm restore 2026-04-17_09-22-00

# AI Request (Requires Claude API)
petacomm login
petacomm -r "why isn't nginx working"
petacomm -r "why is the disk full, clean it"
petacomm -r "are there any security vulnerabilities"

# Simulation (Show but don't run it)
petacomm --dry-run -r "restart mysql"

# LLM Configuration
petacomm config (Shows you available AI Models)
petacomm config --model model_name  (example: petacomm config --model haiku) -> it changes current AI model to selected one.
```

## API Key

You can get a free API key at https://console.anthropic.com.

```bash
petacomm login
# sk-ant-... enter your api key
```

It is saved to the `~/.petacomm/config.json` file.
