scroll-swayipc-compat(1)

# NAME

scroll-swayipc-compat - expose Scroll IPC to strict Sway-schema clients

# SYNOPSIS

*scroll-swayipc-compat* [*--upstream* _SOCKET_]... [_LISTEN_SOCKET_]

# DESCRIPTION

*scroll-swayipc-compat* is a temporary Unix-socket proxy for clients that speak
the i3/Sway IPC protocol but strictly deserialize Sway's layout enum. In
compositor-to-client messages it maps Scroll's _horizontal_ layout to _splith_
and _vertical_ to _splitv_. Frame lengths are recomputed after translation.

No other payload data is changed. In particular, the proxy does not create
workspaces, rewrite workspace IDs, suppress events, or retain favourites.

Client-to-compositor messages pass through unchanged. Point strict clients at
the proxy through _SWAYSOCK_ and ensure _SCROLLSOCK_ and _I3SOCK_ do not bypass
it in those clients' environments.

If _LISTEN_SOCKET_ is omitted, the proxy listens at
_$XDG_RUNTIME_DIR/scroll-swaycompat.sock_. It refuses to replace regular files
or a socket that is accepting connections.

# UPSTREAM SOCKET DISCOVERY

Each new client connection resolves the upstream again, so a restarted Scroll
instance with a new PID-specific socket can be used without restarting the
proxy. Candidates are tried in this order:

. Explicit *--upstream* arguments, in command-line order.
. _SCROLL_REAL_SOCK_, _SCROLLSOCK_, _SWAYSOCK_, and _I3SOCK_.
. Newest-first _scroll-ipc.*.sock_ entries under _$XDG_RUNTIME_DIR_.

The listen socket itself is always excluded.

# SYSTEMD

When _NOTIFY_SOCKET_ is set, readiness is sent only after the proxy socket has
been bound. A user service may therefore use *Type=notify* and order strict IPC
clients after it.

# SEE ALSO

*scroll*(1), *scrollmsg*(1), *scroll-ipc*(7)
