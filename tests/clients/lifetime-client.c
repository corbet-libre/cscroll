// SPDX-License-Identifier: Apache-2.0
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include "xdg-shell-client-protocol.h"

static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct zwlr_layer_shell_v1 *shell;
static struct xdg_wm_base *wm;

struct window {
	struct wl_surface *surface;
	struct wl_buffer *buffer;
	struct xdg_surface *xdg;
	struct xdg_popup *popup;
	struct xdg_toplevel *toplevel;
	struct zwlr_layer_surface_v1 *layer;
	bool configured;
	bool unmapped;
};

static void paint(struct window *window) {
	if (!window->buffer) {
		int size = 128 * 128 * 4;
		int fd = memfd_create("lifetime-test", MFD_CLOEXEC);
		if (fd < 0 || ftruncate(fd, size) < 0) {
			perror("create shared memory");
			exit(1);
		}
		void *data = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
		assert(data != MAP_FAILED);
		memset(data, 255, size);
		struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
		window->buffer = wl_shm_pool_create_buffer(pool, 0, 128, 128, 512,
			WL_SHM_FORMAT_XRGB8888);
		wl_shm_pool_destroy(pool);
		munmap(data, size);
		close(fd);
	}
	wl_surface_attach(window->surface, window->buffer, 0, 0);
	wl_surface_damage_buffer(window->surface, 0, 0, 128, 128);
	wl_surface_commit(window->surface);
	window->configured = true;
}

static void layer_configure(void *data, struct zwlr_layer_surface_v1 *layer,
		uint32_t serial, uint32_t width, uint32_t height) {
	zwlr_layer_surface_v1_ack_configure(layer, serial);
	paint(data);
}

static void layer_closed(void *data, struct zwlr_layer_surface_v1 *layer) {
}

static const struct zwlr_layer_surface_v1_listener layer_listener = {
	.configure = layer_configure,
	.closed = layer_closed,
};

static void xdg_configure(void *data, struct xdg_surface *surface, uint32_t serial) {
	struct window *window = data;
	if (window->unmapped) {
		// Unmapping invalidates configure serials already in flight.
		return;
	}
	xdg_surface_ack_configure(surface, serial);
	paint(data);
}

static const struct xdg_surface_listener xdg_listener = {
	.configure = xdg_configure,
};

static void popup_configure(void *data, struct xdg_popup *popup,
		int32_t x, int32_t y, int32_t width, int32_t height) {
}

static void popup_done(void *data, struct xdg_popup *popup) {
}

static void popup_repositioned(void *data, struct xdg_popup *popup, uint32_t token) {
}

static const struct xdg_popup_listener popup_listener = {
	.configure = popup_configure,
	.popup_done = popup_done,
	.repositioned = popup_repositioned,
};

static void toplevel_configure(void *data, struct xdg_toplevel *toplevel,
		int32_t width, int32_t height, struct wl_array *states) {
}

static void toplevel_close(void *data, struct xdg_toplevel *toplevel) {
}

static const struct xdg_toplevel_listener toplevel_listener = {
	.configure = toplevel_configure,
	.close = toplevel_close,
};

static void ping(void *data, struct xdg_wm_base *base, uint32_t serial) {
	xdg_wm_base_pong(base, serial);
}

static const struct xdg_wm_base_listener wm_listener = {.ping = ping};

static void global(void *data, struct wl_registry *registry, uint32_t name,
		const char *interface, uint32_t version) {
	if (strcmp(interface, wl_compositor_interface.name) == 0) {
		compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 4);
	} else if (strcmp(interface, wl_shm_interface.name) == 0) {
		shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
	} else if (strcmp(interface, zwlr_layer_shell_v1_interface.name) == 0) {
		shell = wl_registry_bind(registry, name, &zwlr_layer_shell_v1_interface, 4);
	} else if (strcmp(interface, xdg_wm_base_interface.name) == 0) {
		wm = wl_registry_bind(registry, name, &xdg_wm_base_interface, 3);
		xdg_wm_base_add_listener(wm, &wm_listener, NULL);
	}
}

static void global_remove(void *data, struct wl_registry *registry, uint32_t name) {
}

static const struct wl_registry_listener registry_listener = {
	.global = global,
	.global_remove = global_remove,
};

static void sync_display(void) {
	if (wl_display_roundtrip(display) < 0) {
		fprintf(stderr, "Wayland connection failed\n");
		exit(1);
	}
}

static struct xdg_positioner *positioner(int offset) {
	struct xdg_positioner *pos = xdg_wm_base_create_positioner(wm);
	xdg_positioner_set_size(pos, 128, 128);
	xdg_positioner_set_anchor_rect(pos, 0, 0, 128, 128);
	xdg_positioner_set_offset(pos, offset, offset);
	return pos;
}

static void create_popup(struct window *popup, struct window *layer) {
	popup->surface = wl_compositor_create_surface(compositor);
	popup->xdg = xdg_wm_base_get_xdg_surface(wm, popup->surface);
	xdg_surface_add_listener(popup->xdg, &xdg_listener, popup);
	struct xdg_positioner *pos = positioner(0);
	popup->popup = xdg_surface_get_popup(popup->xdg, NULL, pos);
	xdg_popup_add_listener(popup->popup, &popup_listener, popup);
	zwlr_layer_surface_v1_get_popup(layer->layer, popup->popup);
	xdg_positioner_destroy(pos);
	wl_surface_commit(popup->surface);
	while (!popup->configured) {
		sync_display();
	}
	sync_display();
}

static void destroy_popup(struct window *popup) {
	if (!popup->popup) {
		return;
	}
	xdg_popup_destroy(popup->popup);
	xdg_surface_destroy(popup->xdg);
	wl_surface_destroy(popup->surface);
	wl_buffer_destroy(popup->buffer);
	memset(popup, 0, sizeof(*popup));
}

int main(void) {
	setvbuf(stdout, NULL, _IOLBF, 0);
	display = wl_display_connect(NULL);
	assert(display);
	struct wl_registry *registry = wl_display_get_registry(display);
	wl_registry_add_listener(registry, &registry_listener, NULL);
	sync_display();
	assert(compositor && shm && shell && wm);

	struct window layer = {0}, popup = {0}, view = {0};
	layer.surface = wl_compositor_create_surface(compositor);
	layer.layer = zwlr_layer_shell_v1_get_layer_surface(shell, layer.surface,
		NULL, ZWLR_LAYER_SHELL_V1_LAYER_TOP, "lifetime-test");
	zwlr_layer_surface_v1_set_size(layer.layer, 128, 128);
	zwlr_layer_surface_v1_add_listener(layer.layer, &layer_listener, &layer);
	wl_surface_commit(layer.surface);
	while (!layer.configured) {
		sync_display();
	}
	sync_display();
	puts("ready");

	char command[64];
	unsigned serial = 0;
	while (fgets(command, sizeof(command), stdin)) {
		if (strcmp(command, "view\n") == 0) {
			view.surface = wl_compositor_create_surface(compositor);
			view.xdg = xdg_wm_base_get_xdg_surface(wm, view.surface);
			xdg_surface_add_listener(view.xdg, &xdg_listener, &view);
			view.toplevel = xdg_surface_get_toplevel(view.xdg);
			xdg_toplevel_add_listener(view.toplevel, &toplevel_listener, &view);
			xdg_toplevel_set_app_id(view.toplevel, "lifetime-test");
			wl_surface_commit(view.surface);
			while (!view.configured) {
				sync_display();
			}
		} else if (strcmp(command, "unmap\n") == 0) {
			sync_display();
			view.unmapped = true;
			wl_surface_attach(view.surface, NULL, 0, 0);
			wl_surface_commit(view.surface);
			view.configured = false;
		} else if (strcmp(command, "remap\n") == 0) {
			view.unmapped = false;
			wl_surface_commit(view.surface);
			while (!view.configured) {
				sync_display();
			}
		} else if (strcmp(command, "destroy-view\n") == 0) {
			xdg_toplevel_destroy(view.toplevel);
			xdg_surface_destroy(view.xdg);
			wl_surface_destroy(view.surface);
			wl_buffer_destroy(view.buffer);
			memset(&view, 0, sizeof(view));
		} else if (strcmp(command, "popup\n") == 0) {
			create_popup(&popup, &layer);
		} else if (strcmp(command, "reposition\n") == 0) {
			struct xdg_positioner *pos = positioner(++serial * 3);
			xdg_popup_reposition(popup.popup, pos, serial);
			xdg_positioner_destroy(pos);
			sync_display();
		} else if (strcmp(command, "resize\n") == 0) {
			zwlr_layer_surface_v1_set_size(layer.layer, 128 + ++serial, 128);
			wl_surface_commit(layer.surface);
		} else if (strcmp(command, "destroy-popup\n") == 0) {
			destroy_popup(&popup);
		} else if (strcmp(command, "destroy-layer\n") == 0) {
			zwlr_layer_surface_v1_destroy(layer.layer);
			wl_surface_destroy(layer.surface);
			wl_buffer_destroy(layer.buffer);
			layer.layer = NULL;
		} else if (strcmp(command, "quit\n") == 0) {
			break;
		} else {
			return 2;
		}
		sync_display();
		puts("done");
	}

	destroy_popup(&popup);
	if (view.toplevel) {
		xdg_toplevel_destroy(view.toplevel);
		xdg_surface_destroy(view.xdg);
		wl_surface_destroy(view.surface);
		wl_buffer_destroy(view.buffer);
	}
	if (layer.layer) {
		zwlr_layer_surface_v1_destroy(layer.layer);
		wl_surface_destroy(layer.surface);
		wl_buffer_destroy(layer.buffer);
	}
	sync_display();
	xdg_wm_base_destroy(wm);
	zwlr_layer_shell_v1_destroy(shell);
	wl_shm_destroy(shm);
	wl_compositor_destroy(compositor);
	wl_registry_destroy(registry);
	wl_display_disconnect(display);
	return 0;
}
