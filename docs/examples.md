# Use Cases & Examples

Real-world recipes for common terminal-mcp workflows.

---

## SSH Sessions

### Connect to a Remote Server

```
session_create   command="ssh user@prod-server.com"   label="prod"
session_read     session_id="a1b2c3d4"  timeout=5
# Wait for password prompt or key auth to complete

session_interact session_id="a1b2c3d4"  input="hostname"  wait_for="\$"
session_interact session_id="a1b2c3d4"  input="df -h"  wait_for="\$"
session_interact session_id="a1b2c3d4"  input="free -m"  wait_for="\$"
session_close    session_id="a1b2c3d4"
```

### SSH with Password Authentication

```
session_create  command="ssh user@server.com"  label="remote"
session_read    session_id="a1b2c3d4"  timeout=10
# Wait for "password:" prompt

session_send    session_id="a1b2c3d4"  password="my-secret-password"
# password parameter ensures credentials are not logged

session_read    session_id="a1b2c3d4"  timeout=5
```

### SSH Jump Host / Bastion

```
session_create  command="ssh -J bastion@jump.example.com user@internal.example.com"  label="internal"
session_read    session_id="a1b2c3d4"  timeout=15
# Longer timeout for multi-hop connection
```

---

## Interactive REPLs

### Python

```
session_create   command="python3"  label="python"
session_interact session_id="e5f6g7h8"  input="import json"  wait_for=">>>"
session_interact session_id="e5f6g7h8"  input="data = {'name': 'test', 'value': 42}"  wait_for=">>>"
session_interact session_id="e5f6g7h8"  input="print(json.dumps(data, indent=2))"  wait_for=">>>"
session_close    session_id="e5f6g7h8"
```

### Node.js

```
session_create   command="node"  label="node"
session_interact session_id="e5f6g7h8"  input="const fs = require('fs')"  wait_for=">"
session_interact session_id="e5f6g7h8"  input="fs.readdirSync('.').length"  wait_for=">"
session_close    session_id="e5f6g7h8"
```

### IPython / Jupyter Console

```
session_create   command="ipython"  label="ipython"
session_interact session_id="e5f6g7h8"  input="%timeit sum(range(1000000))"  wait_for="In \["
session_interact session_id="e5f6g7h8"  input="import numpy as np; np.random.rand(3,3)"  wait_for="In \["
session_close    session_id="e5f6g7h8"
```

---

## Database CLIs

### PostgreSQL

```
session_create   command="psql -U admin -d mydb"  label="postgres"
session_interact session_id="x1y2z3w4"  input="SELECT count(*) FROM users;"  wait_for="row"
session_interact session_id="x1y2z3w4"  input="\\dt"  wait_for="#"
session_interact session_id="x1y2z3w4"  input="\\d users"  wait_for="#"
session_close    session_id="x1y2z3w4"
```

### MySQL

```
session_create   command="mysql -u root -p mydb"  label="mysql"
session_read     session_id="x1y2z3w4"  timeout=5
# Enter password when prompted
session_send     session_id="x1y2z3w4"  password="db-password"
session_interact session_id="x1y2z3w4"  input="SHOW TABLES;"  wait_for="mysql>"
session_close    session_id="x1y2z3w4"
```

### Redis

```
session_create   command="redis-cli"  label="redis"
session_interact session_id="x1y2z3w4"  input="KEYS *"  wait_for=">"
session_interact session_id="x1y2z3w4"  input="INFO memory"  wait_for=">"
session_close    session_id="x1y2z3w4"
```

### MongoDB

```
session_create   command="mongosh"  label="mongo"
session_interact session_id="x1y2z3w4"  input="show dbs"  wait_for=">"
session_interact session_id="x1y2z3w4"  input="use mydb"  wait_for=">"
session_interact session_id="x1y2z3w4"  input="db.users.countDocuments()"  wait_for=">"
session_close    session_id="x1y2z3w4"
```

---

## TUI Applications

### htop (System Monitor)

```
session_create  command="htop"  label="monitor"
session_read    session_id="a1b2c3d4"
# Auto-detects TUI, returns screen snapshot

# Sort by memory
session_send    session_id="a1b2c3d4"  key="F6"
session_read    session_id="a1b2c3d4"  mode="diff"
session_send    session_id="a1b2c3d4"  key="down"
session_send    session_id="a1b2c3d4"  key="enter"
session_read    session_id="a1b2c3d4"  mode="diff"

# Quit
session_send    session_id="a1b2c3d4"  key="F10"
session_close   session_id="a1b2c3d4"
```

### vim / neovim

```
session_create  command="vim myfile.txt"  label="editor"  rows=40  cols=120
session_read    session_id="a1b2c3d4"
# Returns screen snapshot

# Enter insert mode, type text
session_send    session_id="a1b2c3d4"  key="i"
session_send    session_id="a1b2c3d4"  input="Hello, World!"  press_enter=false
session_send    session_id="a1b2c3d4"  key="escape"

# Save and quit
session_send    session_id="a1b2c3d4"  input=":wq"
session_close   session_id="a1b2c3d4"
```

### fzf (Fuzzy Finder)

```
session_create  command="find . -type f | fzf"  label="fzf"
session_read    session_id="a1b2c3d4"

# Type search query
session_send    session_id="a1b2c3d4"  input="main.py"  press_enter=false
session_read    session_id="a1b2c3d4"  mode="diff"

# Navigate and select
session_send    session_id="a1b2c3d4"  key="down"
session_send    session_id="a1b2c3d4"  key="enter"
session_read    session_id="a1b2c3d4"
```

---

## Build & Development Workflows

### Watch a Build

```
session_create   command="bash"  label="build"
session_send     session_id="a1b2c3d4"  input="npm run build"
session_wait_for session_id="a1b2c3d4"  pattern="Build complete|ERROR|FAIL"  timeout=120
```

### Run Tests and Wait for Results

```
session_create   command="bash"  label="tests"
session_send     session_id="a1b2c3d4"  input="pytest tests/ -v"
session_wait_for session_id="a1b2c3d4"  pattern="passed|failed|error"  timeout=300
```

### Start a Dev Server

```
session_create   command="bash"  label="devserver"
session_send     session_id="a1b2c3d4"  input="npm run dev"
session_wait_for session_id="a1b2c3d4"  pattern="ready|localhost|started"  timeout=30
# Server is now running in the background
# Use session_read later to check for errors
```

### Docker Compose

```
session_exec  exec="docker compose up -d"  timeout=30
session_exec  exec="docker compose ps"
session_exec  exec="docker compose logs --tail=20 web"
```

---

## Multi-Session Workflows

### Parallel Operations

```
# Start a build in one session
session_create  command="bash"  label="build"
session_send    session_id="build-id"  input="npm run build"

# Monitor logs in another
session_create  command="bash"  label="logs"
session_send    session_id="logs-id"  input="tail -f /var/log/app.log"

# Check build status
session_wait_for  session_id="build-id"  pattern="complete|error"  timeout=120

# Read recent logs
session_read  session_id="logs-id"
```

### Managing Multiple Sessions

```
session_list
# Returns all active sessions with idle times

# Close idle sessions
session_close  session_id="old-session-1"
session_close  session_id="old-session-2"
```

---

## Tips & Patterns

### Use `wait_for` Instead of Timeouts

Instead of:
```
session_send  session_id="x"  input="make build"
session_read  session_id="x"  timeout=30
# May return incomplete output if build takes longer
```

Use:
```
session_send     session_id="x"  input="make build"
session_wait_for session_id="x"  pattern="Build succeeded|Error:"  timeout=120
# Returns as soon as the pattern matches
```

### Use `session_interact` to Halve Round Trips

Instead of:
```
session_send  session_id="x"  input="ls -la"
session_read  session_id="x"
```

Use:
```
session_interact  session_id="x"  input="ls -la"  wait_for="\$"
# One call instead of two
```

### Use `diff` Mode for TUI Monitoring

```
session_read  session_id="htop-session"  mode="diff"
# Returns only lines that changed - much fewer tokens
```

### Use `session_exec` for One-Off Commands

```
session_exec  exec="git status"
session_exec  exec="python3 -c 'import sys; print(sys.version)'"
# No session management needed
```

### Send Ctrl-C to Stop a Running Process

```
session_send  session_id="x"  control_char="c"
session_read  session_id="x"
```

### Resize for Wide Output

```
session_resize  session_id="x"  rows=50  cols=200
session_read    session_id="x"  mode="snapshot"
# Now captures wide tables without wrapping
```
