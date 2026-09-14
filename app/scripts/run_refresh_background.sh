#!/bin/sh
# Launches refresh_all.py fully detached from the invoking SSH session, so a
# short `flyctl ssh console` call can start it and disconnect immediately
# instead of holding a session open for the job's multi-minute duration.
#
# See .github/workflows/app-daily-refresh.yml for why this exists: flyctl
# ssh console's tunnel doesn't reliably survive being held open that long
# (it dropped mid-session on the 2026-09-12/13 scheduled runs -- "ssh
# shell: wait: remote command exited without exit status or exit signal"),
# and `flyctl machine exec` has a hard, non-configurable 60s server-side
# timeout on Fly's Machines API -- both unusable for this job. `fly
# console` was ruled out too: it spawns a brand-new temporary machine with
# no volume mount, so it can't reach /data (the SQLite DB and Discogs
# tokens the refresh needs).
#
# A separate poller (refresh_status.sh) checks /tmp/refresh.done.

rm -f /tmp/refresh.done /tmp/refresh.exit

setsid nohup sh -c '
  setpriv --reuid=appuser --regid=appuser --init-groups python /app/refresh_all.py --force > /tmp/refresh.log 2>&1
  echo $? > /tmp/refresh.exit
  touch /tmp/refresh.done
' < /dev/null > /tmp/refresh_wrapper.log 2>&1 &

echo started
