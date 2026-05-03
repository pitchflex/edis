#!/bin/bash
# EDIS installer — Fedora / GNOME Wayland
set -e

echo "=== EDIS Installer ==="

# System packages
echo "[1/5] Installing system packages..."
sudo dnf install -y \
  python3-pip \
  grim \
  ydotool \
  brightnessctl \
  espeak-ng \
  fd-find \
  ripgrep \
  python3-gobject \
  python3-dbus \
  libcanberra \
  paplay

# Add user to uinput group (required for ydotool)
echo "[2/5] Configuring ydotool..."
sudo groupadd -f uinput
sudo usermod -aG uinput "$USER"
sudo tee /etc/udev/rules.d/60-ydotool.rules > /dev/null << 'EOF'
KERNEL=="uinput", GROUP="uinput", MODE="0660"
EOF
sudo systemctl enable ydotoold
sudo systemctl start ydotoold
echo "Note: Log out and back in for uinput group to take effect"

# Python dependencies
echo "[3/5] Installing Python packages..."
pip install -r requirements.txt

# EDIS base dirs
echo "[4/5] Creating EDIS directories..."
mkdir -p ~/.edis/{memory/chroma,skills,piper,logs,tmp,wake_word}

# Install GNOME Shell extension
echo "[5/5] Installing GNOME Shell extension..."
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/edis@edis.ai"
mkdir -p "$EXT_DIR"
cp extension/* "$EXT_DIR/"

# compile gschemas if settings schema exists
if [ -f "extension/schemas/org.gnome.shell.extensions.edis.gschema.xml" ]; then
  cp extension/schemas/* "$EXT_DIR/schemas/"
  glib-compile-schemas "$EXT_DIR/schemas/"
fi

echo ""
echo "=== EDIS installed ==="
echo ""
echo "Next steps:"
echo "  1. Add your API keys to config.toml (groq_key and/or gemini_key)"
echo "  2. Enable the extension: gnome-extensions enable edis@edis.ai"
echo "     (or use GNOME Extensions app)"
echo "  3. Download Piper voice model:"
echo "     https://huggingface.co/rhasspy/piper-voices"
echo "     Place en_US-amy-medium.onnx in ~/.edis/piper/"
echo "  4. Start EDIS: python main.py"
echo ""
echo "Say '${WAKE_WORD:-edis}' or press Super+E to activate"
