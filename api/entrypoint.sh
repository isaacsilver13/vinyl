#!/bin/sh
# Runs as root (the container's default user -- see Dockerfile) so it can fix
# up ownership of the Fly volume mounted at /data before dropping to the
# unprivileged appuser. A build-time `chown /data` does NOT survive a real
# Fly volume mount: Fly (like a fresh Docker named volume) mounts its own
# root-owned directory over whatever was baked into the image at that path,
# so this has to happen at container *runtime*, on every start.
set -e

mkdir -p /data
chown -R appuser:appuser /data

# Drop privileges with setpriv rather than `su -s`: util-linux's `su`
# forwards SIGTERM to its child but then SIGKILLs it ~2s later regardless,
# which never gives uvicorn a real graceful-shutdown window on deploy or
# Fly's auto_stop_machines. setpriv instead directly execs its target
# program (its own <program> argument, no separate flag needed -- there is
# no `--exec` option) as appuser -- no forked child, no su-imposed timeout,
# so whatever ends up as PID 1 receives signals the way it would running as
# root. (setpriv ships in util-linux, already present on this image's
# Debian base -- no new package needed.)
#
# migrate_or_stamp.py has to run (and finish) before uvicorn starts, so it
# can't itself be setpriv's target program here -- that's still done via a
# small `sh -c` so the final `exec uvicorn` can replace *that* shell in turn
# and become PID 1 directly, with nothing wrapping it once migrations are done.
#
# Unlike `su`, setpriv only changes process credentials (uid/gid) -- it does
# NOT update $HOME to match, so it stays /root (root's value) unless set
# explicitly here. Nothing in this service currently reads $HOME, but export
# it (and USER) anyway to appuser's actual home (`useradd --create-home` in
# the Dockerfile) so a future dependency that does (pip caches, some
# library's default config-file lookup, etc.) doesn't silently try to read
# a root-owned, appuser-unreadable path and crash -- see app/entrypoint.sh,
# where streamlit hit exactly that with its secrets.toml lookup.
export HOME=/home/appuser
export USER=appuser
exec setpriv --reuid=appuser --regid=appuser --init-groups \
    /bin/sh -c 'python migrate_or_stamp.py && exec uvicorn vinyl_api.main:app --host 0.0.0.0 --port 8000'
