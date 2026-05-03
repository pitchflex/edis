// EDIS GNOME Shell Extension — Dynamic Island UI
// Communicates with Python backend via D-Bus

import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const DBUS_SERVICE = 'ai.edis.Service';
const DBUS_PATH = '/ai/edis/Service';
const DBUS_IFACE = `
<node>
  <interface name='ai.edis.Service'>
    <method name='SetState'>
      <arg type='s' name='state' direction='in'/>
    </method>
    <method name='AddLog'>
      <arg type='s' name='role' direction='in'/>
      <arg type='s' name='text' direction='in'/>
    </method>
    <method name='GetState'>
      <arg type='s' name='state' direction='out'/>
    </method>
    <signal name='StateChanged'>
      <arg type='s' name='state'/>
    </signal>
    <signal name='NewLogEntry'>
      <arg type='s' name='role'/>
      <arg type='s' name='text'/>
    </signal>
    <signal name='InterruptRequested'/>
  </interface>
</node>`;

const EdisProxy = Gio.DBusProxy.makeProxyWrapper(DBUS_IFACE);

export default class EdisExtension extends Extension {
    enable() {
        this._island = new DynamicIsland(this);
        this._trayButton = new TrayButton(this);
        this._island.show();
        this._trayButton.addToPanel();
        this._connectDbus();
        this._bindHotkey();
    }

    disable() {
        this._island?.destroy();
        this._trayButton?.destroy();
        this._disconnectDbus();
        this._unbindHotkey();
        this._island = null;
        this._trayButton = null;
    }

    _connectDbus() {
        try {
            this._proxy = new EdisProxy(
                Gio.DBus.session,
                DBUS_SERVICE,
                DBUS_PATH,
                this._onDbusReady.bind(this),
            );
        } catch (e) {
            log(`EDIS: D-Bus connect failed: ${e}`);
        }
    }

    _onDbusReady(proxy, error) {
        if (error) {
            log(`EDIS: D-Bus not available — backend not running`);
            return;
        }
        this._proxy.connectSignal('StateChanged', (p, s, [state]) => {
            this._island.setState(state);
        });
        this._proxy.connectSignal('NewLogEntry', (p, s, [role, text]) => {
            this._island.addLog(role, text);
        });
        log('EDIS: Connected to backend');
    }

    _disconnectDbus() {
        this._proxy = null;
    }

    _bindHotkey() {
        Main.wm.addKeybinding(
            'edis-activate',
            this.getSettings(),
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.ALL,
            () => this._onHotkey(),
        );
    }

    _unbindHotkey() {
        Main.wm.removeKeybinding('edis-activate');
    }

    _onHotkey() {
        if (this._proxy) {
            try {
                this._proxy.call_sync('TriggerInterrupt', null,
                    Gio.DBusCallFlags.NONE, -1, null);
            } catch (e) { /* backend not ready */ }
        }
        this._island.setState('listening');
    }
}

class DynamicIsland {
    constructor(ext) {
        this._ext = ext;
        this._state = 'standby';
        this._idleTimer = null;
        this._logEntries = [];
        this._build();
    }

    _build() {
        // container positioned below panel
        this._container = new St.BoxLayout({
            style_class: 'edis-island',
            vertical: true,
            reactive: true,
        });

        this._header = new St.BoxLayout({ vertical: false });
        this._dot = new St.Widget({ style_class: 'edis-dot', width: 6, height: 6 });
        this._nameLabel = new St.Label({ style_class: 'edis-name', text: 'E.D.I.S' });
        this._statusLabel = new St.Label({ style_class: 'edis-status', text: 'standby' });

        this._header.add_child(this._dot);
        this._header.add_child(new St.Widget({ width: 8 })); // spacer
        this._header.add_child(this._nameLabel);
        this._header.add_child(new St.Widget({ x_expand: true }));
        this._header.add_child(this._statusLabel);
        this._container.add_child(this._header);

        // log area (hidden when idle/standby)
        this._logBox = new St.BoxLayout({
            vertical: true,
            style_class: 'edis-log-area',
            visible: false,
        });
        this._container.add_child(this._logBox);

        this._container.connect('button-press-event', () => {
            this._ext._onHotkey();
        });

        // position below panel
        const monitor = Main.layoutManager.primaryMonitor;
        const panelHeight = Main.panel.height;
        this._container.set_position(
            Math.floor((monitor.width - 420) / 2),
            panelHeight + 4,
        );

        Main.layoutManager.addTopChrome(this._container);
    }

    setState(state) {
        this._state = state;
        this._resetIdleTimer();

        // update dot color
        this._dot.remove_style_class_name('edis-dot-listening');
        this._dot.remove_style_class_name('edis-dot-thinking');
        this._dot.remove_style_class_name('edis-dot-working');

        this._container.remove_style_class_name('edis-island-idle');
        this._container.remove_style_class_name('edis-island-listening');
        this._container.remove_style_class_name('edis-island-working');

        switch (state) {
        case 'idle':
            this._statusLabel.text = '';
            this._nameLabel.visible = false;
            this._logBox.visible = false;
            this._container.add_style_class_name('edis-island-idle');
            break;

        case 'standby':
            this._nameLabel.visible = true;
            this._statusLabel.text = 'ready';
            this._logBox.visible = false;
            break;

        case 'listening':
            this._nameLabel.visible = true;
            this._statusLabel.text = 'listening...';
            this._dot.add_style_class_name('edis-dot-listening');
            this._container.add_style_class_name('edis-island-listening');
            this._logBox.visible = false;
            break;

        case 'thinking':
            this._statusLabel.text = 'thinking...';
            this._dot.add_style_class_name('edis-dot-thinking');
            this._logBox.visible = true;
            break;

        case 'responding':
            this._statusLabel.text = '';
            this._logBox.visible = true;
            break;

        case 'working':
            this._statusLabel.text = 'working...';
            this._dot.add_style_class_name('edis-dot-working');
            this._container.add_style_class_name('edis-island-working');
            this._logBox.visible = true;
            break;
        }
    }

    addLog(role, text) {
        const label = new St.Label({
            text: `${role === 'user' ? '>' : role === 'tool' ? '→' : '◉'} ${text}`,
            style_class: `edis-log-entry edis-log-${role}`,
        });
        label.clutter_text.set_line_wrap(true);
        label.clutter_text.set_ellipsize(0); // no ellipsis

        this._logBox.add_child(label);
        this._logEntries.push(label);

        // keep max 50 entries
        while (this._logEntries.length > 50) {
            const old = this._logEntries.shift();
            this._logBox.remove_child(old);
            old.destroy();
        }

        this._resetIdleTimer();
    }

    _resetIdleTimer() {
        if (this._idleTimer) {
            GLib.source_remove(this._idleTimer);
            this._idleTimer = null;
        }
        if (this._state !== 'idle') {
            // set to idle after 2 min of no activity
            this._idleTimer = GLib.timeout_add_seconds(
                GLib.PRIORITY_DEFAULT, 120,
                () => { this.setState('idle'); return GLib.SOURCE_REMOVE; }
            );
        }
    }

    show() {
        this._container.show();
        this.setState('standby');
    }

    destroy() {
        if (this._idleTimer) GLib.source_remove(this._idleTimer);
        Main.layoutManager.removeChrome(this._container);
        this._container.destroy();
    }
}

class TrayButton extends PanelMenu.Button {
    static { GObject.registerClass(this); }

    constructor(ext) {
        super(0.0, 'EDIS');
        this._ext = ext;
        const label = new St.Label({
            text: '⬤ EDIS',
            style_class: 'edis-tray-icon',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(label);
        this.connect('button-press-event', () => ext._onHotkey());
    }

    addToPanel() {
        Main.panel.addToStatusArea('edis', this, 0, 'right');
    }
}
