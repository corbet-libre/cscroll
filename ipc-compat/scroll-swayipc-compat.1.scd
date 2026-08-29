scroll-swayipc-compat(1)

# NAME

scroll-swayipc-compat - expose scroll IPC to strict Sway-schema clients

# SYNOPSIS

*scroll-swayipc-compat* [*--upstream* _SOCKET_]... [*--favorite* _WORKSPACE_]... [_LISTEN_SOCKET_]

# DESCRIPTION

*scroll-swayipc-compat* is a temporary Unix-socket proxy for clients that speak
the i3/Sway IPC protocol but strictly deserialize Sway's layout enum. In
compositor-to-client messages it maps scroll's _horizontal_ layout to _splith_
and _vertical_ to _splitv_. Frame lengths are recomputed after translation.

With one or more *--favorite* values, the proxy also exposes those numbered
workspaces to strict workspace clients before the workspaces exist. It gives
numbered workspaces stable IDs matching their numbers, creates inactive entries
for absent favourites, and suppresses the empty event that would otherwise
remove a favourite immediately after it is left. This policy is disabled when
no favourites are configured.

Client-to-compositor messages pass through unchanged. Point strict clients at
the proxy through _SWAYSOCK_ and ensure _SCROLLSOCK_ and _I3SOCK_ do not bypass
it in those clients' environments.

If _LISTEN_SOCKET_ is omitted, the proxy listens at
_$XDG_RUNTIME_DIR/scroll-swaycompat.sock_. It refuses to replace regular files
or a socket that is accepting connections.

# UPSTREAM SOCKET DISCOVERY

Each new client connection resolves the upstream again, so a restarted scroll
instance with a new PID-specific socket can be used without restarting the
proxy. Candidates are tried in this order:

. Explicit *--upstream* arguments, in command-line order.
. _SCROLL_REAL_SOCK_, _SCROLLSOCK_, _SWAYSOCK_, and _I3SOCK_.
. Newest-first entries whose names begin scroll-ipc. and end .sock under
  _$XDG_RUNTIME_DIR_.

The listen socket itself is always excluded.

# OPTIONS

*--favorite* _WORKSPACE_
	Retain a positive numbered workspace for strict workspace clients. May be
	repeated. Duplicate values are ignored.

*--upstream* _SOCKET_
	Try an explicit Scroll IPC socket before environment and runtime discovery.
	May be repeated.

# SYSTEMD

When _NOTIFY_SOCKET_ is set, readiness is sent only after the proxy socket has
been bound. A user service may therefore use *Type=notify* and order strict IPC
clients after it.

# SEE ALSO

*scroll*(1), *scrollmsg*(1), *scroll-ipc*(7)
