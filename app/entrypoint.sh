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
# which never gives streamlit a real graceful-shutdown window on deploy or
# Fly's auto_stop_machines. setpriv instead directly execs its target
# program (its own <program> argument, no separate flag needed -- there is
# no `--exec` option) as appuser -- no forked child, no su-imposed timeout,
# so streamlit itself ends up as PID 1 and receives signals directly.
# (setpriv ships in util-linux, already present on this image's Debian
# base -- no new package needed.)
#
# Unlike `su`, setpriv only changes process credentials (uid/gid) -- it does
# NOT update $HOME to match. Left as /root (root's value, inherited as-is),
# streamlit tries to read /root/.streamlit/secrets.toml as appuser and
# crashes with PermissionError before it ever binds its port. Export HOME
# (and USER, for anything that reads it) to appuser's actual home
# (`useradd --create-home` in the Dockerfile) before the exec so streamlit
# looks in the right, appuser-readable place.
export HOME=/home/appuser
export USER=appuser
exec setpriv --reuid=appuser --regid=appuser --init-groups \
    streamlit run app.py
