# terminal-mcp demo — recorded with https://github.com/charmbracelet/vhs
#
# Usage:
#   vhs demo.tape
#
# Output: assets/demo.gif

Output assets/demo.gif
Set Width 700
Set Height 400
Set FontSize 14
Set FontFamily "JetBrains Mono,Fira Code,monospace"
Set Theme "TokyoNight"
Set Padding 20
Set TypingSpeed 40ms

# Title card
Type "# terminal-mcp — MCP server for interactive terminal sessions"
Enter
Sleep 1.5s

Type "# Install: uvx terminal-mcp"
Enter
Sleep 1s

Type "# Example MCP tool calls:"
Enter
Sleep 500ms

# session_create
Type 'echo ">>> session_create command=\"python3\" label=\"repl\""'
Enter
Sleep 300ms
Type 'echo "{ session_id: \"a1b2c3d4\", label: \"repl\", pid: 42100 }"'
Enter
Sleep 1s

# session_send
Type 'echo ">>> session_send session_id=\"a1b2c3d4\" input=\"print(42 * 42)\""'
Enter
Sleep 300ms
Type 'echo "{ bytes_sent: 16 }"'
Enter
Sleep 800ms

# session_read
Type 'echo ">>> session_read session_id=\"a1b2c3d4\""'
Enter
Sleep 300ms
Type 'echo "{ output: \"1764\\n>>> \", bytes_read: 10 }"'
Enter
Sleep 1s

# session_exec (one-shot)
Type 'echo ">>> session_exec exec=\"echo hello from terminal-mcp\""'
Enter
Sleep 300ms
Type 'echo "{ output: \"hello from terminal-mcp\\n\" }"'
Enter
Sleep 1s

# session_close
Type 'echo ">>> session_close session_id=\"a1b2c3d4\""'
Enter
Sleep 300ms
Type 'echo "{ exit_status: 0 }"'
Enter
Sleep 2s
