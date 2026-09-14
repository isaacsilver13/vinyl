#!/bin/sh
# Companion to run_refresh_background.sh -- reports whether the background
# refresh has finished, and its exit code if so. Prints one line:
#   RUNNING
#   DONE <exit_code>
if [ -f /tmp/refresh.done ]; then
  echo "DONE $(cat /tmp/refresh.exit 2>/dev/null || echo unknown)"
else
  echo RUNNING
fi
